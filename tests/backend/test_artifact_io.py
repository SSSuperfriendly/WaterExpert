from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.app.services.artifact_io import (
    ArtifactReadError,
    iter_csv_rows,
    read_csv,
    read_json,
)


class ArtifactIoTest(unittest.TestCase):
    def test_read_json_round_trips_utf8_object(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "payload.json"
            path.write_text(
                json.dumps({"name": "吴淞口", "rows": 92}, ensure_ascii=False),
                encoding="utf-8",
            )
            self.assertEqual(read_json(path)["name"], "吴淞口")

    def test_read_json_strips_bom(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "bom.json"
            path.write_bytes(b"\xef\xbb\xbf" + json.dumps({"ok": True}).encode("utf-8"))
            self.assertEqual(read_json(path), {"ok": True})

    def test_read_json_raises_artifact_error_on_malformed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "bad.json"
            path.write_text("{not json", encoding="utf-8")
            with self.assertRaises(ArtifactReadError):
                read_json(path)

    def test_read_json_raises_artifact_error_on_non_object(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "list.json"
            path.write_text("[1, 2]", encoding="utf-8")
            with self.assertRaises(ArtifactReadError):
                read_json(path)

    def test_read_json_propagates_file_not_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            with self.assertRaises(FileNotFoundError):
                read_json(Path(tmp_dir) / "missing.json")

    def test_read_csv_handles_bom(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "data.csv"
            path.write_bytes(b"\xef\xbb\xbfstation_code,value\n2586,1.5\n")
            frame = read_csv(path)
            self.assertIn("station_code", frame.columns)
            self.assertEqual(len(frame), 1)

    def test_read_csv_propagates_file_not_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            with self.assertRaises(FileNotFoundError):
                read_csv(Path(tmp_dir) / "missing.csv")

    def test_iter_csv_rows_normalizes_missing_to_empty_string(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "rows.csv"
            path.write_text("a,b\n1,\n,2\n", encoding="utf-8")
            rows = list(iter_csv_rows(path))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["b"], "")
            self.assertEqual(rows[1]["a"], "")


if __name__ == "__main__":
    unittest.main()
