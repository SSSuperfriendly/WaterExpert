from __future__ import annotations

import uuid
from typing import Literal

from fastapi_users import schemas as fastapi_users_schemas
from pydantic import BaseModel, Field

ReportExportFormat = Literal["html", "md", "json", "pdf"]


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class RegisterRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=128)
    confirm_password: str = Field(min_length=8, max_length=128)


class ForgotPasswordRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=1)
    password: str = Field(min_length=8, max_length=128)


class RequestVerifyRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)


class VerifyRequest(BaseModel):
    token: str = Field(min_length=1)


# ---------------------------------------------------------------------------
# fastapi-users schemas (read / create / update) with the domain fields.
# ---------------------------------------------------------------------------
class UserRead(fastapi_users_schemas.BaseUser[uuid.UUID]):
    username: str
    display_name: str
    role: str


class UserCreate(fastapi_users_schemas.BaseUserCreate):
    username: str = Field(min_length=1, max_length=64)
    display_name: str = Field(default="", max_length=120)
    role: str = Field(default="reviewer", max_length=32)


class UserUpdate(fastapi_users_schemas.BaseUserUpdate):
    username: str | None = Field(default=None, min_length=1, max_length=64)
    display_name: str | None = Field(default=None, max_length=120)
    role: str | None = Field(default=None, max_length=32)


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


class KnowledgeGraphPreprocessRequest(BaseModel):
    files: list[str] = Field(default_factory=list)
    write_json: bool = False
    keep_captions: bool = False


class KnowledgeGraphBuildRequest(BaseModel):
    files: list[str] = Field(default_factory=list)
    max_chars: int = Field(default=1200, ge=300, le=3000)


class KnowledgeGraphQARequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
