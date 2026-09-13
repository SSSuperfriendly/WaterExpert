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
    # NOTE: this schema backs the *stock* fastapi-users users router only. That
    # router is NOT mounted (see ``self_service`` in main.py): exposing
    # ``role`` on a self-service PATCH would let any reviewer escalate to
    # admin. Role is immutable through self-service; it is set at provision time
    # (registration → reviewer, seed → env-configured) only.
    username: str | None = Field(default=None, min_length=1, max_length=64)
    display_name: str | None = Field(default=None, max_length=120)
    role: str | None = Field(default=None, max_length=32)


# ---------------------------------------------------------------------------
# Personal centre (self-service account management).
# ---------------------------------------------------------------------------
class ProfileRead(BaseModel):
    """The authenticated user's own profile, as served to that user only."""

    id: uuid.UUID
    username: str
    email: str
    display_name: str
    role: str
    is_active: bool
    is_verified: bool
    is_superuser: bool
    #: True when the account holds a usable (user-chosen) password. OAuth-only
    #: accounts keep an empty hash until the holder sets one; the UI switches
    #: between "设置密码" and the password-gated username/email/password edits on
    #: this flag.
    has_password: bool
    #: Linked identity providers, e.g. ``["github"]`` when the account signs in
    #: via GitHub OAuth (never the account ids themselves).
    oauth_providers: list[str] = Field(default_factory=list)


class ProfileUpdateRequest(BaseModel):
    """Update display-only fields. No password re-authentication is required
    because nothing here changes the sign-in identity or privileges."""

    display_name: str | None = Field(default=None, min_length=1, max_length=120)


class UsernameUpdateRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    current_password: str = Field(min_length=1, max_length=128)


class EmailUpdateRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    current_password: str = Field(min_length=1, max_length=128)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class SetPasswordRequest(BaseModel):
    """Give an OAuth-only account (empty hash) its first usable password.

    There is no current password to re-verify, so identity is proven instead by
    a fresh GitHub re-auth: ``reauth_token`` is the short-lived, purpose-bound
    capability the OAuth callback mints only after the signed-in account holder
    re-authorizes GitHub (see ``users.issue_reauth_token``). It cannot be used
    as a session token, and expires in five minutes.
    """

    new_password: str = Field(min_length=8, max_length=128)
    confirm_password: str = Field(min_length=8, max_length=128)
    reauth_token: str = Field(min_length=1, max_length=2048)


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


class SubgraphEntity(BaseModel):
    """One entity to draw, named the way the API names it."""

    source_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=512)


class SubgraphFocus(BaseModel):
    """The one edge the caller wants located on the canvas.

    Endpoints are not enough on their own — two relations can join the same
    pair — so ``index`` picks among the parallel edges, in the order they are
    drawn.
    """

    source_id: str = Field(min_length=1, max_length=64)
    source: str = Field(min_length=1, max_length=512)
    target: str = Field(min_length=1, max_length=512)
    index: int = Field(default=0, ge=0)


class KnowledgeGraphSubgraphRequest(BaseModel):
    """What the canvas should draw for one answer.

    The entities default to empty so that a request naming only communities, or
    only neighbours, is valid rather than a 422.
    """

    nodes: list[SubgraphEntity] = Field(default_factory=list, max_length=500)
    community_ids: list[str] = Field(default_factory=list, max_length=64)
    include_neighbours: bool = False
    focus: SubgraphFocus | None = None
    max_edges: int = Field(default=300, ge=1, le=2000)


# ---------------------------------------------------------------------------
# External deployed WaterExpert agent (docs/internal/INTEGRATION_GUIDE.md)
# ---------------------------------------------------------------------------


class AgentStateRequest(BaseModel):
    """Current water-quality state handed to the deployed strategy model.

    Bounds mirror the deployed ``WaterQualityState`` from the live ``/openapi.json``
    (verified 2026-09 against the Cloudflare-tunnelled deployment); tightening a
    field here lets a bad input fail fast at our API instead of as an opaque 502
    from upstream.
    """

    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    turbidity: float = Field(ge=0, le=500)
    flow_rate: float = Field(ge=0, le=100)
    temperature: float | None = Field(default=None, ge=0, le=50)
    ph: float | None = Field(default=None, ge=0, le=14)
    dissolved_oxygen: float | None = Field(default=None, ge=0, le=15)
    chlorophyll_a: float | None = Field(default=None, ge=0, le=100)
    rainfall_3d: float | None = Field(default=None, ge=0)
    rainfall_7d: float | None = Field(default=None, ge=0)


class AgentStrategyRequest(BaseModel):
    """Queues a strategy-generation job on the deployed model."""

    scenario: str = Field(min_length=1, max_length=64)
    state: AgentStateRequest
    episodes: int = Field(default=1, ge=1, le=10)
    backend: Literal["api", "local"] = "api"
    #: Attach retrieved knowledge-graph evidence to the request body. Off by
    #: default: a strategy run is the expensive path, and a caller that did not
    #: ask for graph evidence should not silently pay for the retrieval.
    with_knowledge: bool = False


class AgentExplainRequest(BaseModel):
    """Ask the deployed stack to explain a state under a scenario.

    Drives the guide's unlisted ``POST /api/explain`` — the narrative
    diagnosis + matched historical cases that make the lab page an answer
    rather than just a number. ``state`` carries the same bounds as strategy.
    """

    scenario: str = Field(min_length=1, max_length=64)
    state: AgentStateRequest
    #: On by default, unlike strategy: this endpoint renders the lab page's
    #: narrative, the evidence is what makes it checkable, and retrieval costs
    #: no model call.
    with_knowledge: bool = True


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
