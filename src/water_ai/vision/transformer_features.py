from __future__ import annotations

from typing import Any

import numpy as np
import torch
import torch.nn as nn


TRANSFORMER_PATCH_GRID = 4
TRANSFORMER_TOKEN_DIM = 9
TRANSFORMER_EMBED_DIM = 32
TRANSFORMER_SEED = 20260817


class VisualPatchTransformer(nn.Module):
    """Small offline visual Transformer used to encode UAV image patches."""

    def __init__(self) -> None:
        super().__init__()
        self.projection = nn.Linear(TRANSFORMER_TOKEN_DIM, TRANSFORMER_EMBED_DIM)
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=TRANSFORMER_EMBED_DIM,
            nhead=4,
            dim_feedforward=64,
            dropout=0.0,
            batch_first=True,
            activation="gelu",
        )
        self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=2)
        self.norm = nn.LayerNorm(TRANSFORMER_EMBED_DIM)

    def forward(self, tokens: torch.Tensor) -> torch.Tensor:
        encoded = self.encoder(self.projection(tokens))
        return self.norm(encoded.mean(dim=1))


_VISUAL_TRANSFORMER: VisualPatchTransformer | None = None


def _get_visual_transformer() -> VisualPatchTransformer:
    global _VISUAL_TRANSFORMER
    if _VISUAL_TRANSFORMER is None:
        state = torch.random.get_rng_state()
        torch.manual_seed(TRANSFORMER_SEED)
        _VISUAL_TRANSFORMER = VisualPatchTransformer().eval()
        torch.random.set_rng_state(state)
    return _VISUAL_TRANSFORMER


def _visual_transformer_tokens(image_rgb: np.ndarray) -> torch.Tensor:
    height, width = image_rgb.shape[:2]
    tokens: list[list[float]] = []
    for row in range(TRANSFORMER_PATCH_GRID):
        y0 = int(row * height / TRANSFORMER_PATCH_GRID)
        y1 = int((row + 1) * height / TRANSFORMER_PATCH_GRID)
        for col in range(TRANSFORMER_PATCH_GRID):
            x0 = int(col * width / TRANSFORMER_PATCH_GRID)
            x1 = int((col + 1) * width / TRANSFORMER_PATCH_GRID)
            patch = image_rgb[y0:y1, x0:x1].astype(np.float32) / 255.0
            if patch.size == 0:
                patch = image_rgb.astype(np.float32) / 255.0
            flattened = patch.reshape(-1, 3)
            mean_rgb = flattened.mean(axis=0)
            std_rgb = flattened.std(axis=0)
            tokens.append(
                [
                    float(mean_rgb[0]),
                    float(mean_rgb[1]),
                    float(mean_rgb[2]),
                    float(std_rgb[0]),
                    float(std_rgb[1]),
                    float(std_rgb[2]),
                    row / max(TRANSFORMER_PATCH_GRID - 1, 1),
                    col / max(TRANSFORMER_PATCH_GRID - 1, 1),
                    float(patch.mean()),
                ]
            )
    return torch.tensor(tokens, dtype=torch.float32).unsqueeze(0)


def extract_visual_transformer_features(image_rgb: np.ndarray) -> dict[str, Any]:
    if image_rgb.size == 0:
        return {}
    with torch.no_grad():
        embedding = _get_visual_transformer()(_visual_transformer_tokens(image_rgb)).squeeze(0)
    values = embedding.detach().cpu().numpy().astype(float)
    features = {
        f"visual_transformer_embedding_{idx:02d}": float(value)
        for idx, value in enumerate(values, start=1)
    }
    features["visual_transformer_embedding_norm"] = float(np.linalg.norm(values))
    features["visual_transformer_patch_count"] = TRANSFORMER_PATCH_GRID * TRANSFORMER_PATCH_GRID
    features["visual_transformer_embed_dim"] = TRANSFORMER_EMBED_DIM
    return features
