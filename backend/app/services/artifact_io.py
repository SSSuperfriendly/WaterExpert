from __future__ import annotations

"""Shared artifact readers for the backend service layer.

Centralizes CSV/JSON reading, encoding, and error handling so repository and
service classes do not each re-implement slightly different file IO. All readers
use a tolerant UTF-8 encoding (``utf-8-sig`` strips an optional BOM) and raise a
consistent ``ArtifactReadError`` for malformed artifacts while letting
``FileNotFoundError`` propagate for callers that map it to HTTP 503/404.
"""

import csv
import json
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Iterator

import pandas as pd

DEFAULT_CSV_ENCODING = "utf-8-sig"


class ArtifactReadError(ValueError):
    """Raised when an artifact exists but is malformed or unreadable."""


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding=DEFAULT_CSV_ENCODING))
    except FileNotFoundError:
        raise
    except (OSError, UnicodeDecodeError, JSONDecodeError) as exc:
        raise ArtifactReadError(f"Invalid JSON artifact at {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ArtifactReadError(f"JSON artifact must decode to an object: {path}")
    return payload


def read_csv(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path, encoding=DEFAULT_CSV_ENCODING)
    except FileNotFoundError:
        raise
    except Exception as exc:
        raise ArtifactReadError(f"Failed to read CSV artifact at {path}: {exc}") from exc


def iter_csv_rows(path: Path) -> Iterator[dict[str, str]]:
    with path.open("r", encoding=DEFAULT_CSV_ENCODING, newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            yield {key: str(value or "") for key, value in row.items()}
