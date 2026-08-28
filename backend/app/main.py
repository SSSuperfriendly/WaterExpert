from __future__ import annotations

import os
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.staticfiles import StaticFiles
from fastapi_users import exceptions as user_exceptions

from backend.app.config import get_settings
from backend.app.db import Base, engine
from backend.app.domain.codes import ErrorCode
from backend.app.domain.roles import Permission
from backend.app.schemas import (
    CaseCreateRequest,
    CaseRunRequest,
    CaseUpdateRequest,
    DatasetImportRequest,
    EventCloseRequest,
    EventCreateRequest,
    EventEscalateRequest,
    EventFalsePositiveRequest,
    EventTransitionRequest,
    KnowledgeGraphBuildRequest,
    KnowledgeGraphPreprocessRequest,
    KnowledgeGraphQARequest,
    LoginRequest,
    ModelRegisterRequest,
    ModelTransitionRequest,
    PredictionJobCreateRequest,
    RegisterRequest,
    ReportCreateRequest,
    ReportExportFormat,
    ReportReviewRequest,
    ReportUpdateRequest,
    UserCreate,
    UserRead,
    UserUpdate,
)
from backend.app.services.artifact_repository import ArtifactReadError, ArtifactRepository
from backend.app.services.case_service import CaseNotFound, CaseService
from backend.app.services.cross_modal_repository import CrossModalRepository
from backend.app.services.data_explorer import DataExplorerService
from backend.app.services.dataset_service import DatasetNotFound, DatasetService
from backend.app.services.event_service import EventNotFound, EventService
from backend.app.services.health import HealthService
from backend.app.services.kg_service import KnowledgeGraphService
from backend.app.services.model_service import ModelNotFound, ModelService
from backend.app.services.realtime_validation import RealtimeValidationService
from backend.app.services.report_builder import get_report_media_type, write_report
from backend.app.services.report_service import ReportNotFound, ReportService
from backend.app.services.runtime_jobs import JobParameterError, RuntimeJobService
from backend.app.services.security import AuditLogger, PermissionDenied, require_permission
from backend.app.services.state_store import SqliteStateStore
from backend.app.services.task_progress import task_view
from backend.app.services.upload_guard import UploadRejected
from backend.app.users import (
    SECRET,
    UserManager,
    authenticate_token,
    auth_backend,
    demo_credentials,
    fastapi_users,
    get_jwt_strategy,
    get_user_manager,
    seed_demo_user,
)


settings = get_settings()
repository = ArtifactRepository(settings)
store = SqliteStateStore(settings.state_root)
runtime_jobs = RuntimeJobService(settings, repository, store)
dataset_service = DatasetService(settings, store)
case_service = CaseService(settings, store, dataset_service)
model_service = ModelService(store)
report_service = ReportService(settings, store)
event_service = EventService(settings, store)
audit_logger = AuditLogger(store)
health_service = HealthService(settings, store, runtime_jobs, model_service, dataset_service)
data_explorer = DataExplorerService(settings)
realtime_validation_service = RealtimeValidationService(settings)
cross_modal_repository = CrossModalRepository(settings)
kg_service = KnowledgeGraphService(settings)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _requires_auth(path: str) -> bool:
    """Whether ``path`` is a protected API route (auth gate applies).

    Review item 7: report downloads, knowledge-graph files and cross-modal media
    used to be exempt, so a token was never required to fetch them. Only the
    ``/api/v1/auth/`` bootstrap is public now; everything else is protected.
    """
    if not path.startswith("/api/"):
        return False
    return not path.startswith("/api/v1/auth/")


async def auth_guard(request: Request) -> None:
    """Global dependency: enforce a valid bearer token on protected API routes.

    On success the resolved user is left on ``request.state.actor_user`` so the
    RBAC dependency and audit middleware do not re-decode the token.
    """
    if not _requires_auth(request.url.path):
        return
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        raise error_response(ErrorCode.NOT_AUTHENTICATED, "Not authenticated.", 401)
    token = authorization[7:].strip()
    user = await authenticate_token(token)
    if user is None:
        raise error_response(ErrorCode.TOKEN_INVALID, "Invalid or expired token.", 401)
    request.state.actor_user = user


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await seed_demo_user()
    yield


