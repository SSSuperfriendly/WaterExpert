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
from backend.app.schemas import (
    DataImportRequest,
    KnowledgeGraphBuildRequest,
    KnowledgeGraphPreprocessRequest,
    KnowledgeGraphQARequest,
    LoginRequest,
    RegisterRequest,
    PredictionJobCreateRequest,
    ReportExportFormat,
    UserCreate,
    UserRead,
    UserUpdate,
)
from backend.app.services.artifact_repository import ArtifactReadError, ArtifactRepository
from backend.app.services.cross_modal_repository import CrossModalRepository
from backend.app.services.data_explorer import DataExplorerService
from backend.app.services.kg_service import KnowledgeGraphService
from backend.app.services.realtime_validation import RealtimeValidationService
from backend.app.services.report_builder import get_report_media_type, write_report
from backend.app.services.runtime_jobs import RuntimeJobService
from backend.app.services.state_store import SqliteStateStore
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
data_explorer = DataExplorerService(settings)
realtime_validation_service = RealtimeValidationService(settings)
cross_modal_repository = CrossModalRepository(settings)
kg_service = KnowledgeGraphService(settings)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _requires_auth(path: str) -> bool:
    """Whether ``path`` is a protected API route (auth gate applies)."""
    if not path.startswith("/api/"):
        return False
    return not path.startswith(
        (
            "/api/v1/auth/",
            "/api/v1/report/files/",
            "/api/v1/knowledge-graph/files/",
            "/api/v1/cross-modal/media",
        )
    )


async def auth_guard(request: Request) -> None:
    """Global dependency: enforce a valid bearer token on protected API routes."""
    if not _requires_auth(request.url.path):
        return
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated.")
    token = authorization[7:].strip()
    if await authenticate_token(token) is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token.")


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
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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


def run_repository_call(operation, *, bad_request_errors: tuple[type[Exception], ...] = ()):
    try:
        return operation()
    except HTTPException:
        raise
    except bad_request_errors as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise artifact_error_to_http(exc) from exc


def resolve_repository(job_id: str | None, require_completed: bool = False) -> ArtifactRepository:
    if not job_id:
        return repository
    try:
        return runtime_jobs.get_job_repository(job_id, require_completed=require_completed)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Prediction job not found.") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/", include_in_schema=False)
def index() -> RedirectResponse:
    return RedirectResponse(url="/ui/login")


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(status_code=204)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> Response:
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": str(exc.detail)}, status_code=exc.status_code)
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
def healthz() -> dict[str, str]:
    return run_repository_call(_healthz_payload)


def _healthz_payload() -> dict[str, str]:
    repository.assert_source_ready()
    return {"status": "ok"}


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
def meta(job_id: str | None = Query(default=None)) -> dict:
    return run_repository_call(
        lambda: resolve_repository(job_id, require_completed=bool(job_id)).metadata()
    )


@app.get("/api/v1/stations")
def stations() -> list[dict]:
    return run_repository_call(repository.stations)


@app.post("/api/v1/data/import")
def import_data(payload: DataImportRequest) -> dict:
    return runtime_jobs.import_data(payload)


@app.post("/api/v1/data/upload")
def upload_data_files(
    data_type: str = Form(...),
    station_code: str = Form(default="2586"),
    time_granularity: str = Form(default="daily"),
    files: list[UploadFile] = File(...),
) -> dict:
    try:
        return runtime_jobs.upload_data_files(
            data_type=data_type,
            station_code=station_code,
            time_granularity=time_granularity,
            files=files,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/v1/data/imports")
def list_imports() -> list[dict]:
    return runtime_jobs.list_imports()


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


@app.post("/api/v1/prediction-jobs")
def create_prediction_job(payload: PredictionJobCreateRequest) -> dict:
    try:
        return runtime_jobs.create_prediction_job(payload)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/v1/prediction-jobs")
def list_prediction_jobs() -> list[dict]:
    return runtime_jobs.list_jobs()


@app.get("/api/v1/prediction-jobs/{job_id}")
def get_prediction_job(job_id: str) -> dict:
    try:
        return runtime_jobs.refresh_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Prediction job not found.") from exc


@app.get("/api/v1/prediction-jobs/{job_id}/series")
def get_prediction_job_series(job_id: str) -> dict:
    try:
        return runtime_jobs.get_job_series(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Prediction job not found.") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/v1/dashboard")
def dashboard(job_id: str | None = Query(default=None)) -> dict:
    return run_repository_call(
        lambda: resolve_repository(job_id, require_completed=bool(job_id)).dashboard()
    )


@app.get("/api/v1/predictions")
def predictions(
    model: str | None = Query(default=None),
    split: str = Query(default="test"),
    job_id: str | None = Query(default=None),
) -> dict:
    return run_repository_call(
        lambda: resolve_repository(job_id, require_completed=bool(job_id)).predictions(
            model=model,
            split=split,
        ),
        bad_request_errors=(ValueError,),
    )


@app.get("/api/v1/diagnostics")
def diagnostics(job_id: str | None = Query(default=None)) -> dict:
    return run_repository_call(
        lambda: resolve_repository(job_id, require_completed=bool(job_id)).diagnostics()
    )


@app.get("/api/v1/scenario-triage")
def scenario_triage(job_id: str | None = Query(default=None)) -> dict:
    return run_repository_call(
        lambda: resolve_repository(job_id, require_completed=bool(job_id)).scenario_triage()
    )


@app.get("/api/v1/response-playbook")
def response_playbook(job_id: str | None = Query(default=None)) -> dict:
    return run_repository_call(
        lambda: resolve_repository(job_id, require_completed=bool(job_id)).response_playbook()
    )


@app.get("/api/v1/thresholds")
def thresholds(
    feature: str | None = Query(default=None),
    job_id: str | None = Query(default=None),
) -> dict:
    return run_repository_call(
        lambda: resolve_repository(job_id, require_completed=bool(job_id)).thresholds(
            feature=feature
        )
    )


@app.get("/api/v1/boundary")
def boundary(job_id: str | None = Query(default=None)) -> dict:
    return run_repository_call(
        lambda: resolve_repository(job_id, require_completed=bool(job_id)).boundary()
    )


@app.get("/api/v1/sensitivity")
def sensitivity(job_id: str | None = Query(default=None)) -> dict:
    return run_repository_call(
        lambda: resolve_repository(job_id, require_completed=bool(job_id)).sensitivity()
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
    job_id: str | None = Query(default=None),
    format: ReportExportFormat = Query(default="html"),
) -> dict[str, str]:
    def operation() -> dict[str, str]:
        scoped_repository = resolve_repository(job_id, require_completed=bool(job_id))
        report_path = write_report(
            scoped_repository,
            settings.report_root,
            export_format=format,
        )
        return {
            "report_path": str(report_path),
            "filename": report_path.name,
            "format": format,
            "download_url": f"/api/v1/report/files/{report_path.name}",
        }

    return run_repository_call(operation)


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
