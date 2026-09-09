from __future__ import annotations

import json
from typing import Any


def parse_json_response(response: str) -> dict[str, Any]:
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        return {"text": response}
