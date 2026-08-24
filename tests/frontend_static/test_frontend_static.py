from __future__ import annotations

import unittest
from pathlib import Path

from scripts.dev.check_encoding import find_violations

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_OUT = REPO_ROOT / "frontend" / "out"

# Every route in the Next.js app (App Router, static export). The static export
# emits one `index.html` per route under `frontend/out/<route>/index.html`, plus
# the root `index.html` and a top-level `404.html` error page.
EXPECTED_ROUTES = (
    "index.html",
    "login/index.html",
    "database/index.html",
    "upload/index.html",
    "preprocess/index.html",
    "visualization/index.html",
    "prediction/index.html",
    "diagnosis/index.html",
    "thresholds/index.html",
    "boundary/index.html",
    "scenario/index.html",
    "playbook/index.html",
    "sensitivity/index.html",
    "realtime/index.html",
    "knowledge-graph/index.html",
    "knowledge-graph/upload/index.html",
    "knowledge-graph/preprocess/index.html",
    "knowledge-graph/build/index.html",
    "knowledge-graph/qa/index.html",
    "knowledge-graph/view/index.html",
)


class FrontendStaticTest(unittest.TestCase):
    def test_static_export_contains_expected_routes(self) -> None:
        for relative in EXPECTED_ROUTES:
            path = FRONTEND_OUT / relative
            self.assertTrue(
                path.is_file(),
                f"Expected static export route missing: frontend/out/{relative}",
            )

    def test_html_files_declare_utf8_charset(self) -> None:
        html_files = sorted(FRONTEND_OUT.glob("**/*.html"))
        self.assertGreater(len(html_files), 0)
        for path in html_files:
            content = path.read_text(encoding="utf-8").lower()
            self.assertIn(
                "charset",
                content,
                f"{path.name} is missing a charset declaration",
            )
            self.assertIn(
                "utf-8",
                content,
                f"{path.name} does not declare UTF-8",
            )

    def test_repository_text_is_utf8_without_mojibake(self) -> None:
        violations = find_violations(REPO_ROOT)
        self.assertEqual(violations, [], "Encoding guard violations found")


if __name__ == "__main__":
    unittest.main()
