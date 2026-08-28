"""End-to-end acceptance of the five closed loops (review item 24).

The unit and API suites prove the pieces; this proves the *chain*. It drives the
real FastAPI app with a ``TestClient`` and the **real** auth guard — no
``dependency_overrides``, no stubbed token — so the login, JWT validation, RBAC
matrix, audit log and result-scope resolution are exercised together:

    register/login → upload data → quality gate → open a case → run (submit
    validation) → read results + diagnosis → governed report → export/download.

Because the model pipeline is a multi-hour research run, the "task completed"
step is simulated by marking the case ready and resolving artifacts from a
``FakeRepository``; the submit-stage refusal (out-of-coverage date → 400) is
real. A permission-matrix section then proves an operator cannot publish models
or run maintenance, that an admin can, and that every refusal lands in the audit
log — closing the "权限管得住、故障看得见" loops.
"""

from __future__ import annotations

import asyncio
import io
import tempfile
import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from fastapi.testclient import TestClient
from fastapi_users.password import PasswordHelper
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app import main
from backend.app.db import DATABASE_URL, Base
from backend.app.domain.codes import CaseStatus, ErrorCode
from backend.app.models import User
from backend.app.services.case_service import CaseService
from backend.app.services.dataset_service import DatasetService
from backend.app.services.event_service import EventService
from backend.app.services.model_service import ModelService
from backend.app.services.report_service import ReportService
from backend.app.services.security import AuditLogger
from backend.app.services.state_store import SqliteStateStore

from tests.backend.test_report_builder import FakeRepository


def _water_quality_csv(days: int = 60) -> bytes:
    dates = pd.date_range("2024-01-01", periods=days, freq="D")
    frame = pd.DataFrame(
        {
            "监测时间": [day.date().isoformat() for day in dates],
            "站点": ["2586"] * days,
            "浊度": [30.0 + index for index in range(days)],
            "水温": [15.0] * days,
            "pH": [7.4] * days,
        }
    )
    return frame.to_csv(index=False).encode("utf-8-sig")


def _password_helper() -> PasswordHelper:
    return PasswordHelper()


def _run_async(coro):
    """Run one coroutine against a fresh engine+loop so it cannot collide with
    the TestClient's loop (which owns ``main.engine``)."""
    return asyncio.run(coro)


def _provision_user(username: str, role: str, password: str) -> None:
    async def _run() -> None:
        engine = create_async_engine(DATABASE_URL)
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            maker = async_sessionmaker(engine, expire_on_commit=False)
            async with maker() as session:
                user = User(
                    username=username,
                    email=f"{username}@example.com",
                    display_name=username,
                    role=role,
                    hashed_password=_password_helper().hash(password),
                    is_active=True,
                    is_verified=True,
                    is_superuser=False,
                )
                session.add(user)
                await session.commit()
        finally:
            await engine.dispose()

    _run_async(_run())


def _delete_user(username: str) -> None:
    async def _run() -> None:
        from sqlalchemy import select

        engine = create_async_engine(DATABASE_URL)
        try:
            maker = async_sessionmaker(engine, expire_on_commit=False)
            async with maker() as session:
                result = await session.execute(select(User).where(User.username == username))
                user = result.scalar_one_or_none()
                if user is not None:
                    await session.delete(user)
                    await session.commit()
        finally:
            await engine.dispose()

    _run_async(_run())


def _login(client: TestClient, username: str, password: str) -> str:
    response = client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


