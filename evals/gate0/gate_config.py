#!/usr/bin/env python3
"""
evals/gate0/gate_config.py

Single import point for backend/app/core/config.py's Stage-0 gate floors
(EVAL_HARNESS_STAGE0_SPEC.md §8, CLAUDE.md §3: config.py is the single source of truth). Every
other module in this harness (aggregate.py, exercise_lib.py, scorers/*.py) imports floors from
here rather than the backend package directly, so the sys.path fixup needed to reach a
sibling-repo package (no pyproject.toml/packaging exists yet -- see aggregate.py's original
comment) lives in exactly one place.

Never restate a gate-floor number in this harness -- import it from here.
"""
from __future__ import annotations

import sys
from pathlib import Path

# kinetiq-v2/evals/gate0/gate_config.py -> parents[2] == kinetiq-v2/
_BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.core.config import (  # noqa: E402
    FORM_PRECISION_FLOOR_HIGH_SEV,
    FORM_PRECISION_FLOOR_MED_SEV,
    FORM_RECALL_FLOOR_HIGH_SEV,
    FORM_RECALL_FLOOR_MED_SEV,
    GATE0_TARGET_ACCURACY,
    LIVE_CUE_MAX_WORDS,
    PHANTOM_REPS_MUST_BE_ZERO,
    SUBJECT_LOCK_FLOOR,
    VIEW_ACC_MAX_GAP,
    load_exercise_library,
)

__all__ = [
    "FORM_PRECISION_FLOOR_HIGH_SEV",
    "FORM_PRECISION_FLOOR_MED_SEV",
    "FORM_RECALL_FLOOR_HIGH_SEV",
    "FORM_RECALL_FLOOR_MED_SEV",
    "GATE0_TARGET_ACCURACY",
    "LIVE_CUE_MAX_WORDS",
    "PHANTOM_REPS_MUST_BE_ZERO",
    "SUBJECT_LOCK_FLOOR",
    "VIEW_ACC_MAX_GAP",
    "load_exercise_library",
]
