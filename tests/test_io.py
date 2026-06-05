from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from water_ai.utils.io import load_yaml, save_json


class IoUtilsTest(unittest.TestCase):
    def test_load_yaml_returns_empty_mapping_for_empty_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "empty.yaml"
            path.write_text("", encoding="utf-8")
            self.assertEqual(load_yaml(path), {})

    def test_load_yaml_rejects_non_mapping_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "list.yaml"
            path.write_text("- one\n- two\n", encoding="utf-8")
            with self.assertRaises(TypeError):
                load_yaml(path)

    def test_save_json_writes_valid_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "nested" / "payload.json"
            save_json({"value": 1, "items": [1, 2, 3]}, path)
            self.assertTrue(path.exists())
            self.assertIn('"value": 1', path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
