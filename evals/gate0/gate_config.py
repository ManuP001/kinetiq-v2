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
    FITNESS_LEVEL_DEFAULT_SETS_REPS,
    FORM_PRECISION_FLOOR_HIGH_SEV,
    FORM_PRECISION_FLOOR_MED_SEV,
    FORM_RECALL_FLOOR_HIGH_SEV,
    FORM_RECALL_FLOOR_MED_SEV,
    FORM_SCORE_PENALTY_PER_FLAG,
    FLAG_BOTTOM_PHASE_FRACTION,
    FLAG_HYSTERESIS_MIN_FRACTION_HIGH_SEV,
    FLAG_HYSTERESIS_MIN_FRACTION_LOW_SEV,
    FLAG_HYSTERESIS_MIN_FRACTION_MED_SEV,
    FLAG_MIN_EVALUABLE_FRAMES,
    FLAG_MIN_VISIBILITY,
    GATE0_TARGET_ACCURACY,
    GRADED_DEPTH_FORM_SCORE_FLOOR,
    HUMAN_LIMB_RATIO_MAX,
    HUMAN_LIMB_RATIO_MIN,
    LIVE_CUE_MAX_WORDS,
    MAX_REP_DURATION_MS,
    MIN_KEYPOINT_VISIBILITY,
    MIN_REP_DURATION_MS,
    MIN_VISIBLE_KEYPOINT_FRACTION,
    PHANTOM_REPS_MUST_BE_ZERO,
    POSE_MODEL_CANDIDATES,
    REP_COUNTER_HYSTERESIS_DEG,
    REP_COUNTER_SMOOTHING_WINDOW_FRAMES,
    REP_COUNTER_TOP_ANGLE_DEG,
    REP_MIN_EXCURSION_DEG,
    SUBJECT_LOCK_FLOOR,
    SUBJECT_LOST_FRAMES_THRESHOLD,
    SUBJECT_REID_MAX_CENTROID_DIST,
    SUBJECT_SELECTION_RULE,
    VIEW_ACC_MAX_GAP,
    load_exercise_library,
)

__all__ = [
    "FITNESS_LEVEL_DEFAULT_SETS_REPS",
    "FORM_PRECISION_FLOOR_HIGH_SEV",
    "FORM_PRECISION_FLOOR_MED_SEV",
    "FORM_RECALL_FLOOR_HIGH_SEV",
    "FORM_RECALL_FLOOR_MED_SEV",
    "FORM_SCORE_PENALTY_PER_FLAG",
    "FLAG_BOTTOM_PHASE_FRACTION",
    "FLAG_HYSTERESIS_MIN_FRACTION_HIGH_SEV",
    "FLAG_HYSTERESIS_MIN_FRACTION_LOW_SEV",
    "FLAG_HYSTERESIS_MIN_FRACTION_MED_SEV",
    "FLAG_MIN_EVALUABLE_FRAMES",
    "FLAG_MIN_VISIBILITY",
    "GATE0_TARGET_ACCURACY",
    "GRADED_DEPTH_FORM_SCORE_FLOOR",
    "HUMAN_LIMB_RATIO_MAX",
    "HUMAN_LIMB_RATIO_MIN",
    "LIVE_CUE_MAX_WORDS",
    "MAX_REP_DURATION_MS",
    "MIN_KEYPOINT_VISIBILITY",
    "MIN_REP_DURATION_MS",
    "MIN_VISIBLE_KEYPOINT_FRACTION",
    "PHANTOM_REPS_MUST_BE_ZERO",
    "POSE_MODEL_CANDIDATES",
    "REP_COUNTER_HYSTERESIS_DEG",
    "REP_COUNTER_SMOOTHING_WINDOW_FRAMES",
    "REP_COUNTER_TOP_ANGLE_DEG",
    "REP_MIN_EXCURSION_DEG",
    "SUBJECT_LOCK_FLOOR",
    "SUBJECT_LOST_FRAMES_THRESHOLD",
    "SUBJECT_REID_MAX_CENTROID_DIST",
    "SUBJECT_SELECTION_RULE",
    "VIEW_ACC_MAX_GAP",
    "load_exercise_library",
]
