from __future__ import annotations

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F


def _normalize_adjacency(adjacency: np.ndarray) -> np.ndarray:
    adjacency = adjacency.astype(np.float32)
    adjacency = adjacency + np.eye(adjacency.shape[0], dtype=np.float32)
    degree = adjacency.sum(axis=1, keepdims=True)
    degree[degree == 0.0] = 1.0
    return adjacency / degree


class FeatureGraphBlock(nn.Module):
    def __init__(self, adjacency: np.ndarray) -> None:
        super().__init__()
        normalized = _normalize_adjacency(adjacency)
        self.register_buffer("adjacency", torch.tensor(normalized, dtype=torch.float32))
        self.mix_logit = nn.Parameter(torch.tensor(0.35))
        self.norm = nn.LayerNorm(normalized.shape[0])

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        propagated = torch.einsum("ij,btj->bti", self.adjacency, x)
        mix = torch.sigmoid(self.mix_logit)
        return self.norm(mix * x + (1.0 - mix) * propagated)


class BoundarySegmentationHead(nn.Module):
    """Boundary-state classifier over the temporal backbone representation."""

    def __init__(self, hidden_dim: int) -> None:
        super().__init__()
        self.gate = nn.Sequential(
            nn.Linear(hidden_dim * 3, hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, hidden_dim),
        )
        self.head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, 2),
        )

    def forward(
        self,
        encoded_sequence: torch.Tensor,
        attention_pooled: torch.Tensor,
        last_state: torch.Tensor,
    ) -> torch.Tensor:
        mean_state = encoded_sequence.mean(dim=1)
        fused_state = torch.cat([attention_pooled, mean_state, last_state], dim=-1)
        return self.head(self.gate(fused_state))


