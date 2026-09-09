"""Health check and system status routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from datetime import datetime
import os

from ...agents import (
    MSCIMAgent,
    CMFBEAgent,
    KnowledgeBaseAgent,
    AquaTurbGPTAgent,
    RLTGRRAgent,
    SafetyAgent,
)
from ...data.loader import WaterQualityDataLoader
from ..schemas import HealthStatus, SystemStatus, AgentStatus

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=HealthStatus)
async def health_check() -> HealthStatus:
    """Check API and system health.
    
    Returns:
        Health status with component details
    """
    agents_status = {}
    
    # Check each agent
    for agent_name, agent_class in [
        ("MSCIM", MSCIMAgent),
        ("CMFBE", CMFBEAgent),
        ("KnowledgeBase", KnowledgeBaseAgent),
        ("AquaTurbGPT", AquaTurbGPTAgent),
        ("RL-TGRR", RLTGRRAgent),
        ("Safety", SafetyAgent),
    ]:
        try:
            agent = agent_class()
            status = agent.health() if hasattr(agent, "health") else {"status": "ready"}
            agents_status[agent_name] = status.get("status", "ready")
        except Exception as e:
            agents_status[agent_name] = f"error: {str(e)}"
    
    # Check data loader
    try:
        loader = WaterQualityDataLoader()
        data_status = "ready"
    except Exception as e:
        data_status = f"error: {str(e)}"
    
    # Check DeepSeek configuration
    deepseek_status = "configured" if os.getenv("DEEPSEEK_API_KEY") else "not_configured"
    
    # Overall status
    overall_status = "healthy" if all(
        status == "ready" for status in agents_status.values()
    ) else "degraded"
    
    return HealthStatus(
        status=overall_status,
        agents=agents_status,
        database="not_configured",  # TODO: Add DB support
        deepseek=deepseek_status,
    )


@router.get("/status", response_model=SystemStatus)
async def system_status() -> SystemStatus:
    """Get detailed system status.
    
    Returns:
        Comprehensive system status
    """
    # Collect agent statuses
    agent_statuses = []
    for agent_name, agent_class in [
        ("MSCIM", MSCIMAgent),
        ("CMFBE", CMFBEAgent),
        ("KnowledgeBase", KnowledgeBaseAgent),
        ("AquaTurbGPT", AquaTurbGPTAgent),
        ("RL-TGRR", RLTGRRAgent),
        ("Safety", SafetyAgent),
    ]:
        try:
            agent = agent_class()
            agent_statuses.append(
                AgentStatus(
                    name=agent_name,
                    type="specialist",
                    status="ready",
                )
            )
        except Exception as e:
            agent_statuses.append(
                AgentStatus(
                    name=agent_name,
                    type="specialist",
                    status="error",
                )
            )
    
    # Data loader info
    data_loader_info = {}
    try:
        loader = WaterQualityDataLoader()
        data_loader_info = {
            "status": "ready",
            "total_rows": loader.get_total_rows(),
            "date_range": {
                "start": loader.get_date_range()[0],
                "end": loader.get_date_range()[1],
            }
        }
    except Exception as e:
        data_loader_info = {"status": "error", "message": str(e)}
    
    deepseek_backend = "api" if os.getenv("DEEPSEEK_API_KEY") else "mock"
    
    return SystemStatus(
        version="1.0.0",
        status="healthy",
        agents=agent_statuses,
        data_loader=data_loader_info,
        deepseek_backend=deepseek_backend,
    )
