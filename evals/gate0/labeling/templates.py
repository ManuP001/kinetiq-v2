#!/usr/bin/env python3
"""
evals/gate0/labeling/templates.py

Writes the two blank CSV templates a PT fills in with no engineering help
(GOLDEN_SET_PROTOCOL.md §7): a clip-level sheet (one row per clip) and a rep-level sheet (one row
per rep). Header-only -- no example data row, so nothing a PT forgets to delete is ever
accidentally exported as a real clip.

Also exposes the valid fault (error) ids per exercise, read from the exercise library at runtime
(never hardcoded here -- CLAUDE.md §3) so a PT knows exactly what to type in the `faults` column.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List

import exercise_lib

from labeling.csv_schema import CLIP_COLUMNS, REP_COLUMNS

CLIPS_TEMPLATE_FILENAME = "clips_template.csv"
REPS_TEMPLATE_FILENAME = "reps_template.csv"


def write_templates(out_dir: Path) -> tuple[Path, Path]:
    """Writes clips_template.csv and reps_template.csv (header row only) into out_dir, creating
    it if needed. Returns their paths."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    clips_path = out_dir / CLIPS_TEMPLATE_FILENAME
    with clips_path.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(CLIP_COLUMNS)

    reps_path = out_dir / REPS_TEMPLATE_FILENAME
    with reps_path.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(REP_COLUMNS)

    return clips_path, reps_path


def fault_ids_by_exercise(directory: Path | None = None) -> Dict[str, List[str]]:
    """exercise_id -> sorted list of valid error_ids, straight from the exercise library --
    exactly what a PT is allowed to type into the reps template's `faults` column."""
    severities = exercise_lib.load_fault_severities(directory)
    return {exercise: sorted(faults) for exercise, faults in severities.items()}


def format_fault_ids(exercise: str, directory: Path | None = None) -> str:
    by_exercise = fault_ids_by_exercise(directory)
    if exercise not in by_exercise:
        known = sorted(by_exercise)
        return f"unknown exercise {exercise!r}; known exercises: {known}"
    faults = by_exercise[exercise]
    if not faults:
        return f"{exercise}: no faults defined in its exercise-library entry"
    return f"{exercise}: " + ", ".join(faults)
