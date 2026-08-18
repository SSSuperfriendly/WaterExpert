from __future__ import annotations

import unittest
from pathlib import Path

from scripts.dev.check_encoding import find_violations

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_ROOT = REPO_ROOT / "frontend"


class FrontendStaticTest(unittest.TestCase):
    def test_html_files_declare_utf8_charset(self) -> None:
        html_files = sorted(FRONTEND_ROOT.glob("*.html"))
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
