"""Pydantic data models for Water AI API."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


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


class StrategyRequest(BaseModel):
    """Request body for strategy generation."""

    scenario: ScenarioType = Field(..., description="Water quality scenario type")
    state: WaterQualityState = Field(..., description="Current water quality state")
    episodes: int = Field(1, ge=1, le=10, description="Number of episodes to run")
    backend: str = Field("api", description="DeepSeek backend: 'api' or 'local'")
    request_id: Optional[str] = Field(None, description="Optional request tracking ID")


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
