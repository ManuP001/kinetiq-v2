#!/usr/bin/env python3
"""
evals/gate0/exercise_lib.py

Exposes each exercise's fault ids and severities to the eval harness -- the one place the
harness reads "what faults exist and how severe are they" (EVAL_HARNESS_STAGE0_SPEC.md: "flag
lists and severities are read from the exercise library at runtime ... never re-hardcoded in the
harness").

Severity alias -- flagged, not silently reconciled (EXERCISE_LIBRARY.md §4):
    The canonical Stage-0 severity taxonomy is {high, med, low}. The current
    kinetiq-v2/exercises/*.json files (and the Vision_Contract sheet) still write "medium", not
    "med". Bulk-rewriting that JSON is explicitly out of scope for the Stage-0 harness
    (EVAL_HARNESS_STAGE0_SPEC.md's "one decision to surface, not silently resolve"), so this
    loader aliases "medium" -> "med" at read time instead. The underlying JSON data still says
    "medium" -- a follow-up should normalise the source files and delete this alias.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import gate_config

VALID_SEVERITIES = ("high", "med", "low")

# "medium" is the only alias needed today (see module docstring); "high"/"med"/"low" pass
# through unchanged so the loader also accepts already-normalised data.
_SEVERITY_ALIASES = {
    "medium": "med",
    "high": "high",
    "med": "med",
    "low": "low",
}


class ExerciseLibraryError(ValueError):
    """Raised when an exercise-library entry violates the Stage-0 schema contract
    (EXERCISE_LIBRARY.md §4: every fault must declare a severity that normalises to
    high/med/low)."""


def normalize_severity(raw: str) -> str:
    try:
        return _SEVERITY_ALIASES[raw]
    except KeyError:
        raise ExerciseLibraryError(
            f"unknown severity {raw!r}; must be one of {sorted(_SEVERITY_ALIASES)} "
            f"(normalises to {VALID_SEVERITIES})"
        ) from None


def load_fault_severities(directory: Path | None = None) -> dict[str, dict[str, str]]:
    """exercise_id -> {fault_id: severity}, severity normalised to {high, med, low}.

    Raises ExerciseLibraryError if any fault in the library has no severity at all --
    EXERCISE_LIBRARY.md §4 makes that a schema error, not a silent default.
    """
    library = gate_config.load_exercise_library(directory)
    out: dict[str, dict[str, str]] = {}
    for exercise_id, entry in library.items():
        faults: dict[str, str] = {}
        common_errors = entry.get("reference_keypoints", {}).get("common_errors", [])
        for err in common_errors:
            fault_id = err["error_id"]
            severity_raw = err.get("severity")
            if severity_raw is None:
                raise ExerciseLibraryError(
                    f"{exercise_id}.{fault_id} has no severity -- EXERCISE_LIBRARY.md §4 "
                    f"requires one of {VALID_SEVERITIES}"
                )
            faults[fault_id] = normalize_severity(severity_raw)
        out[exercise_id] = faults
    return out


def load_fault_metadata(directory: Path | None = None) -> dict[str, dict[str, dict[str, Any]]]:
    """exercise_id -> {fault_id: raw common_errors entry} -- for callers that need more than
    just severity (e.g. description). Severity is left un-normalised here; use
    load_fault_severities() for the normalised value."""
    library = gate_config.load_exercise_library(directory)
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for exercise_id, entry in library.items():
        common_errors = entry.get("reference_keypoints", {}).get("common_errors", [])
        out[exercise_id] = {err["error_id"]: err for err in common_errors}
    return out
