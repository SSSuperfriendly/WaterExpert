"""The curated case library, and the readings it can honestly lend to a plan.

Why this module exists
----------------------
``data/case_library/cases.json`` is the only place in this service where a
number that was *actually applied to a real water body* exists. Eight documented
interventions, each carrying the water body's condition, what was done
(``intervention``), what happened (``outcome``), and a citable reference.

It used to be read by exactly one caller — ``api/routes/explain.py`` — for
exactly one purpose: a prose ``【案例支撑】`` paragraph. The knowledge base, which
is the component that *proposes* techniques, never saw it. It filled in the
operating parameters of everything it proposed from two module constants
instead (``DEFAULT_INTENSITY = 0.5``, ``DEFAULT_COST_PER_DAY = 0.0``), which is
how a literature candidate reached the report wearing the same shape as a costed
technique and carrying two numbers that came from nowhere. This module is the
shared reader that lets the knowledge base answer with what the cases recorded.

What it does not do
-------------------
It does not invent a reading, and it does not convert one between units.
``intervention`` is a fixed triple — ``release_rate``, ``aeration_intensity``,
``chemical_dosage`` — and a caller asking for anything else gets ``None`` rather
than a plausible substitute. Units are given only where the case text states
them: the summaries write "5.2m³/s" and "高强度曝气(18kW)", and they state no
unit at all for the chemical dose, so :data:`INTERVENTION_UNITS` leaves that one
``None`` and a consumer is expected to render the bare number rather than guess
a denominator. A number a hydrologist cannot check is not evidence.
"""

from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any

#: Where the library lives. This file is ``agent/src/water_ai/data/case_library.py``,
#: so three parents up is ``agent/``.
DEFAULT_LIBRARY = Path(__file__).resolve().parents[3] / "data" / "case_library" / "cases.json"

#: The intervention fields a case records, with the unit its summary states.
#: ``chemical_dosage`` has none: the cases describe the dose ("微量PAC投加",
#: "生物制剂投加") without ever naming a unit, and a guessed denominator would
#: destroy the only thing the number is good for, which is being checkable.
INTERVENTION_UNITS: dict[str, str | None] = {
    "release_rate": "m³/s",
    "aeration_intensity": "kW",
    "chemical_dosage": None,
}

#: The condition fields similarity is measured over. Deliberately the same three
#: for every case: they are the ones all eight of them report, and a similarity
#: computed over different axes for different cases would not be comparable.
SIMILARITY_FIELDS = ("rainfall_3d", "turbidity", "flow_rate")


@lru_cache(maxsize=8)
def _read(path: str, _modified_ns: int) -> tuple[dict[str, Any], ...]:
    """Parsed cases, keyed by the file's identity *and* its mtime.

    The mtime is part of the key so a library edited while the service is
    running is picked up, and part of the *key* rather than a check so the
    common path stays a dictionary hit.
    """
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return ()
    if not isinstance(data, list):
        return ()
    return tuple(item for item in data if isinstance(item, dict))


def load_cases(path: Path | None = None) -> list[dict[str, Any]]:
    """Every case in the library. An unreadable library is empty, not fatal."""
    target = Path(path) if path is not None else DEFAULT_LIBRARY
    try:
        modified_ns = target.stat().st_mtime_ns
    except OSError:
        return []
    return list(_read(str(target), modified_ns))


def similarity(condition: dict[str, Any], state: dict[str, Any]) -> float:
    """Normalised distance between a case's condition and the current state.

    Scale-free: each field is divided by the larger of the two readings before
    it is squared, so 32 NTU versus 28 NTU counts the same as 3.2 versus 2.8.
    A field either side does not report is skipped rather than counted as a
    mismatch, and a case with no overlapping field scores 0 instead of being
    silently ranked first.
    """
    distance = 0.0
    counted = 0
    for key in SIMILARITY_FIELDS:
        case_value = condition.get(key)
        state_value = state.get(key)
        if isinstance(case_value, bool) or isinstance(state_value, bool):
            continue
        if not isinstance(case_value, (int, float)) or not isinstance(state_value, (int, float)):
            continue
        scale = max(abs(case_value), abs(state_value), 1.0)
        distance += ((case_value - state_value) / scale) ** 2
        counted += 1
    if counted == 0:
        return 0.0
    return max(0.0, 1.0 - math.sqrt(distance / counted))


def cases_for(
    scenario: str,
    state: dict[str, Any] | None,
    top_k: int = 2,
    *,
    fallback_to_all: bool = True,
) -> list[dict[str, Any]]:
    """The cases of ``scenario`` most like ``state``, best first.

    ``fallback_to_all`` is what separates the two callers. The explain route has
    always widened to the whole library when a scenario has no cases of its own,
    because a prose "here is the closest thing we have" is more useful than
    nothing. The knowledge base must *not*: binding a technique to the
    intervention of a case from a different scenario would put a real number
    behind the wrong claim, which is worse than an honest blank.
    """
    cases = load_cases()
    matched = [case for case in cases if case.get("scenario") == scenario]
    if not matched and fallback_to_all:
        matched = cases
    current = state or {}
    scored = [(case, similarity(case.get("condition") or {}, current)) for case in matched]
    # Stable, so cases of equal similarity keep the library's own order.
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return [
        {"case": case, "similarity": round(score, 3)}
        for case, score in scored[: max(0, top_k)]
    ]


def reading(case: dict[str, Any], field: str) -> dict[str, Any] | None:
    """What one case recorded for one intervention field, or ``None``.

    A recorded zero is a reading: ``chemical_dosage: 0`` on the Taihu case means
    no chemical was dosed, not that the field is missing. The guard is therefore
    on type rather than on truthiness, which is also what keeps a missing field
    from being reported as an intensity of nought.
    """
    intervention = case.get("intervention")
    if not isinstance(intervention, dict):
        return None
    value = intervention.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return {"field": field, "value": float(value), "unit": INTERVENTION_UNITS.get(field)}


def outcome_of(case: dict[str, Any]) -> dict[str, Any]:
    """What the case reports happened. Never ``None``, so callers can index it."""
    outcome = case.get("outcome")
    return dict(outcome) if isinstance(outcome, dict) else {}


def describe(match: dict[str, Any]) -> dict[str, Any]:
    """One :func:`cases_for` result as the API reports it.

    Both the explain route and the knowledge base go through here, so a case
    cited by a recommendation is the same record — same id, same numbers — as
    the case card the explanation showed. Two hand-written dict literals would
    have drifted the first time a field was added to one of them.
    """
    case = match.get("case") or {}
    return {
        "id": str(case.get("id") or ""),
        "title": str(case.get("title") or ""),
        "location": str(case.get("location") or ""),
        "year": case.get("year"),
        "scenario": str(case.get("scenario") or ""),
        "similarity": match.get("similarity", 0.0),
        "summary": str(case.get("summary") or ""),
        "reference": str(case.get("reference") or ""),
        "intervention": dict(case.get("intervention") or {}),
        "outcome": outcome_of(case),
    }