app = FastAPI(
    title=settings.app_name,
    description="Integrated software product with embedded WaterExpert algorithm runtime.",
    version="0.3.0",
    lifespan=lifespan,
    dependencies=[Depends(auth_guard)],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _client_ip(request: Request) -> str | None:
    """Best-effort client address for an audit row."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


@app.middleware("http")
async def audit_refusals(request: Request, call_next):
    """Record authentication/authorization refusals (review item 7).

    Successful privileged actions are audited at their route; this middleware
    only captures the failures — a token that did not authenticate, a permission
    that was denied — so a probing session is visible even though it changed
    nothing.
    """
    response = await call_next(request)
    if request.url.path.startswith("/api/") and response.status_code in (401, 403):
        actor = "anonymous"
        authorization = request.headers.get("Authorization", "")
        if authorization.startswith("Bearer "):
            user = await authenticate_token(authorization[7:].strip())
            if user is not None:
                actor = str(
                    getattr(user, "email", None)
                    or getattr(user, "username", None)
                    or "unknown"
                )
        outcome = "unauthorized" if response.status_code == 401 else "denied"
        audit_logger.record(
            actor=actor,
            action=f"{request.method} {request.url.path}",
            object_type="http",
            object_id=request.url.path,
            outcome=outcome,
            ip=_client_ip(request),
        )
    return response


app.mount("/ui", StaticFiles(directory=settings.frontend_root, html=True), name="ui")


def _frontend_error_page(filename: str, status_code: int) -> FileResponse:
    path = settings.frontend_root / filename
    return FileResponse(path, media_type="text/html; charset=utf-8", status_code=status_code)


def artifact_error_to_http(exc: Exception) -> HTTPException:
    if isinstance(exc, FileNotFoundError):
        return HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, ArtifactReadError):
        return HTTPException(status_code=500, detail=str(exc))
    return HTTPException(status_code=500, detail="Unexpected application error.")


def error_response(code: ErrorCode, detail: str, status_code: int) -> HTTPException:
    """A refusal the frontend can localise.

    ``code`` is stable and drives the UI's message catalogue; ``detail`` stays
    English for operators and logs (review item 22).
    """
    return HTTPException(status_code=status_code, detail={"code": str(code), "detail": detail})


#: HTTP status for each way a request can be refused.
_ERROR_STATUS: dict[ErrorCode, int] = {
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.PERMISSION_DENIED: 403,
    ErrorCode.PATH_NOT_ALLOWED: 403,
    ErrorCode.FILE_TOO_LARGE: 413,
    ErrorCode.INVALID_STATE_TRANSITION: 409,
    ErrorCode.CASE_REQUIRED: 409,
    ErrorCode.CASE_NOT_READY: 409,
    ErrorCode.RESULT_STALE: 409,
    ErrorCode.JOB_NOT_CANCELLABLE: 409,
    ErrorCode.MODEL_NOT_PUBLISHED: 403,
    ErrorCode.REPORT_NOT_APPROVED: 409,
    ErrorCode.ARTIFACT_UNAVAILABLE: 503,
}


def run_service_call(operation):
    """Run a domain-service call, mapping its refusals to HTTP status codes."""
    try:
        return operation()
    except HTTPException:
        raise
    except DatasetNotFound as exc:
        raise error_response(ErrorCode.NOT_FOUND, f"Dataset {exc} was not found.", 404) from exc
    except CaseNotFound as exc:
        raise error_response(ErrorCode.NOT_FOUND, f"Case {exc} was not found.", 404) from exc
    except ModelNotFound as exc:
        raise error_response(ErrorCode.NOT_FOUND, f"Model {exc} was not found.", 404) from exc
    except ReportNotFound as exc:
        raise error_response(ErrorCode.NOT_FOUND, f"Report {exc} was not found.", 404) from exc
    except EventNotFound as exc:
        raise error_response(ErrorCode.NOT_FOUND, f"Event {exc} was not found.", 404) from exc
    except UploadRejected as exc:
        raise error_response(exc.code, exc.detail, _ERROR_STATUS.get(exc.code, 400)) from exc
    except JobParameterError as exc:
        raise error_response(exc.code, exc.detail, _ERROR_STATUS.get(exc.code, 400)) from exc
    except ValueError as exc:
        raise error_response(ErrorCode.VALIDATION_FAILED, str(exc), 400) from exc


async def current_actor(request: Request) -> str:
    """Who is making this request, for ownership and audit records.

    The global :func:`auth_guard` has already rejected an unauthenticated call
    by the time a route runs, so a token here is always valid; the fallback
    covers routes reached in tests with the guard disabled.
    """
    authorization = request.headers.get("Authorization", "")
    if authorization.startswith("Bearer "):
        user = await authenticate_token(authorization[7:].strip())
        if user is not None:
            return str(getattr(user, "email", None) or getattr(user, "id", "unknown"))
    return "unknown"


def run_repository_call(operation, *, bad_request_errors: tuple[type[Exception], ...] = ()):
    try:
        return operation()
    except HTTPException:
        raise
    except bad_request_errors as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise artifact_error_to_http(exc) from exc


def job_repository(job_id: str, *, require_completed: bool = True) -> ArtifactRepository:
    try:
        return runtime_jobs.get_job_repository(job_id, require_completed=require_completed)
    except KeyError as exc:
        raise error_response(ErrorCode.NOT_FOUND, f"Prediction job {job_id} not found.", 404) from exc
    except RuntimeError as exc:
        raise error_response(ErrorCode.CASE_NOT_READY, str(exc), 409) from exc


def job_provenance(job_id: str) -> dict:
    """Version stamp for a bare ``?job_id=`` read.

    A job that belongs to a case reports the case's full provenance; one that
    does not still reports its own run id rather than nothing.
    """
    case = case_service.case_for_job(job_id)
    if case is not None:
        return case_service.provenance(str(case["case_id"]))
    record = store.get_job(job_id) or {}
    return {
        "case_id": None,
        "run_id": job_id,
        "job_id": job_id,
        "generated_at": record.get("finished_at") or record.get("updated_at"),
        "model_version": record.get("model_name"),
        "config_hash": None,
        "is_stale": False,
        "stale_reason": None,
        "scope": "job",
    }


def resolve_artifacts(
    *,
    case_id: str | None = None,
    job_id: str | None = None,
    scope: str | None = None,
) -> tuple[ArtifactRepository, dict]:
    """Pick the artifacts a result request is asking about, and say which they are.

    Review item 5: this used to fall back to the repository's *integrated*
    artifacts whenever no ``job_id`` was given, so a page could present the
    checked-in research outputs as if they were the run the user had just
    launched. That fallback is gone. A caller now either names a case, names a
    job, or asks for ``scope=integrated`` explicitly and gets a payload that
    says so.
    """
    if scope == "integrated":
        return repository, CaseService.integrated_provenance()
    if scope not in (None, "", "case"):
        raise error_response(
            ErrorCode.VALIDATION_FAILED,
            f"Unknown artifact scope '{scope}'. Use 'case' or 'integrated'.",
            400,
        )

    if case_id:
        case = run_service_call(lambda: case_service.assert_readable(case_id))
        bound_job = case.get("job_id")
        if not bound_job:
            raise error_response(
                ErrorCode.ARTIFACT_UNAVAILABLE,
                f"Case {case_id} has no completed run; start one before reading results.",
                409,
            )
        return job_repository(str(bound_job)), case_service.provenance(case_id)

    if job_id:
        return job_repository(job_id), job_provenance(job_id)

    raise error_response(
        ErrorCode.CASE_REQUIRED,
        "This endpoint returns the results of a specific analysis case. "
        "Pass case_id (or job_id), or scope=integrated for the shared research artifacts.",
        409,
    )


def artifact_payload(
    read,
    *,
    case_id: str | None = None,
    job_id: str | None = None,
    scope: str | None = None,
    bad_request_errors: tuple[type[Exception], ...] = (),
) -> dict:
    """Read one artifact and stamp it with the run it came from.

    Every result payload carries the same ``provenance`` block, so two pages
    showing the same number can be checked for agreement instead of assumed to
    agree (review item 5).
    """
    artifacts, provenance = resolve_artifacts(case_id=case_id, job_id=job_id, scope=scope)
    payload = run_repository_call(
        lambda: read(artifacts), bad_request_errors=bad_request_errors
    )
    return {**payload, "provenance": provenance}


@app.get("/", include_in_schema=False)
def index() -> RedirectResponse:
    return RedirectResponse(url="/ui/login")


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(status_code=204)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> Response:
    if request.url.path.startswith("/api/"):
        # A structured `{code, detail}` refusal is passed through intact —
        # `str()` on it would flatten a Python dict repr into the response and
        # cost the frontend the stable code it localises with.
        detail = exc.detail if isinstance(exc.detail, dict) else str(exc.detail)
        return JSONResponse({"detail": detail}, status_code=exc.status_code)
    accepts_html = "text/html" in request.headers.get("accept", "")
    if accepts_html and exc.status_code == 404:
        return _frontend_error_page("404.html", 404)
    return Response(
        content=str(exc.detail),
        status_code=exc.status_code,
        media_type="text/plain; charset=utf-8",
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> Response:
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": "Internal server error."}, status_code=500)
    accepts_html = "text/html" in request.headers.get("accept", "")
    if accepts_html:
        return _frontend_error_page("500.html", 500)
    return Response(
        content="Internal server error.",
        status_code=500,
        media_type="text/plain; charset=utf-8",
    )


@app.get("/healthz")
def healthz() -> dict:
    """Liveness: is the process alive? No external dependencies are checked."""
    return health_service.liveness()


@app.get("/readyz")
def readyz(response: Response) -> dict:
    """Readiness: can we serve traffic? Fails on an unreadable state DB or a
    disk that has dropped below the free-space floor."""
    payload = health_service.readiness()
    if payload["status"] != "ready":
        response.status_code = 503
    return payload


@app.get("/api/v1/health/dependencies")
def health_dependencies(response: Response) -> dict:
    """Deep dependency check: state DB, executor, disk, and state directories."""
    payload = health_service.dependencies()
    if payload["status"] != "ok":
        response.status_code = 503
    return payload


@app.get("/api/v1/health/model")
def health_model(response: Response) -> dict:
    """Is a published model serving predictions right now?"""
    payload = health_service.model()
    if payload["status"] != "ok":
        response.status_code = 503
    return payload


@app.get("/api/v1/health/data")
def health_data() -> dict:
    """Data freshness: how recent is the latest accepted dataset version?"""
    return health_service.data()


@app.post("/api/v1/admin/maintenance/cleanup")
def run_maintenance_cleanup(
    actor: str = Depends(current_actor),
    _: None = Depends(require_permission(Permission.MAINTENANCE)),
) -> dict:
    """Run every retention purge in one place (review item 26)."""
    jobs = runtime_jobs.purge_expired_jobs()
    datasets = dataset_service.purge_expired()
    reports = report_service.purge_expired()
    audit_logger.record(
        actor=actor,
        action="maintenance:cleanup",
        object_type="system",
        object_id="cleanup",
    )
    return {"jobs": jobs, "datasets": datasets, "reports": reports}


@app.post("/api/v1/auth/login")
async def login(
    payload: LoginRequest,
    user_manager: UserManager = Depends(get_user_manager),
) -> dict:
    user = await user_manager.authenticate_identifier(payload.username, payload.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="User account is inactive.")
    access_token = await get_jwt_strategy().write_token(user)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "username": user.username,
        "display_name": user.display_name or user.username,
        "role": user.role,
    }


@app.get("/api/v1/auth/hint")
def auth_hint() -> dict[str, str]:
    """Demo credentials, gated off by default (review item 7).

    Only served when ``WATEREXPERT_ENABLE_DEMO_HINT=1``; otherwise the bootstrap
    login page has no way to discover the account from the network.
    """
    if not settings.expose_demo_hint:
        raise error_response(ErrorCode.NOT_FOUND, "Demo credentials are not exposed.", 404)
    return demo_credentials()


@app.post("/api/v1/auth/register")
async def register(
    payload: RegisterRequest,
    user_manager: UserManager = Depends(get_user_manager),
) -> dict:
    if payload.password != payload.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match.")
    username = payload.username.strip()
    email = payload.email.strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username is required.")
    if not _EMAIL_RE.fullmatch(email):
        raise HTTPException(status_code=400, detail="Invalid email address.")
    try:
        user = await user_manager.create(
            UserCreate(
                username=username,
                email=email,
                password=payload.password,
                display_name=username,
                role="reviewer",
            ),
            safe=True,
        )
    except user_exceptions.UserAlreadyExists:
        raise HTTPException(
            status_code=409, detail="Username or email is already registered."
        )
    access_token = await get_jwt_strategy().write_token(user)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "username": user.username,
        "display_name": user.display_name or user.username,
        "role": user.role,
    }


# fastapi-users routers: password reset, email verification, user management.
app.include_router(
    fastapi_users.get_reset_password_router(),
    prefix="/api/v1/auth",
    tags=["auth"],
)
app.include_router(
    fastapi_users.get_verify_router(UserRead),
    prefix="/api/v1/auth",
    tags=["auth"],
)
app.include_router(
    fastapi_users.get_users_router(UserRead, UserUpdate),
    prefix="/api/v1/users",
    tags=["users"],
)

# GitHub OAuth (mounted only when credentials are configured).
github_client_id = os.environ.get("WATEREXPERT_GITHUB_CLIENT_ID")
github_client_secret = os.environ.get("WATEREXPERT_GITHUB_CLIENT_SECRET")
if github_client_id and github_client_secret:
    from httpx_oauth.clients.github import GitHubOAuth2

    github_client = GitHubOAuth2(github_client_id, github_client_secret)
    app.include_router(
        fastapi_users.get_oauth_router(
            github_client,
            auth_backend,
            SECRET,
            associate_by_email=True,
            is_verified_by_default=True,
        ),
        prefix="/api/v1/auth/oauth/github",
        tags=["auth"],
    )


@app.get("/api/v1/meta")
def meta(
    case_id: str | None = Query(default=None),
    job_id: str | None = Query(default=None),
) -> dict:
    """Describes the deployment, not a conclusion.

    Unlike the result endpoints this keeps working with no case bound — the app
    shell needs the station profile and guardrails before a case exists — but it
    reports the scope it answered from so the caller is never guessing.
    """
    if case_id or job_id:
        return artifact_payload(lambda artifacts: artifacts.metadata(), case_id=case_id, job_id=job_id)
    return artifact_payload(lambda artifacts: artifacts.metadata(), scope="integrated")


@app.get("/api/v1/stations")
def stations() -> list[dict]:
    return run_repository_call(repository.stations)


# -- data asset centre -------------------------------------------------------
# `/api/v1/data/upload` and `/api/v1/data/import` were two entry points that did
# the same thing (copy a file, count rows, log a row) with no field mapping, no
# unit conversion and no quality gate. Both are replaced by this family, where
# every file goes through the same acceptance chain and a version is only
# modelable once it passes (review items 3, 8, 9).


@app.post("/api/v1/datasets", status_code=201)
def create_dataset_version(
    data_type: str = Form(...),
    station_code: str = Form(default="2586"),
    dataset_id: str | None = Form(default=None),
    title: str | None = Form(default=None),
    file: UploadFile = File(...),
    actor: str = Depends(current_actor),
) -> dict:
    return run_service_call(
        lambda: dataset_service.ingest_upload(
            source=file.file,
            filename=file.filename,
            data_type=data_type,
            station_code=station_code,
            owner=actor,
            dataset_id=dataset_id,
            title=title,
        )
    )


@app.post("/api/v1/datasets/import", status_code=201)
def import_dataset_version(
    payload: DatasetImportRequest,
    actor: str = Depends(current_actor),
) -> dict:
    return run_service_call(
        lambda: dataset_service.ingest_managed_path(
            relative_path=payload.relative_path,
            data_type=payload.data_type,
            station_code=payload.station_code,
            owner=actor,
            dataset_id=payload.dataset_id,
            title=payload.title,
        )
    )


@app.get("/api/v1/datasets")
def list_datasets(
    data_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
) -> list[dict]:
    return run_service_call(
        lambda: dataset_service.list_datasets(data_type=data_type, status=status)
    )


@app.get("/api/v1/datasets/freshness")
def dataset_freshness() -> dict:
    return run_service_call(dataset_service.freshness_summary)


@app.get("/api/v1/datasets/quality-alerts")
def dataset_quality_alerts(limit: int = Query(default=10, ge=1, le=100)) -> list[dict]:
    return run_service_call(lambda: dataset_service.quality_alerts(limit=limit))


@app.get("/api/v1/datasets/field-dictionary/{data_type}")
def dataset_field_dictionary(data_type: str) -> dict:
    return run_service_call(lambda: dataset_service.field_dictionary(data_type))


@app.get("/api/v1/datasets/{dataset_id}")
def get_dataset(dataset_id: str) -> dict:
    return run_service_call(lambda: dataset_service.get_dataset(dataset_id))


@app.delete("/api/v1/datasets/{dataset_id}")
def delete_dataset(
    dataset_id: str,
    actor: str = Depends(current_actor),
    _: None = Depends(require_permission(Permission.DATA_DELETE)),
) -> dict:
    def operation() -> dict:
        result = dataset_service.delete_dataset(dataset_id, actor=actor)
        audit_logger.record(actor=actor, action="dataset:delete", object_type="dataset", object_id=dataset_id)
        return result

    return run_service_call(operation)


@app.post("/api/v1/datasets/{dataset_id}/archive")
def archive_dataset(
    dataset_id: str,
    actor: str = Depends(current_actor),
    _: None = Depends(require_permission(Permission.DATA_DELETE)),
) -> dict:
    def operation() -> dict:
        result = dataset_service.archive_dataset(dataset_id, actor=actor)
        audit_logger.record(actor=actor, action="dataset:archive", object_type="dataset", object_id=dataset_id)
        return result

    return run_service_call(operation)


@app.get("/api/v1/datasets/{dataset_id}/versions")
def list_dataset_versions(dataset_id: str) -> list[dict]:
    return run_service_call(lambda: dataset_service.list_versions(dataset_id))


@app.get("/api/v1/dataset-versions/{version_id}")
def get_dataset_version(version_id: str) -> dict:
    return run_service_call(lambda: dataset_service.get_version(version_id))


@app.get("/api/v1/dataset-versions/{version_id}/quality")
def get_dataset_version_quality(version_id: str) -> dict:
    return run_service_call(lambda: dataset_service.quality_report(version_id))


@app.get("/api/v1/dataset-versions/{version_id}/preview")
def get_dataset_version_preview(
    version_id: str, limit: int = Query(default=50, ge=1, le=500)
) -> dict:
    return run_service_call(lambda: dataset_service.preview(version_id, limit=limit))


@app.get("/api/v1/dataset-versions/{version_id}/lineage")
def get_dataset_version_lineage(version_id: str) -> dict:
    return run_service_call(lambda: dataset_service.lineage(version_id))


@app.get("/api/v1/database/summary")
def database_summary() -> dict:
    return run_repository_call(data_explorer.database_summary)


@app.get("/api/v1/database/stations")
def database_stations() -> list[dict]:
    return run_repository_call(data_explorer.database_stations)


@app.get("/api/v1/database/query")
def database_query(
    station_code: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict:
    return run_repository_call(
        lambda: data_explorer.query_records(
            station_code=station_code,
            keyword=keyword,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offset=offset,
        )
    )


@app.get("/api/v1/preprocess/summary")
def preprocess_summary(station_code: str = Query(default="2586")) -> dict:
    return run_repository_call(lambda: data_explorer.preprocessing_summary(station_code))


@app.get("/api/v1/visualization/summary")
def visualization_summary(
    station_code: str = Query(default="2586"),
    indicator: str = Query(default="turbidity"),
    limit: int = Query(default=180, ge=30, le=720),
) -> dict:
    return run_repository_call(
        lambda: data_explorer.visualization_payload(
            station_code=station_code,
            indicator=indicator,
            limit=limit,
        )
    )


def modelable_coverage(station_code: str | None) -> tuple[str, str] | None:
    """The window covered by every modelable dataset for this station.

    Returns ``None`` when no modelable dataset is registered yet, in which case
    the date range is left unchecked rather than refusing every job — the
    pipeline still clips to whatever the configured files contain.
    """
    versions = dataset_service.modelable_versions(station_code=station_code)
    if not versions:
        return None
    start, end = dataset_service.coverage_window(
        [str(version["version_id"]) for version in versions]
    )
    return (start, end) if start and end else None


def launch_job(
    payload: PredictionJobCreateRequest,
    *,
    coverage: tuple[str, str] | None = None,
) -> dict:
    """Submit a run, refusing anything the data cannot support.

    A job carrying a ``case_id`` is bound to that case here, and the case's
    status follows the run from this point on.
    """
    if coverage is None:
        coverage = modelable_coverage(payload.station_code)
    job = run_service_call(
        lambda: runtime_jobs.create_prediction_job(payload, coverage=coverage)
    )
    if payload.case_id:
        run_service_call(lambda: case_service.attach_job(payload.case_id, job))
        run_service_call(lambda: case_service.sync_from_job(payload.case_id, job))
    return job


@app.post("/api/v1/prediction-jobs")
def create_prediction_job(
    payload: PredictionJobCreateRequest,
    actor: str = Depends(current_actor),
    _: None = Depends(require_permission(Permission.JOB_START)),
) -> dict:
    try:
        job = launch_job(payload)
        audit_logger.record(
            actor=actor, action="job:start", object_type="job", object_id=str(job.get("job_id"))
        )
        return job
    except FileNotFoundError as exc:
        raise error_response(ErrorCode.NOT_FOUND, str(exc), 400) from exc


@app.get("/api/v1/prediction-jobs")
def list_prediction_jobs() -> list[dict]:
    return runtime_jobs.list_jobs()


@app.get("/api/v1/prediction-jobs/queue")
def job_queue_snapshot() -> dict:
    return runtime_jobs.queue_snapshot()


@app.get("/api/v1/prediction-jobs/{job_id}")
def get_prediction_job(job_id: str) -> dict:
    try:
        job = runtime_jobs.refresh_job(job_id)
    except KeyError as exc:
        raise error_response(ErrorCode.NOT_FOUND, f"Prediction job {job_id} not found.", 404) from exc
    # Polling this endpoint is how the UI learns a run finished, so it is also
    # where the case learns: otherwise a case would sit at `running` until
    # something else happened to look at it.
    if job.get("case_id"):
        run_service_call(lambda: case_service.sync_from_job(str(job["case_id"]), job))
    return task_view(job)


@app.get("/api/v1/prediction-jobs/{job_id}/series")
def get_prediction_job_series(job_id: str) -> dict:
    try:
        return runtime_jobs.get_job_series(job_id)
    except KeyError as exc:
        raise error_response(ErrorCode.NOT_FOUND, f"Prediction job {job_id} not found.", 404) from exc
    except RuntimeError as exc:
        raise error_response(ErrorCode.CASE_NOT_READY, str(exc), 409) from exc


@app.post("/api/v1/prediction-jobs/{job_id}/cancel")
def cancel_prediction_job(
    job_id: str,
    actor: str = Depends(current_actor),
    _: None = Depends(require_permission(Permission.JOB_CANCEL)),
) -> dict:
    try:
        result = runtime_jobs.cancel_job(job_id)
        audit_logger.record(actor=actor, action="job:cancel", object_type="job", object_id=job_id)
        return result
    except KeyError as exc:
        raise error_response(ErrorCode.NOT_FOUND, f"Prediction job {job_id} not found.", 404) from exc
    except JobParameterError as exc:
        raise error_response(exc.code, exc.detail, _ERROR_STATUS.get(exc.code, 409)) from exc


@app.post("/api/v1/prediction-jobs/{job_id}/retry", status_code=201)
def retry_prediction_job(
    job_id: str,
    actor: str = Depends(current_actor),
    _: None = Depends(require_permission(Permission.JOB_START)),
) -> dict:
    try:
        result = runtime_jobs.retry_job(job_id)
        audit_logger.record(actor=actor, action="job:retry", object_type="job", object_id=job_id)
        return result
    except KeyError as exc:
        raise error_response(ErrorCode.NOT_FOUND, f"Prediction job {job_id} not found.", 404) from exc
    except JobParameterError as exc:
        raise error_response(exc.code, exc.detail, _ERROR_STATUS.get(exc.code, 400)) from exc


@app.get("/api/v1/prediction-jobs/{job_id}/artifacts")
def get_prediction_job_artifacts(job_id: str) -> list[dict]:
    try:
        return runtime_jobs.job_artifacts(job_id)
    except KeyError as exc:
        raise error_response(ErrorCode.NOT_FOUND, f"Prediction job {job_id} not found.", 404) from exc


@app.get("/api/v1/prediction-jobs/{job_id}/logs/{stream}")
def download_job_log(job_id: str, stream: str) -> FileResponse:
    """Download a run's stdout or stderr log.

    The task centre needs the full log to classify a failure; ``stream`` is
    fixed to ``stdout``/``stderr`` rather than taking a path.
    """
    try:
        path = runtime_jobs.log_path(job_id, stream)
    except KeyError as exc:
        raise error_response(ErrorCode.NOT_FOUND, f"Prediction job {job_id} not found.", 404) from exc
    except FileNotFoundError as exc:
        raise error_response(ErrorCode.NOT_FOUND, str(exc), 404) from exc
    except JobParameterError as exc:
        raise error_response(exc.code, exc.detail, _ERROR_STATUS.get(exc.code, 400)) from exc
    return FileResponse(path, media_type="text/plain; charset=utf-8", filename=path.name)


# -- analysis cases ----------------------------------------------------------
# The case is what a result belongs to (review item 4): it names the datasets
# that went in, the run that produced the artifacts, and the reports that cite
# them. Before this existed, a conclusion had no identity and no way to say
# which data it came from.


@app.post("/api/v1/cases", status_code=201)
def create_case(
    payload: CaseCreateRequest,
    actor: str = Depends(current_actor),
    _: None = Depends(require_permission(Permission.CASE_CREATE)),
) -> dict:
    def operation() -> dict:
        case = case_service.create_case(
            title=payload.title,
            description=payload.description,
            owner=actor,
            station_code=payload.station_code,
            target_date=payload.target_date,
            dataset_version_ids=payload.dataset_version_ids,
        )
        audit_logger.record(
            actor=actor, action="case:create", object_type="case", object_id=str(case["case_id"])
        )
        return case

    return run_service_call(operation)


@app.get("/api/v1/cases")
def list_cases(
    owner: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[dict]:
    return case_service.list_cases(owner=owner, status=status, limit=limit)


@app.get("/api/v1/cases/summary")
def case_summary() -> dict:
    return case_service.summary()


@app.get("/api/v1/audit-events")
def list_audit_events(
    actor: str | None = Query(default=None),
    action: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    _: None = Depends(require_permission(Permission.AUDIT_READ)),
) -> list[dict]:
    """Query the append-only audit log (review item 7)."""
    return audit_logger.list(actor=actor, action=action, limit=limit)


@app.get("/api/v1/cases/{case_id}")
def get_case(case_id: str) -> dict:
    return run_service_call(lambda: case_service.case_view(case_id))


@app.patch("/api/v1/cases/{case_id}")
def update_case(case_id: str, payload: CaseUpdateRequest) -> dict:
    updates = payload.model_dump(exclude_none=True)
    return run_service_call(lambda: case_service.update_case(case_id, updates))


@app.delete("/api/v1/cases/{case_id}")
def delete_case(
    case_id: str,
    actor: str = Depends(current_actor),
    _: None = Depends(require_permission(Permission.CASE_DELETE)),
) -> dict:
    def operation() -> dict:
        result = case_service.delete_case(case_id, actor)
        audit_logger.record(
            actor=actor, action="case:delete", object_type="case", object_id=case_id
        )
        return result

    return run_service_call(operation)


@app.post("/api/v1/cases/{case_id}/archive")
def archive_case(
    case_id: str,
    actor: str = Depends(current_actor),
    _: None = Depends(require_permission(Permission.CASE_DELETE)),
) -> dict:
    def operation() -> dict:
        result = case_service.archive_case(case_id, actor)
        audit_logger.record(
            actor=actor, action="case:archive", object_type="case", object_id=case_id
        )
        return result

    return run_service_call(operation)


@app.get("/api/v1/cases/{case_id}/provenance")
def case_provenance(case_id: str) -> dict:
    return run_service_call(lambda: case_service.provenance(case_id))


@app.post("/api/v1/cases/{case_id}/run", status_code=201)
def run_case(
    case_id: str,
    payload: CaseRunRequest,
    actor: str = Depends(current_actor),
    _: None = Depends(require_permission(Permission.JOB_START)),
) -> dict:
    """Launch the case's analysis run.

    The station comes from the case, so the run cannot be pointed at data the
    case was not opened against.
    """
    case = run_service_call(lambda: case_service.get_case(case_id))
    request = PredictionJobCreateRequest(
        model_name=payload.model_name,
        station_code=str(case.get("station_code") or "2586"),
        config_path=payload.config_path,
        start_date=payload.start_date,
        end_date=payload.end_date,
        use_existing_artifacts=payload.use_existing_artifacts,
        case_id=case_id,
    )
    # The window checked is the one the case's own datasets cover — not every
    # dataset that happens to exist for the station.
    coverage = None
    if case.get("coverage_start") and case.get("coverage_end"):
        coverage = (str(case["coverage_start"]), str(case["coverage_end"]))
    try:
        result = launch_job(request, coverage=coverage)
    except FileNotFoundError as exc:
        raise error_response(ErrorCode.NOT_FOUND, str(exc), 400) from exc
    audit_logger.record(
        actor=actor,
        action="case:run",
        object_type="case",
        object_id=case_id,
        detail=f"job_id={result.get('job_id')}",
    )
    return result


# -- model registry ----------------------------------------------------------
# Models as governed, versioned assets (review item 11).


@app.get("/api/v1/models")
def list_models(
    model_key: str | None = Query(default=None),
    stage: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict]:
    return model_service.list(model_key=model_key, stage=stage, limit=limit)


@app.get("/api/v1/models/summary")
def model_summary() -> dict:
    return model_service.summary()


@app.get("/api/v1/models/current")
def current_model(model_key: str | None = Query(default=None)) -> dict | None:
    return model_service.current(model_key=model_key)


@app.post("/api/v1/models", status_code=201)
def register_model(
    payload: ModelRegisterRequest,
    actor: str = Depends(current_actor),
    _: None = Depends(require_permission(Permission.MODEL_PUBLISH)),
) -> dict:
    def operation() -> dict:
        model = model_service.register(
            model_key=payload.model_key,
            version=payload.version,
            author=actor,
            station_code=payload.station_code,
            training_dataset_version_id=payload.training_dataset_version_id,
            config_hash=payload.config_hash,
            metrics=payload.metrics,
            notes=payload.notes,
        )
        audit_logger.record(
            actor=actor,
            action="model:register",
            object_type="model",
            object_id=str(model["model_version_id"]),
        )
        return model

    return run_service_call(operation)


@app.get("/api/v1/models/{model_version_id}")
def get_model(model_version_id: str) -> dict:
    return run_service_call(lambda: model_service.get(model_version_id))


@app.post("/api/v1/models/{model_version_id}/transition")
def transition_model(
    model_version_id: str,
    payload: ModelTransitionRequest,
    actor: str = Depends(current_actor),
    _: None = Depends(require_permission(Permission.MODEL_PUBLISH)),
) -> dict:
    def operation() -> dict:
        model = model_service.transition(model_version_id, payload.to_stage, actor)
        audit_logger.record(
            actor=actor,
            action="model:transition",
            object_type="model",
            object_id=model_version_id,
            detail=f"to_stage={payload.to_stage}",
        )
        return model

    return run_service_call(operation)


# -- report centre -----------------------------------------------------------
# Reports as governed business objects (review item 21).


@app.get("/api/v1/reports")
def list_reports(
    status: str | None = Query(default=None),
    case_id: str | None = Query(default=None),
    author: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict]:
    return report_service.list(status=status, case_id=case_id, author=author, limit=limit)


@app.get("/api/v1/reports/summary")
def report_summary() -> dict:
    return report_service.summary()


@app.post("/api/v1/reports", status_code=201)
def create_report(
    payload: ReportCreateRequest,
    actor: str = Depends(current_actor),
) -> dict:
    def operation() -> dict:
        report = report_service.create(
            title=payload.title,
            author=actor,
            case_id=payload.case_id,
            project_name=payload.project_name,
            format=payload.format,
            time_range_start=payload.time_range_start,
            time_range_end=payload.time_range_end,
            content_selection=payload.content_selection,
        )
        audit_logger.record(
            actor=actor,
            action="report:create",
            object_type="report",
            object_id=str(report["report_id"]),
        )
        return report

    return run_service_call(operation)


@app.get("/api/v1/reports/{report_id}")
def get_report(report_id: str) -> dict:
    return run_service_call(lambda: report_service.get(report_id))


@app.patch("/api/v1/reports/{report_id}")
def update_report(report_id: str, payload: ReportUpdateRequest) -> dict:
    updates = payload.model_dump(exclude_none=True)
    return run_service_call(lambda: report_service.update(report_id, updates))


@app.post("/api/v1/reports/{report_id}/submit")
def submit_report(report_id: str) -> dict:
    return run_service_call(lambda: report_service.submit(report_id))


@app.post("/api/v1/reports/{report_id}/review")
def review_report(
    report_id: str,
    payload: ReportReviewRequest,
    actor: str = Depends(current_actor),
    _: None = Depends(require_permission(Permission.REPORT_REVIEW)),
) -> dict:
    def operation() -> dict:
        report = report_service.review(report_id, payload.approve, actor, payload.comment)
        audit_logger.record(
            actor=actor,
            action="report:review",
            object_type="report",
            object_id=report_id,
            detail=f"approve={payload.approve}",
        )
        return report

    return run_service_call(operation)


@app.post("/api/v1/reports/{report_id}/generate")
def generate_report(
    report_id: str,
    actor: str = Depends(current_actor),
    _: None = Depends(require_permission(Permission.REPORT_EXPORT)),
) -> dict:
    """Render the approved report, locking its manifest into the record."""
    report = run_service_call(lambda: report_service.get(report_id))
    artifacts, provenance = resolve_artifacts(
        case_id=report.get("case_id"),
        scope="integrated" if not report.get("case_id") else None,
    )

    def operation() -> dict:
        result = report_service.generate(report_id, artifacts, provenance)
        audit_logger.record(
            actor=actor,
            action="report:generate",
            object_type="report",
            object_id=report_id,
        )
        return result

    try:
        return run_service_call(operation)
    except HTTPException:
        raise
    except Exception as exc:
        raise artifact_error_to_http(exc) from exc


@app.post("/api/v1/reports/{report_id}/archive")
def archive_report(
    report_id: str,
    actor: str = Depends(current_actor),
    _: None = Depends(require_permission(Permission.REPORT_DELETE)),
) -> dict:
    return run_service_call(lambda: report_service.archive(report_id, actor))


@app.delete("/api/v1/reports/{report_id}")
def delete_report(
    report_id: str,
    actor: str = Depends(current_actor),
    _: None = Depends(require_permission(Permission.REPORT_DELETE)),
) -> dict:
    def operation() -> dict:
        result = report_service.delete(report_id, actor)
        audit_logger.record(
            actor=actor,
            action="report:delete",
            object_type="report",
            object_id=report_id,
        )
        return result

    return run_service_call(operation)


# -- event handling ----------------------------------------------------------
# Alerts with a closed loop (review item 27).


@app.get("/api/v1/events")
def list_events(
    status: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    case_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict]:
    return event_service.list(status=status, severity=severity, case_id=case_id, limit=limit)


@app.get("/api/v1/events/summary")
def event_summary() -> dict:
    return event_service.summary()


@app.post("/api/v1/events", status_code=201)
def create_event(
    payload: EventCreateRequest,
    actor: str = Depends(current_actor),
) -> dict:
    return run_service_call(
        lambda: event_service.create(
            title=payload.title,
            description=payload.description,
            severity=payload.severity,
            case_id=payload.case_id,
            target_date=payload.target_date,
            source=payload.source,
            creator=actor,
        )
    )


@app.get("/api/v1/events/{event_id}")
def get_event(event_id: str) -> dict:
    return run_service_call(lambda: event_service.get(event_id))


@app.post("/api/v1/events/{event_id}/assign")
def assign_event(
    event_id: str,
    payload: EventTransitionRequest,
    actor: str = Depends(current_actor),
    _: None = Depends(require_permission(Permission.EVENT_ASSIGN)),
) -> dict:
    return run_service_call(
        lambda: event_service.transition(
            event_id,
            "assigned",
            actor=actor,
            note=payload.note,
            assignee=payload.assignee,
        )
    )


@app.post("/api/v1/events/{event_id}/acknowledge")
def acknowledge_event(
    event_id: str,
    actor: str = Depends(current_actor),
) -> dict:
    return run_service_call(
        lambda: event_service.transition(event_id, "acknowledged", actor=actor)
    )


@app.post("/api/v1/events/{event_id}/handle")
def handle_event(
    event_id: str,
    actor: str = Depends(current_actor),
    _: None = Depends(require_permission(Permission.EVENT_HANDLE)),
) -> dict:
    return run_service_call(
        lambda: event_service.transition(event_id, "handling", actor=actor)
    )


@app.post("/api/v1/events/{event_id}/review")
def review_event(
    event_id: str,
    actor: str = Depends(current_actor),
    _: None = Depends(require_permission(Permission.EVENT_CLOSE)),
) -> dict:
    return run_service_call(
        lambda: event_service.transition(event_id, "reviewing", actor=actor)
    )


@app.post("/api/v1/events/{event_id}/close")
def close_event(
    event_id: str,
    payload: EventCloseRequest,
    actor: str = Depends(current_actor),
    _: None = Depends(require_permission(Permission.EVENT_CLOSE)),
) -> dict:
    return run_service_call(
        lambda: event_service.close(event_id, actor, payload.post_mortem, payload.note)
    )


@app.post("/api/v1/events/{event_id}/false-positive")
def false_positive_event(
    event_id: str,
    payload: EventFalsePositiveRequest,
    actor: str = Depends(current_actor),
    _: None = Depends(require_permission(Permission.EVENT_CLOSE)),
) -> dict:
    return run_service_call(
        lambda: event_service.mark_false_positive(event_id, actor, payload.reason)
    )


@app.post("/api/v1/events/{event_id}/escalate")
def escalate_event(
    event_id: str,
    payload: EventEscalateRequest,
    actor: str = Depends(current_actor),
    _: None = Depends(require_permission(Permission.EVENT_ASSIGN)),
) -> dict:
    return run_service_call(
        lambda: event_service.escalate(event_id, actor, payload.note)
    )


# -- results -----------------------------------------------------------------
# Every endpoint below answers "what did this case conclude?", so each takes the
# same three selectors: `case_id` (the normal path), `job_id` (compatibility
# alias for a run not yet bound to a case), or `scope=integrated` for the shared
# research artifacts. Omitting all three is a 409, not a silent fallback.


@app.get("/api/v1/dashboard")
def dashboard(
    case_id: str | None = Query(default=None),
    job_id: str | None = Query(default=None),
    scope: str | None = Query(default=None),
) -> dict:
    return artifact_payload(
        lambda artifacts: artifacts.dashboard(), case_id=case_id, job_id=job_id, scope=scope
    )


@app.get("/api/v1/predictions")
def predictions(
    model: str | None = Query(default=None),
    split: str = Query(default="test"),
    case_id: str | None = Query(default=None),
    job_id: str | None = Query(default=None),
    scope: str | None = Query(default=None),
) -> dict:
    return artifact_payload(
        lambda artifacts: artifacts.predictions(model=model, split=split),
        case_id=case_id,
        job_id=job_id,
        scope=scope,
        bad_request_errors=(ValueError,),
    )


@app.get("/api/v1/diagnostics")
def diagnostics(
    case_id: str | None = Query(default=None),
    job_id: str | None = Query(default=None),
    scope: str | None = Query(default=None),
) -> dict:
    return artifact_payload(
        lambda artifacts: artifacts.diagnostics(), case_id=case_id, job_id=job_id, scope=scope
    )


@app.get("/api/v1/scenario-triage")
def scenario_triage(
    case_id: str | None = Query(default=None),
    job_id: str | None = Query(default=None),
    scope: str | None = Query(default=None),
) -> dict:
    return artifact_payload(
        lambda artifacts: artifacts.scenario_triage(), case_id=case_id, job_id=job_id, scope=scope
    )


@app.get("/api/v1/response-playbook")
def response_playbook(
    case_id: str | None = Query(default=None),
    job_id: str | None = Query(default=None),
    scope: str | None = Query(default=None),
) -> dict:
    return artifact_payload(
        lambda artifacts: artifacts.response_playbook(), case_id=case_id, job_id=job_id, scope=scope
    )


@app.get("/api/v1/thresholds")
def thresholds(
    feature: str | None = Query(default=None),
    case_id: str | None = Query(default=None),
    job_id: str | None = Query(default=None),
    scope: str | None = Query(default=None),
) -> dict:
    return artifact_payload(
        lambda artifacts: artifacts.thresholds(feature=feature),
        case_id=case_id,
        job_id=job_id,
        scope=scope,
    )


@app.get("/api/v1/boundary")
def boundary(
    case_id: str | None = Query(default=None),
    job_id: str | None = Query(default=None),
    scope: str | None = Query(default=None),
) -> dict:
    return artifact_payload(
        lambda artifacts: artifacts.boundary(), case_id=case_id, job_id=job_id, scope=scope
    )


@app.get("/api/v1/sensitivity")
def sensitivity(
    case_id: str | None = Query(default=None),
    job_id: str | None = Query(default=None),
    scope: str | None = Query(default=None),
) -> dict:
    return artifact_payload(
        lambda artifacts: artifacts.sensitivity(), case_id=case_id, job_id=job_id, scope=scope
    )


@app.get("/api/v1/realtime-validation")
def realtime_validation() -> dict:
    return realtime_validation_service.latest()


@app.get("/api/v1/cross-modal/zhangjiabang")
def zhangjiabang_cross_modal() -> dict:
    return run_repository_call(cross_modal_repository.summary)


@app.get("/api/v1/cross-modal/media")
def cross_modal_media(path: str = Query(...)) -> FileResponse:
    try:
        media_path = cross_modal_repository.resolve_media_path(path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Cross-modal media file not found.") from exc
    return FileResponse(media_path)


@app.post("/api/v1/report/export")
def export_report(
    case_id: str | None = Query(default=None),
    job_id: str | None = Query(default=None),
    scope: str | None = Query(default=None),
    format: ReportExportFormat = Query(default="html"),
    actor: str = Depends(current_actor),
    _: None = Depends(require_permission(Permission.REPORT_EXPORT)),
) -> dict[str, str]:
    """Render a report from one scoped set of artifacts.

    The scope is resolved *once*, before rendering, so every section of the
    document comes from the same run — and the response carries that run's
    provenance, which the report centre records alongside the file.
    """
    artifacts, provenance = resolve_artifacts(case_id=case_id, job_id=job_id, scope=scope)

    def operation() -> dict[str, str]:
        report_path = write_report(
            artifacts,
            settings.report_root,
            export_format=format,
        )
        return {
            "report_path": str(report_path),
            "filename": report_path.name,
            "format": format,
            "download_url": f"/api/v1/report/files/{report_path.name}",
        }

    result = {**run_repository_call(operation), "provenance": provenance}
    audit_logger.record(
        actor=actor,
        action="report:export",
        object_type="report",
        object_id=result.get("filename"),
        detail=f"case_id={case_id} job_id={job_id} scope={scope} format={format}",
    )
    return result


@app.get("/api/v1/report/files/{filename}")
def download_report(filename: str) -> FileResponse:
    path = settings.report_root / Path(filename).name
    if not path.exists():
        raise HTTPException(status_code=404, detail="Report file not found.")
    return FileResponse(path, media_type=get_report_media_type(path), filename=path.name)


# ---------------------------------------------------------------------------
# Knowledge graph (literature → KG → QA)
# ---------------------------------------------------------------------------
@app.get("/api/v1/knowledge-graph/summary")
def knowledge_graph_summary() -> dict:
    return kg_service.summary()


@app.post("/api/v1/knowledge-graph/upload")
def knowledge_graph_upload(files: list[UploadFile] = File(...)) -> dict:
    try:
        return kg_service.upload_pdfs(files)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/v1/knowledge-graph/uploads")
def knowledge_graph_uploads() -> list[dict]:
    return kg_service.list_uploads()


@app.post("/api/v1/knowledge-graph/uploads/clear")
def knowledge_graph_clear_uploads() -> dict:
    return {"deleted_count": kg_service.clear_uploads()}


@app.post("/api/v1/knowledge-graph/preprocess")
def knowledge_graph_preprocess(payload: KnowledgeGraphPreprocessRequest) -> dict:
    try:
        return kg_service.preprocess(
            files=payload.files,
            write_json=payload.write_json,
            keep_captions=payload.keep_captions,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/v1/knowledge-graph/texts")
def knowledge_graph_texts() -> dict:
    return kg_service.list_texts()


@app.post("/api/v1/knowledge-graph/texts/clear")
def knowledge_graph_clear_texts() -> dict:
    return {"deleted_count": kg_service.clear_texts()}


@app.post("/api/v1/knowledge-graph/build")
def knowledge_graph_build(payload: KnowledgeGraphBuildRequest) -> dict:
    try:
        return kg_service.start_build(files=payload.files, max_chars=payload.max_chars)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/v1/knowledge-graph/jobs")
def knowledge_graph_jobs() -> list[dict]:
    return kg_service.list_build_jobs()


@app.get("/api/v1/knowledge-graph/jobs/{job_id}")
def knowledge_graph_job(job_id: str) -> dict:
    try:
        return kg_service.refresh_build_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Knowledge graph build job not found.") from exc


@app.get("/api/v1/knowledge-graph/graph")
def knowledge_graph_graph() -> dict:
    return kg_service.graph()


@app.post("/api/v1/knowledge-graph/kg/clear")
def knowledge_graph_clear_kg() -> dict:
    return {"deleted_count": kg_service.clear_kg()}


@app.post("/api/v1/knowledge-graph/qa")
def knowledge_graph_qa(payload: KnowledgeGraphQARequest) -> dict:
    try:
        return kg_service.qa(payload.question)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/v1/knowledge-graph/files/{name}")
def knowledge_graph_file(name: str) -> FileResponse:
    try:
        path = kg_service.file_download_path(name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(path, filename=path.name)