class MSCIMPrototype(nn.Module):
    def __init__(
        self,
        num_features: int,
        adjacency: np.ndarray,
        feature_index: dict[str, int],
        clearness_log_min: float,
        clearness_log_max: float,
        hidden_dim: int,
        transformer_layers: int,
        num_heads: int,
        dropout: float,
        max_sequence_length: int = 32,
        enable_boundary_head: bool = True,
    ) -> None:
        super().__init__()
        self.num_features = num_features
        self.feature_index = feature_index
        self.max_sequence_length = max_sequence_length
        self.register_buffer(
            "clearness_log_min", torch.tensor(float(clearness_log_min), dtype=torch.float32)
        )
        self.register_buffer(
            "clearness_log_max", torch.tensor(float(clearness_log_max), dtype=torch.float32)
        )
        self.graph_block = FeatureGraphBlock(adjacency)
        self.input_projection = nn.Linear(num_features, hidden_dim)
        self.position_embedding = nn.Parameter(
            torch.zeros(1, max_sequence_length, hidden_dim)
        )
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=hidden_dim,
            nhead=num_heads,
            dim_feedforward=hidden_dim * 4,
            dropout=dropout,
            batch_first=True,
            activation="gelu",
        )
        self.temporal_encoder = nn.TransformerEncoder(
            encoder_layer, num_layers=transformer_layers
        )
        self.temporal_pooler = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim),
            nn.Tanh(),
            nn.Linear(hidden_dim, 1),
        )
        self.dropout = nn.Dropout(dropout)
        self.causal_scorer = nn.Sequential(
            nn.Linear(num_features, hidden_dim),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, num_features),
        )
        self.turbidity_direct_head = nn.Sequential(
            nn.Linear(hidden_dim + num_features, hidden_dim),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, 1),
        )
        self.turbidity_delta_head = nn.Sequential(
            nn.Linear(hidden_dim + num_features, hidden_dim),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, 1),
        )
        self.clearness_head = nn.Sequential(
            nn.Linear(hidden_dim + num_features, hidden_dim),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, 1),
        )
        self.risk_head = nn.Sequential(
            nn.Linear(hidden_dim + num_features, hidden_dim),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, 3),
        )
        self.delta_gate = nn.Sequential(
            nn.Linear(hidden_dim + num_features, hidden_dim // 2),
            nn.GELU(),
            nn.Linear(hidden_dim // 2, 1),
        )
        self.persistence_mix_logit = nn.Parameter(torch.tensor(1.35))
        self.delta_scale = nn.Parameter(torch.tensor(0.18))
        self.clearness_turbidity_coeff = nn.Parameter(torch.tensor(0.85))
        self.clearness_bias = nn.Parameter(torch.tensor(1.2))
        self.enable_boundary_head = enable_boundary_head
        self.boundary_head = BoundarySegmentationHead(hidden_dim) if enable_boundary_head else None
        nn.init.normal_(self.position_embedding, mean=0.0, std=0.02)

    def derive_clearness_from_log_turbidity(self, log_turbidity: torch.Tensor) -> torch.Tensor:
        log_range = torch.clamp(self.clearness_log_max - self.clearness_log_min, min=1e-6)
        clearness = 1.0 - (log_turbidity - self.clearness_log_min) / log_range
        return torch.clamp(clearness, min=0.0, max=1.0)

    def forward(self, x: torch.Tensor, x_raw: torch.Tensor | None = None) -> dict[str, torch.Tensor]:
        graph_encoded = self.graph_block(x)
        seq_len = graph_encoded.size(1)
        if seq_len > self.max_sequence_length:
            raise ValueError(
                f"Input sequence length {seq_len} exceeds max_sequence_length {self.max_sequence_length}."
            )
        temporal_input = self.input_projection(graph_encoded)
        temporal_input = temporal_input + self.position_embedding[:, :seq_len, :]
        temporal_input = self.dropout(temporal_input)
        temporal_output = self.temporal_encoder(temporal_input)

        temporal_attention_scores = self.temporal_pooler(temporal_output).squeeze(-1)
        temporal_attention = torch.softmax(temporal_attention_scores, dim=1)
        attention_pooled = torch.sum(
            temporal_output * temporal_attention.unsqueeze(-1), dim=1
        )
        pooled_temporal = (
            attention_pooled + temporal_output.mean(dim=1) + temporal_output[:, -1, :]
        ) / 3.0
        feature_summary = graph_encoded.mean(dim=1)
        causal_saliency = torch.softmax(self.causal_scorer(feature_summary), dim=-1)
        causal_context = feature_summary * causal_saliency
        fused_representation = torch.cat([pooled_temporal, causal_context], dim=-1)

        direct_log_turbidity = F.softplus(
            self.turbidity_direct_head(fused_representation).squeeze(-1)
        )
        delta_gate = torch.sigmoid(self.delta_gate(fused_representation).squeeze(-1))
        delta_log_turbidity = (
            delta_gate
            * F.softplus(self.delta_scale)
            * torch.tanh(self.turbidity_delta_head(fused_representation).squeeze(-1))
        )

        baseline_log_turbidity = direct_log_turbidity.detach() * 0.0
        if x_raw is not None and "turbidity" in self.feature_index:
            turbidity_index = self.feature_index["turbidity"]
            baseline_log_turbidity = torch.log1p(torch.clamp(x_raw[:, -1, turbidity_index], min=0.0))

        residual_log_turbidity = torch.clamp(
            baseline_log_turbidity + delta_log_turbidity, min=0.0
        )
        persistence_mix = torch.sigmoid(self.persistence_mix_logit)
        log_turbidity_pred = persistence_mix * residual_log_turbidity + (
            1.0 - persistence_mix
        ) * direct_log_turbidity
        turbidity_pred = torch.expm1(log_turbidity_pred)
        clearness_aux_logit = (
            self.clearness_head(fused_representation).squeeze(-1)
            + self.clearness_bias
            - F.softplus(self.clearness_turbidity_coeff) * log_turbidity_pred
        )
        clearness_aux_pred = torch.sigmoid(clearness_aux_logit)
        clearness_pred = self.derive_clearness_from_log_turbidity(log_turbidity_pred)
        risk_logits = self.risk_head(fused_representation)
        self_purification_failure_logit = risk_logits[:, 0]
        turbidity_surge_logit = risk_logits[:, 1]
        critical_transition_logit = risk_logits[:, 2]

        output = {
            "graph_encoded": graph_encoded,
            "temporal_output": temporal_output,
            "temporal_attention": temporal_attention,
            "latent": pooled_temporal,
            "causal_saliency": causal_saliency,
            "delta_gate": delta_gate,
            "baseline_log_turbidity": baseline_log_turbidity,
            "delta_log_turbidity": delta_log_turbidity,
            "direct_log_turbidity": direct_log_turbidity,
            "log_turbidity_pred": log_turbidity_pred,
            "turbidity_pred": turbidity_pred,
            "clearness_aux_pred": clearness_aux_pred,
            "clearness_pred": clearness_pred,
            "self_purification_failure_logit": self_purification_failure_logit,
            "self_purification_failure_prob": torch.sigmoid(self_purification_failure_logit),
            "turbidity_surge_logit": turbidity_surge_logit,
            "turbidity_surge_prob": torch.sigmoid(turbidity_surge_logit),
            "critical_transition_logit": critical_transition_logit,
            "critical_transition_prob": torch.sigmoid(critical_transition_logit),
        }
        if self.enable_boundary_head and self.boundary_head is not None:
            output["boundary_logits"] = self.boundary_head(
                temporal_output,
                attention_pooled=attention_pooled,
                last_state=temporal_output[:, -1, :],
            )
        return output
