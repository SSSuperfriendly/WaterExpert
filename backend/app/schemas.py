from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class DataImportRequest(BaseModel):
    data_type: Literal[
        "water_quality",
        "weather",
        "hydrodynamics",
        "water_control",
        "boundary_labels",
        "spatial",
    ]
    source_name: str = Field(min_length=1, max_length=120)
    file_path: str = Field(min_length=1)
    time_granularity: str = Field(default="daily", min_length=1, max_length=32)
    station_code: str | None = Field(default="2586")


class PredictionJobCreateRequest(BaseModel):
    mode: Literal["inference", "full_pipeline"] = "inference"
    model_name: Literal["mscim", "mscim_no_kg", "cmfbe_stgcn"] = "cmfbe_stgcn"
    station_code: str = "2586"
    config_path: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    use_existing_artifacts: bool = True

