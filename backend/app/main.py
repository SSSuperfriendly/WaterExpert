from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.staticfiles import StaticFiles

from backend.app.config import get_settings
from backend.app.schemas import (
    DataImportRequest,
    LoginRequest,
    PredictionJobCreateRequest,
    ReportExportFormat,
)
from backend.app.services.auth_service import DemoAuthService
from backend.app.services.artifact_repository import ArtifactReadError, ArtifactRepository
from backend.app.services.data_explorer import DataExplorerService
from backend.app.services.report_builder import get_report_media_type, write_report
from backend.app.services.runtime_jobs import RuntimeJobService
from backend.app.services.state_store import SqliteStateStore


settings = get_settings()
repository = ArtifactRepository(settings)
store = SqliteStateStore(settings.state_root)
runtime_jobs = RuntimeJobService(settings, repository, store)
auth_service = DemoAuthService()
data_explorer = DataExplorerService(settings)

app = FastAPI(
    title=settings.app_name,
    description="Integrated software product with embedded WaterExpert algorithm runtime.",
    version="0.3.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/ui", StaticFiles(directory=settings.frontend_root), name="ui")


def _frontend_error_page(filename: str, status_code: int) -> FileResponse:
    path = settings.frontend_root / filename
    return FileResponse(path, media_type="text/html", status_code=status_code)


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
    return RedirectResponse(url="/ui/login.html")


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
        media_type="text/plain",
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
        media_type="text/plain",
    )


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return run_repository_call(_healthz_payload)


def _healthz_payload() -> dict[str, str]:
    repository.assert_source_ready()
    return {"status": "ok"}


@app.post("/api/v1/auth/login")
def login(payload: LoginRequest) -> dict:
    profile = auth_service.authenticate(payload.username, payload.password)
    if profile is None:
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    return {
        "username": profile.username,
        "display_name": profile.display_name,
        "role": profile.role,
    }


@app.get("/api/v1/auth/hint")
def auth_hint() -> dict[str, str]:
    return auth_service.credential_hint()


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