class BusinessChainTest(unittest.TestCase):
    """One temp-rooted app with two real users: an admin and an operator."""

    _ADMIN = f"e2e_admin_{uuid.uuid4().hex[:8]}"
    _OPERATOR = f"e2e_operator_{uuid.uuid4().hex[:8]}"
    _PASSWORD = "e2e-password-123"

    @classmethod
    def setUpClass(cls) -> None:
        _provision_user(cls._ADMIN, "admin", cls._PASSWORD)
        _provision_user(cls._OPERATOR, "operator", cls._PASSWORD)

    @classmethod
    def tearDownClass(cls) -> None:
        _delete_user(cls._ADMIN)
        _delete_user(cls._OPERATOR)

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.settings = replace(
            main.settings,
            project_root=root,
            runtime_root=root,
            state_root=root / "state",
            report_root=root / "reports",
        )
        store = SqliteStateStore(self.settings.state_root)

        self._originals = {
            "settings": main.settings,
            "store": main.store,
            "dataset_service": main.dataset_service,
            "case_service": main.case_service,
            "model_service": main.model_service,
            "report_service": main.report_service,
            "event_service": main.event_service,
            "audit_logger": main.audit_logger,
        }
        # ``download_report``/``export_report`` read ``main.settings.report_root``
        # at call time, so they must agree with the temp-rooted report service.
        main.settings = self.settings
        main.store = store
        main.dataset_service = DatasetService(self.settings, store)
        main.case_service = CaseService(self.settings, store, main.dataset_service)
        main.model_service = ModelService(store)
        main.report_service = ReportService(self.settings, store)
        main.event_service = EventService(self.settings, store)
        main.audit_logger = AuditLogger(store)

        self.client = TestClient(main.app)
        self.admin_token = _login(self.client, self._ADMIN, self._PASSWORD)
        self.operator_token = _login(self.client, self._OPERATOR, self._PASSWORD)
        self.admin_headers = {"Authorization": f"Bearer {self.admin_token}"}
        self.operator_headers = {"Authorization": f"Bearer {self.operator_token}"}

    def tearDown(self) -> None:
        main.settings = self._originals["settings"]
        main.store = self._originals["store"]
        main.dataset_service = self._originals["dataset_service"]
        main.case_service = self._originals["case_service"]
        main.model_service = self._originals["model_service"]
        main.report_service = self._originals["report_service"]
        main.event_service = self._originals["event_service"]
        main.audit_logger = self._originals["audit_logger"]
        self._tmp.cleanup()

    # -- helpers -------------------------------------------------------------

    def _upload(self) -> dict:
        response = self.client.post(
            "/api/v1/datasets",
            data={"data_type": "water_quality", "station_code": "2586"},
            files={"file": ("wq.csv", io.BytesIO(_water_quality_csv()), "text/csv")},
            headers=self.operator_headers,
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def _create_case(self, version_id: str) -> dict:
        response = self.client.post(
            "/api/v1/cases",
            json={
                "title": "E2E turbidity spike",
                "station_code": "2586",
                "target_date": "2024-02-01",
                "dataset_version_ids": [version_id],
            },
            headers=self.operator_headers,
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()


class AuthBootstrapTest(BusinessChainTest):
    def test_login_returns_a_role_and_a_token(self) -> None:
        self.assertTrue(self.admin_token)
        self.assertTrue(self.operator_token)

    def test_every_data_route_requires_a_token(self) -> None:
        for path in ("/api/v1/datasets", "/api/v1/cases", "/api/v1/models"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 401)


class BusinessChainFlowTest(BusinessChainTest):
    def test_the_full_chain_closes_the_loop(self) -> None:
        # 1. upload → accepted, modelable, graded
        version = self._upload()
        self.assertEqual(version["status"], "accepted")
        self.assertEqual(version["modelable"], "1")

        # 2. quality report exposes the stage chain
        quality = self.client.get(
            f"/api/v1/dataset-versions/{version['version_id']}/quality",
            headers=self.operator_headers,
        )
        self.assertEqual(quality.status_code, 200)
        self.assertEqual(quality.json()["final_stage"], "accepted")

        # 3. open a case against the accepted data
        case = self._create_case(version["version_id"])
        case_id = case["case_id"]
        # ``current_actor`` identifies the caller by email; the case records it.
        self.assertEqual(case["owner"], f"{self._OPERATOR}@example.com")

        # 4. submit-stage validation: an out-of-coverage run is refused now, not
        #    after the multi-hour pipeline.
        refused = self.client.post(
            f"/api/v1/cases/{case_id}/run",
            json={"model_name": "cmfbe_stgcn", "start_date": "2019-01-01"},
            headers=self.operator_headers,
        )
        self.assertEqual(refused.status_code, 400)
        self.assertEqual(
            refused.json()["detail"]["code"], str(ErrorCode.DATE_RANGE_OUT_OF_COVERAGE)
        )

        # 5. simulate a completed run, then read results + diagnosis through the
        #    real scope resolution.
        main.case_service.update_case(
            case_id,
            {
                "status": str(CaseStatus.READY),
                "job_id": "job-e2e",
                "run_id": "job-e2e",
                "model_version": "cmfbe_stgcn",
                "config_hash": "e2e000000001",
                "artifacts_generated_at": "2030-01-01T00:00:00Z",
            },
        )
        provenance = {"case_id": case_id, "run_id": "job-e2e", "scope": "case"}
        with patch.object(main, "resolve_artifacts", return_value=(FakeRepository(), provenance)):
            dashboard = self.client.get(
                "/api/v1/dashboard", params={"case_id": case_id}, headers=self.operator_headers
            )
            self.assertEqual(dashboard.status_code, 200, dashboard.text)
            self.assertEqual(dashboard.json()["provenance"]["run_id"], "job-e2e")

            diagnosis = self.client.get(
                "/api/v1/diagnostics", params={"case_id": case_id}, headers=self.operator_headers
            )
            self.assertEqual(diagnosis.status_code, 200)
            self.assertIn("factor_summary", diagnosis.json())

            # 6. governed report: draft → submit → review → generate → download
            created = self.client.post(
                "/api/v1/reports",
                json={"title": "E2E report", "case_id": case_id, "format": "html"},
                headers=self.operator_headers,
            )
            self.assertEqual(created.status_code, 201, created.text)
            report_id = created.json()["report_id"]

            self.assertEqual(
                self.client.post(
                    f"/api/v1/reports/{report_id}/submit", headers=self.operator_headers
                ).status_code,
                200,
            )
            reviewed = self.client.post(
                f"/api/v1/reports/{report_id}/review",
                json={"approve": True, "comment": "looks good"},
                headers=self.admin_headers,
            )
            self.assertEqual(reviewed.status_code, 200, reviewed.text)

            generated = self.client.post(
                f"/api/v1/reports/{report_id}/generate", headers=self.operator_headers
            )
            self.assertEqual(generated.status_code, 200, generated.text)
            self.assertEqual(generated.json()["provenance"]["run_id"], "job-e2e")

            download = self.client.get(
                generated.json()["download_url"], headers=self.operator_headers
            )
            self.assertEqual(download.status_code, 200)

    def test_results_refuse_an_unscoped_read_through_real_auth(self) -> None:
        response = self.client.get("/api/v1/dashboard", headers=self.operator_headers)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["code"], str(ErrorCode.CASE_REQUIRED))


class PermissionMatrixTest(BusinessChainTest):
    def test_operator_can_do_day_to_day_work(self) -> None:
        version = self._upload()
        case = self._create_case(version["version_id"])
        self.assertEqual(case["status"], str(CaseStatus.DRAFT))

    def test_operator_cannot_publish_models_or_run_maintenance(self) -> None:
        publish = self.client.post(
            "/api/v1/models",
            json={"model_key": "cmfbe_stgcn", "version": "0.1", "station_code": "2586"},
            headers=self.operator_headers,
        )
        self.assertEqual(publish.status_code, 403)
        self.assertEqual(
            publish.json()["detail"]["code"], str(ErrorCode.PERMISSION_DENIED)
        )

        maintenance = self.client.post(
            "/api/v1/admin/maintenance/cleanup", headers=self.operator_headers
        )
        self.assertEqual(maintenance.status_code, 403)

    def test_admin_can_publish_and_the_refusal_is_audited(self) -> None:
        # Operator's refusal is recorded, and an admin can see it in the log.
        self.client.post(
            "/api/v1/models",
            json={"model_key": "cmfbe_stgcn", "version": "0.1"},
            headers=self.operator_headers,
        )
        audit = self.client.get("/api/v1/audit-events", headers=self.admin_headers)
        self.assertEqual(audit.status_code, 200)
        actions = [event["action"] for event in audit.json()]
        self.assertTrue(any("POST /api/v1/models" in action for action in actions))

        # The admin themselves may publish.
        published = self.client.post(
            "/api/v1/models",
            json={"model_key": "cmfbe_stgcn", "version": "0.2", "station_code": "2586"},
            headers=self.admin_headers,
        )
        self.assertEqual(published.status_code, 201, published.text)


if __name__ == "__main__":
    unittest.main()
