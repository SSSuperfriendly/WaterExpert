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


DataType = Literal[
    "water_quality",
    "weather",
    "hydrodynamics",
    "water_control",
    "boundary_labels",
    "spatial",
]


class DatasetImportRequest(BaseModel):
    """Import a file the operator has already placed in the managed inbox.

    ``relative_path`` is resolved inside ``settings.managed_import_root`` — the
    endpoint no longer accepts an arbitrary server path (review item 7).
    """

    data_type: DataType
    relative_path: str = Field(min_length=1, max_length=400)
    station_code: str | None = Field(default="2586", max_length=64)
    dataset_id: str | None = Field(default=None, max_length=64)
    title: str | None = Field(default=None, max_length=200)


class DatasetArchiveRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class PredictionJobCreateRequest(BaseModel):
    # `mode` was removed in the 2026-08 delivery patch: "inference" and
    # "full_pipeline" both ran the identical pipeline, so the choice was a
    # control that did nothing. Every job is now one run of the pipeline.
    model_name: Literal["mscim", "mscim_no_kg", "cmfbe_stgcn"] = "cmfbe_stgcn"
    station_code: str = "2586"
    config_path: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    use_existing_artifacts: bool = True
    #: Bind this run to an analysis case, so its results are attributable.
    case_id: str | None = Field(default=None, max_length=64)
    #: Queue priority, higher first (task centre, review item 10).
    priority: int = Field(default=5, ge=0, le=10)


class CaseCreateRequest(BaseModel):
    """Open an analysis case (review item 4).

    A case is the unit every result is attributed to: it names the data that
    went in, the run that produced the artifacts, and the reports that cite it.
    """

    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    station_code: str | None = Field(default="2586", max_length=64)
    target_date: str | None = Field(default=None, max_length=32)
    dataset_version_ids: list[str] = Field(default_factory=list)


class CaseUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    target_date: str | None = Field(default=None, max_length=32)


class CaseRunRequest(BaseModel):
    """Launch the case's prediction run.

    The station and date window default to the case's own, so the caller does
    not restate what the case already records.
    """

    model_name: Literal["mscim", "mscim_no_kg", "cmfbe_stgcn"] = "cmfbe_stgcn"
    start_date: str | None = None
    end_date: str | None = None
    config_path: str | None = None
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


# ---------------------------------------------------------------------------
# Model registry (review item 11)
# ---------------------------------------------------------------------------


class ModelRegisterRequest(BaseModel):
    model_key: str = Field(min_length=1, max_length=64)
    version: str = Field(min_length=1, max_length=32)
    station_code: str | None = Field(default=None, max_length=64)
    training_dataset_version_id: str | None = None
    config_hash: str | None = None
    metrics: dict = Field(default_factory=dict)
    notes: str | None = Field(default=None, max_length=2000)


class ModelTransitionRequest(BaseModel):
    to_stage: Literal["experiment", "candidate", "in_review", "published", "retired"]


# ---------------------------------------------------------------------------
# Report centre (review item 21)
# ---------------------------------------------------------------------------


class ReportCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    project_name: str | None = Field(default=None, max_length=200)
    case_id: str | None = None
    format: ReportExportFormat = "html"
    time_range_start: str | None = None
    time_range_end: str | None = None
    content_selection: list[str] = Field(default_factory=list)


class ReportUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    project_name: str | None = Field(default=None, max_length=200)
    time_range_start: str | None = None
    time_range_end: str | None = None
    content_selection: list[str] | None = None


class ReportReviewRequest(BaseModel):
    approve: bool
    comment: str | None = Field(default=None, max_length=2000)


# ---------------------------------------------------------------------------
# Event handling (review item 27)
# ---------------------------------------------------------------------------


class EventCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=4000)
    severity: Literal["info", "low", "medium", "high", "critical"] = "medium"
    case_id: str | None = None
    target_date: str | None = None
    source: str = Field(default="manual", max_length=64)


class EventTransitionRequest(BaseModel):
    to_stage: Literal[
        "open", "assigned", "acknowledged", "handling", "reviewing", "closed", "false_positive"
    ]
    note: str | None = Field(default=None, max_length=2000)
    assignee: str | None = Field(default=None, max_length=128)


class EventCloseRequest(BaseModel):
    post_mortem: str = Field(min_length=1, max_length=4000)
    note: str | None = Field(default=None, max_length=2000)


class EventFalsePositiveRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class EventEscalateRequest(BaseModel):
    note: str | None = Field(default=None, max_length=2000)
