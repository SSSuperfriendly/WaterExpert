from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import pandas as pd

from backend.app.config import get_settings
from backend.app.services.data_explorer import DataExplorerService
from backend.app.services.dataset_service import DatasetService
from backend.app.services.state_store import SqliteStateStore

CATALOG_COLUMNS = [
    "station_code",
    "station_name",
    "province",
    "city",
    "basin",
    "river",
    "longitude",
    "latitude",
    "start_date",
    "end_date",
    "raw_rows",
    "daily_rows",
    "is_available",
    "availability_note",
    "source_file",
]

SECCHI_COLUMNS = [
    "date",
    "station_code",
    "station_name",
    "river",
    "water_temp",
    "ph",
    "dissolved_oxygen",
    "conductivity",
    "turbidity",
    "tp",
    "tn",
    "secchi_depth_sd_m",
    "water_quality_class",
]


def _catalog_csv(station_codes: list[str]) -> bytes:
    rows = [
        {
            "station_code": code,
            "station_name": f"station-{code}",
            "province": "上海",
            "city": "上海",
            "basin": "太湖",
            "river": "黄浦江",
            "longitude": "121.5",
            "latitude": "31.2",
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "raw_rows": "365",
            "daily_rows": "365",
            "is_available": "true",
            "availability_note": "",
            "source_file": "raw.csv",
        }
        for code in station_codes
    ]
    return pd.DataFrame(rows).to_csv(index=False).encode("utf-8-sig")


def _secchi_csv(rows: list[dict]) -> bytes:
    return pd.DataFrame(rows, columns=SECCHI_COLUMNS).to_csv(index=False).encode("utf-8-sig")


class DataExplorerSwitchTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        base = get_settings()
        self.settings = replace(
            base,
            project_root=root,
            runtime_root=root,
            state_root=root / "state",
            report_root=root / "reports",
        )
        self.store = SqliteStateStore(self.settings.state_root)
        self.dataset_service = DatasetService(self.settings, self.store)

        # Committed fallback files (the pre-registration read path), one station
        # and one row only, so the tests can tell which source was actually read.
        fallback_dir = self.settings.runtime_root / "data" / "full_station_database"
        fallback_dir.mkdir(parents=True, exist_ok=True)
        (fallback_dir / "station_catalog.csv").write_bytes(_catalog_csv(["1111"]))
        (fallback_dir / "water_quality_daily_all_stations_with_secchi.csv").write_bytes(
            _secchi_csv(
                [
                    {
                        "date": "2024-01-01",
                        "station_code": "1111",
                        "station_name": "station-1111",
                        "river": "黄浦江",
                        "turbidity": "30.0",
                        "secchi_depth_sd_m": "0.8",
                    }
                ]
            )
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _register(self, dataset_id: str, data_type: str, payload: bytes) -> None:
        source = self.settings.runtime_root / f"{dataset_id}.csv"
        source.write_bytes(payload)
        self.dataset_service.ensure_dataset(
            dataset_id=dataset_id,
            data_type=data_type,
            station_code=None,
            owner="baseline",
            kind="derived",
        )
        self.dataset_service.register_derived_file(
            source_path=source,
            data_type=data_type,
            station_code=None,
            owner="baseline",
            dataset_id=dataset_id,
            kind="derived",
        )

    def test_reads_registered_versions_over_committed_fallback(self) -> None:
        # Two stations in the registered version, one in the fallback.
        self._register("station_catalog", "station_catalog", _catalog_csv(["2586", "4001"]))
        self._register(
            "wq_all_stations_secchi",
            "water_quality",
            _secchi_csv(
                [
                    {
                        "date": "2024-01-01",
                        "station_code": "2586",
                        "station_name": "station-2586",
                        "river": "黄浦江",
                        "turbidity": "30.0",
                        "secchi_depth_sd_m": "0.8",
                    },
                    {
                        "date": "2024-01-02",
                        "station_code": "2586",
                        "station_name": "station-2586",
                        "river": "黄浦江",
                        "turbidity": "31.0",
                        "secchi_depth_sd_m": "0.81",
                    },
                ]
            ),
        )

        explorer = DataExplorerService(self.settings, self.dataset_service)

        stations = explorer.database_stations()
        self.assertEqual(len(stations), 2)
        self.assertEqual({station["station_code"] for station in stations}, {"2586", "4001"})

        result = explorer.query_records(station_code="2586")
        self.assertEqual(result["matched_rows"], 2)
        self.assertEqual(result["summary"]["station_count"], 1)

    def test_falls_back_to_committed_files_when_unregistered(self) -> None:
        explorer = DataExplorerService(self.settings, self.dataset_service)

        stations = explorer.database_stations()
        self.assertEqual(len(stations), 1)
        self.assertEqual(stations[0]["station_code"], "1111")

        result = explorer.query_records()
        self.assertEqual(result["matched_rows"], 1)


if __name__ == "__main__":
    unittest.main()
