#!/usr/bin/env python3
"""
evals/gate0/labeling/csv_schema.py

The two CSV shapes a PT fills in, and the handful of parsing helpers shared by templates.py
(writes blank headers) and export.py (reads filled rows) -- one definition of each column name,
never restated independently in the writer and the reader.

CLIP_COLUMNS: one row per clip (GOLDEN_SET_PROTOCOL.md §5 step 2's "set the metadata").
REP_COLUMNS: one row per rep (§5 step 3's "count reps out loud ... call the intended fault").
Blank optional cells become `None` (`view`, `lighting`, `fitness_level`, `subject_track_id`);
required cells raise LabelExportError if blank or malformed -- this module never guesses.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

CLIP_COLUMNS: tuple[str, ...] = (
    "clip_id",
    "exercise",
    "clip_type",
    "view",
    "lighting",
    "fitness_level",
    "actual_reps",
    "num_people_in_frame",
    "subject_track_id",
    "labeler",
    "pt_verified",
)

REP_COLUMNS: tuple[str, ...] = ("clip_id", "rep_idx", "faults")

# Faults within one CSV cell are ';'-separated (fault/error ids never contain ';' or ',').
FAULT_DELIMITER = ";"

_TRUE_STRINGS = {"true", "1", "yes", "y"}
_FALSE_STRINGS = {"false", "0", "no", "n", ""}


class LabelExportError(ValueError):
    """Raised for a CSV that can't be turned into valid JSON at all -- a missing column, a
    non-integer where an integer is required, a duplicate clip_id/rep_idx. Domain rules (does
    this fault id exist, does a phantom clip really have zero reps) are validate.py's job, not
    this one's -- see the package docstring."""


def _blank_to_none(raw: str) -> Optional[str]:
    stripped = raw.strip()
    return stripped if stripped else None


def parse_bool(raw: str, *, context: str) -> bool:
    normalized = raw.strip().lower()
    if normalized in _TRUE_STRINGS:
        return True
    if normalized in _FALSE_STRINGS:
        return False
    raise LabelExportError(f"{context}: {raw!r} is not a recognized boolean (true/false/yes/no)")


def parse_int(raw: str, *, context: str, required: bool = True) -> Optional[int]:
    stripped = raw.strip()
    if not stripped:
        if required:
            raise LabelExportError(f"{context}: missing required integer value")
        return None
    try:
        return int(stripped)
    except ValueError:
        raise LabelExportError(f"{context}: {raw!r} is not an integer") from None


def parse_faults(raw: str) -> List[str]:
    stripped = raw.strip()
    if not stripped:
        return []
    return [f.strip() for f in stripped.split(FAULT_DELIMITER) if f.strip()]


def require_columns(fieldnames: Optional[List[str]], expected: tuple[str, ...], *, context: str) -> None:
    if fieldnames is None:
        raise LabelExportError(f"{context}: empty CSV (no header row)")
    missing = [c for c in expected if c not in fieldnames]
    if missing:
        raise LabelExportError(f"{context}: missing required column(s) {missing}")


def clip_row_get(row: Dict[str, Any], column: str, *, clip_id: str) -> Optional[str]:
    return _blank_to_none(row.get(column, "") or "")
