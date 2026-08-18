from __future__ import annotations

"""Repository encoding guard.

Verifies that every text file in the repository is valid UTF-8 and contains no
mojibake characters (the classic corruption where UTF-8 Chinese bytes are shown
as GBK, e.g. the word for "join" rendered as four unrelated CJK glyphs). Run it
before committing, or wire it into CI.

Exit code is 0 when the repository is clean, 1 when violations are found.
"""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

TEXT_SUFFIXES = (
    ".md",
    ".py",
    ".js",
    ".html",
    ".css",
    ".json",
    ".yaml",
    ".yml",
    ".txt",
    ".csv",
    ".ps1",
    ".sh",
    ".cfg",
    ".ini",
    ".toml",
    ".ts",
    ".vue",
    ".rst",
)

SKIP_DIR_NAMES = {
    ".git",
    ".ai4s",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".ipynb_checkpoints",
    ".vscode",
}

MAX_TEXT_BYTES = 50_000_000


def _is_common_cjk(char: str) -> bool:
    """Return True when ``char`` is a common CJK character.

    Mojibake produced by decoding UTF-8 bytes as GBK lands in the rare CJK
    area that is *not* representable in GB2312, so characters outside the
    GB2312 set are treated as corruption candidates.
    """
    try:
        char.encode("gb2312")
    except UnicodeEncodeError:
        return False
    return True


def iter_text_files(root: Path):
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        yield path


def find_violations(root: Path) -> list[str]:
    violations: list[str] = []
    for path in iter_text_files(root):
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size > MAX_TEXT_BYTES:
            continue
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            violations.append(f"non-utf8: {path}: {exc}")
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            for char in line:
                codepoint = ord(char)
                if 0x4E00 <= codepoint <= 0x9FFF and not _is_common_cjk(char):
                    violations.append(
                        f"mojibake: {path}:{line_number}: U+{codepoint:04X} {char!r}"
                    )
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=PROJECT_ROOT,
        help="Repository root to scan (default: project root).",
    )
    args = parser.parse_args(argv)

    violations = find_violations(args.root)
    if violations:
        print(f"Encoding guard failed with {len(violations)} violation(s):")
        for message in violations:
            print(f"  {message}")
        return 1
    print("Encoding guard passed: all text files are valid UTF-8 without mojibake.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
