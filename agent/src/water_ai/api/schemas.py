"""Pydantic data models for Water AI API."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class ScenarioType(str, Enum):
    """Available water quality scenarios."""

    S1_EXTERNAL_INPUT = "s1_external_input"
    S2_INTERNAL_RELEASE = "s2_internal_release"
    S3_ALGAE_BLOOM = "s3_algae_bloom"
    S4_CHRONIC_COMBO = "s4_chronic_combo"


class WaterQualityState(BaseModel):
    """Real-time water quality measurement."""

    date: str = Field(..., description="Date in YYYY-MM-DD format")
    turbidity: float = Field(..., ge=0, le=500, description="Turbidity in NTU (0-500)")
    flow_rate: float = Field(..., ge=0, le=100, description="Flow rate in m³/s")
    temperature: Optional[float] = Field(None, ge=0, le=50, description="Temperature in °C")
    ph: Optional[float] = Field(None, ge=0, le=14, description="pH value")
    dissolved_oxygen: Optional[float] = Field(None, ge=0, le=15, description="DO in mg/L")
    chlorophyll_a: Optional[float] = Field(None, ge=0, le=100, description="Chl-a in μg/L")
    rainfall_3d: Optional[float] = Field(None, ge=0, description="3-day cumulative rainfall (mm)")
    rainfall_7d: Optional[float] = Field(None, ge=0, description="7-day cumulative rainfall (mm)")


class KnowledgeRelation(BaseModel):
    """One retrieved knowledge-graph edge, with its own provenance.

    ``source_label`` and ``source_id`` say which graph it came from — the
    platform's own literature graph or the inherited GraphRAG export — because
    the two have very different standing and a reader is entitled to know which
    one a claim rests on.
    """

    model_config = ConfigDict(extra="ignore")

    source: str = ""
    relation: str = ""
    target: str = ""
    evidence: str = ""
    source_id: str = ""
    source_label: str = ""
    source_file: str = ""
    chunk_id: Optional[str] = None


class KnowledgeThresholdNode(BaseModel):
    """One critical level from the platform's threshold graph.

    ``r2_gain`` and ``response_jump`` are what make the level a finding rather
    than a number: the split's improvement in fit and how far the response
    moves across it. ``interpretation`` is the claim in words.
    """

    model_config = ConfigDict(extra="ignore")

    node_id: str = ""
    feature: str = ""
    label: str = ""
    threshold: Optional[float] = None
    unit: str = ""
    response: str = ""
    r2_gain: Optional[float] = None
    piecewise_r2: Optional[float] = None
    response_jump: Optional[float] = None
    interpretation: str = ""


class KnowledgeThresholds(BaseModel):
    """The mechanism-parameter critical levels the agent screens against.

    Declared here because it must not be dropped. ``KnowledgeContext`` is
    ``extra="ignore"``, so a field the platform sends but this model does not
    name is discarded in silence — the platform would send ten thresholds, the
    agent would find none, and both would look correct from their own side. That
    is the same shape as the defect this section replaced, and the reason the
    reader in ``cmfbe_agent`` reports ``threshold_source`` rather than assuming.
    """

    model_config = ConfigDict(extra="ignore")

    available: bool = False
    graph_name: str = ""
    scope: str = ""
    semantics: str = ""
    guardrails: list[str] = Field(default_factory=list)
    nodes: list[KnowledgeThresholdNode] = Field(default_factory=list)
    contextual_nodes: list[KnowledgeThresholdNode] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class KnowledgeContext(BaseModel):
    """Graph evidence retrieved by the platform for one request.

    The platform retrieves and the agent consumes; the agent never calls back
    into the platform. That keeps this service free of pandas, scikit-learn and
    networkx, and keeps the two deployments independently restartable.

    ``extra="ignore"`` is the documented contract rather than an accident:
    pydantic v2 already ignores unknown fields, so an agent running this version
    accepts a payload from a newer platform, and an older agent accepts one that
    has grown fields. Writing it down is what makes that a promise.
    """

    model_config = ConfigDict(extra="ignore")

    version: str = "1"
    query: str = ""
    scenario: str = ""
    mode: str = "none"
    source: str = "none"
    summary_text: str = ""
    relations: list[KnowledgeRelation] = Field(default_factory=list)
    paths: list[dict[str, Any]] = Field(default_factory=list)
    recommendations: list[dict[str, Any]] = Field(default_factory=list)
    citations: list[dict[str, Any]] = Field(default_factory=list)
    seeds: list[dict[str, Any]] = Field(default_factory=list)
    capabilities: dict[str, Any] = Field(default_factory=dict)
    degraded: bool = False
    notes: list[str] = Field(default_factory=list)
    #: The critical levels, which are not a retrieval result: the same ten apply
    #: whatever the question, and CMFBE screens against them. Absent means the
    #: agent screened nothing and says so — it has no local copy to fall back on,
    #: deliberately, because the copy it used to keep had gone stale.
    thresholds: Optional[KnowledgeThresholds] = None


class StrategyRequest(BaseModel):
    """Request body for strategy generation."""

    model_config = ConfigDict(extra="ignore")

    scenario: ScenarioType = Field(..., description="Water quality scenario type")
    state: WaterQualityState = Field(..., description="Current water quality state")
    episodes: int = Field(1, ge=1, le=10, description="Number of episodes to run")
    backend: str = Field("api", description="DeepSeek backend: 'api' or 'local'")
    request_id: Optional[str] = Field(None, description="Optional request tracking ID")
    #: Graph evidence the platform retrieved for this request. Absent means the
    #: knowledge base falls back to its curated scenario dictionary, exactly as
    #: it did before the graph was wired in.
    knowledge_context: Optional[KnowledgeContext] = Field(
        None, description="Retrieved knowledge-graph evidence (platform-supplied)"
    )


class StrategyResponse(BaseModel):
    """Response body for strategy generation."""

    job_id: str = Field(..., description="Unique job identifier")
    status: str = Field(..., description="Job status: 'queued', 'running', 'completed', 'failed'")
    scenario: str = Field(..., description="Scenario type")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    message: str = Field(..., description="Status message")


class StrategyResult(BaseModel):
    """Strategy generation result."""

    job_id: str
    scenario: str
    status: str
    strategy: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    agent_traces: dict[str, Any] = Field(default_factory=dict)
    reasoning_viz_path: Optional[str] = None
    report_path: Optional[str] = None
    error: Optional[str] = None
    completed_at: Optional[datetime] = None


class BatchStrategyRequest(BaseModel):
    """Request body for batch strategy generation."""

    requests: list[StrategyRequest] = Field(..., min_items=1, max_items=100)
    parallel: bool = Field(False, description="Run requests in parallel")


class HealthStatus(BaseModel):
    """Health check response."""

    status: str = Field(..., description="'healthy' or 'degraded'")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    agents: dict[str, str] = Field(default_factory=dict)
    database: str = Field("not_configured", description="'connected' or 'not_configured'")
    deepseek: str = Field("not_configured", description="'configured' or 'not_configured'")


class ScenarioInfo(BaseModel):
    """Information about a water quality scenario."""

    code: str
    name: str
    description: str
    characteristics: list[str]
    recommended_actions: list[str]


class AgentStatus(BaseModel):
    """Status of a single agent."""

    name: str
    type: str
    status: str  # 'ready', 'error', 'unavailable'
    version: Optional[str] = None
    last_used: Optional[datetime] = None


class SystemStatus(BaseModel):
    """Overall system status."""

    version: str
    status: str  # 'healthy', 'degraded', 'error'
    agents: list[AgentStatus]
    data_loader: dict[str, Any] = Field(default_factory=dict)
    deepseek_backend: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
