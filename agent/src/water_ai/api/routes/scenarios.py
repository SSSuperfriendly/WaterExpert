"""Scenario information routes."""

from __future__ import annotations

from fastapi import APIRouter

from ..schemas import ScenarioInfo

router = APIRouter(prefix="/api", tags=["scenarios"])


SCENARIOS_DATABASE = {
    "s1_external_input": ScenarioInfo(
        code="S1",
        name="External Input Type",
        description="外源输入型 - 降水增加导致通过支流输入大量悬浮物和营养盐",
        characteristics=[
            "3-day cumulative rainfall > 36 mm",
            "High upstream erosion",
            "Suspended sediment influx",
            "Turbidity spike within 24h",
        ],
        recommended_actions=[
            "Increase water release for flushing",
            "Enhanced sedimentation",
            "Monitor upstream stations",
            "Adjust flow control parameters",
        ],
    ),
    "s2_internal_release": ScenarioInfo(
        code="S2",
        name="Internal Release Type",
        description="内源释放型 - 底泥翻动释放营养盐和悬浮物",
        characteristics=[
            "High sediment resuspension intensity",
            "Benthic disturbance signals",
            "Nutrient release from sediment",
            "Gradual turbidity increase",
        ],
        recommended_actions=[
            "Precise flow control",
            "In-situ aeration",
            "Low-intensity nutrient control",
            "Sediment stabilization",
        ],
    ),
    "s3_algae_bloom": ScenarioInfo(
        code="S3",
        name="Algae Bloom Type",
        description="藻华主导型 - 叶绿素-a高且光照充足导致蓝绿藻大量繁殖",
        characteristics=[
            "Chlorophyll-a > 8 μg/L",
            "Sufficient sunlight",
            "Cyanobacteria abundance",
            "Rapid biological growth",
        ],
        recommended_actions=[
            "Aeration and oxygenation",
            "Biological treatment agents",
            "Algae harvesting",
            "Light intensity reduction",
        ],
    ),
    "s4_chronic_combo": ScenarioInfo(
        code="S4",
        name="Chronic Combination Type",
        description="慢性复合型 - 基础浊度连续升高，多因素长期叠加",
        characteristics=[
            "Baseline turbidity > 3 NTU for 7+ days",
            "Multiple simultaneous stressors",
            "Long-term accumulation",
            "Resistant to acute interventions",
        ],
        recommended_actions=[
            "Long-term low-intensity treatment",
            "Ecological restoration",
            "Infrastructure upgrades",
            "Comprehensive water quality improvement",
        ],
    ),
}


@router.get("/scenarios", response_model=list[ScenarioInfo])
async def list_scenarios() -> list[ScenarioInfo]:
    """Get all available water quality scenarios.
    
    Returns:
        List of scenario definitions
    """
    return list(SCENARIOS_DATABASE.values())


@router.get("/scenarios/{scenario_code}", response_model=ScenarioInfo)
async def get_scenario(scenario_code: str) -> ScenarioInfo:
    """Get details of a specific scenario.
    
    Args:
        scenario_code: Scenario identifier (e.g., 's1_external_input')
        
    Returns:
        Scenario information
        
    Raises:
        HTTPException: If scenario not found
    """
    if scenario_code not in SCENARIOS_DATABASE:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=404,
            detail=f"Scenario {scenario_code} not found"
        )
    
    return SCENARIOS_DATABASE[scenario_code]
