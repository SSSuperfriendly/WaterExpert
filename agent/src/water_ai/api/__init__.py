"""Water AI API module.

Note: This module requires FastAPI to be installed.
Install with: pip install fastapi uvicorn pydantic python-multipart
"""

# Lazy imports to avoid import errors if FastAPI is not installed
def __getattr__(name):
    if name == "app":
        from .main import app
        return app
    elif name == "create_app":
        from .main import create_app
        return create_app
    elif name == "StrategyRequest":
        from .schemas import StrategyRequest
        return StrategyRequest
    elif name == "StrategyResponse":
        from .schemas import StrategyResponse
        return StrategyResponse
    elif name == "StrategyResult":
        from .schemas import StrategyResult
        return StrategyResult
    elif name == "WaterQualityState":
        from .schemas import WaterQualityState
        return WaterQualityState
    elif name == "ScenarioType":
        from .schemas import ScenarioType
        return ScenarioType
    elif name == "HealthStatus":
        from .schemas import HealthStatus
        return HealthStatus
    elif name == "SystemStatus":
        from .schemas import SystemStatus
        return SystemStatus
    elif name == "JobManager":
        from .job_manager import JobManager
        return JobManager
    elif name == "JobStatus":
        from .job_manager import JobStatus
        return JobStatus
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

