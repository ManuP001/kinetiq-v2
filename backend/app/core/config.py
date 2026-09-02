"""
backend/app/core/config.py

Named constants for the Kinetiq v2 backend (CLAUDE.md §3: "All constants — model names,
thresholds, latency budgets, streak windows — live in backend/app/core/config.py. No magic
numbers inline, anywhere.").

Design principle: this file holds GLOBAL / cross-cutting constants only. It deliberately does
NOT hand-copy per-exercise numeric thresholds (knee_cave_x, torso_lean_max_deg, etc.) — those
live solely in exercises/*.json (CLAUDE.md §6), loaded at runtime via load_exercise_library().
Duplicating them here was exactly the failure mode that caused kinetiq-demo2's CONFIG object to
drift out of sync with exercises/*.json and the Vision_Contract spreadsheet (see CHANGELOG 0.3.0)
— one source of truth per value, always.

No pyproject.toml/requirements.txt exists in this repo yet, so this module is stdlib-only
(no pydantic-settings). Model-name keys read from the environment with a default so they're
env-overridable later without adding a dependency now.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# ─── Model tiering (CLAUDE.md §5.1, ADR-100, ADR-104) ────────────────────────────
# Model names are config keys, never literals, per CLAUDE.md §5.1.

# Hot path (<120ms, per-rep form scoring) is deterministic + on-device — there is no LLM call
# here at all (ADR-100). None (not a model-name string) so nothing downstream mistakes this for
# a real model to call.
HOT_PATH_MODEL: str | None = None

# Warm path (<600ms): set summaries, live nuance. Cheap/Haiku-class.
COACHING_MODEL: str = os.getenv("COACHING_MODEL", "claude-haiku-4-5-20251001")

# Cold path (async, seconds): weekly recap, re-engagement, plan generation. Strong/Sonnet-class.
PLANNER_MODEL: str = os.getenv("PLANNER_MODEL", "claude-sonnet-5")

# Cold path (async batch): memory synthesis / form-trend narratives. Strong/Sonnet-class.
MEMORY_MODEL: str = os.getenv("MEMORY_MODEL", "claude-sonnet-5")
# NOTE: the four defaults above are placeholders to confirm/pin once the actual API client is
# wired up — not a verified production model selection.

# ─── Latency budgets (CLAUDE.md §5.1 table) ──────────────────────────────────────
HOT_PATH_LATENCY_BUDGET_MS: int = 120
WARM_PATH_LATENCY_BUDGET_MS: int = 600
# Cold path is "seconds, async" per CLAUDE.md — not latency-bound, so no hard numeric budget is
# defined here; it would be a fake precision.

# ─── Coaching (CLAUDE.md §5.3) ────────────────────────────────────────────────────
LIVE_CUE_MAX_WORDS: int = 8
SET_SUMMARY_MAX_WORDS: int = 30
# Confidence >= this -> directive delivery ("Push your left knee out"); below -> suggestion
# delivery ("Try tracking your knee over your toe").
COACHING_DIRECTIVE_CONFIDENCE_THRESHOLD: float = 0.75

# Model-assisted form layer (ADR-100/102): "low confidence falls back to deterministic" is
# specified qualitatively but no number is given anywhere in PRD_v2/ARCHITECTURE.md. Placeholder
# pending the Phase 2 expert-agreement eval (ADR-102) — revisit once that eval exists.
MODEL_ASSIST_MIN_CONFIDENCE: float = 0.6

# max_tokens per model call: CLAUDE.md §4 mandates always setting this, but gives no numbers.
# Conservative placeholders — revisit once real prompts exist in prompts/.
COACHING_MAX_TOKENS: int = 150
PLANNER_MAX_TOKENS: int = 2000
MEMORY_MAX_TOKENS: int = 1000

# ─── Streaks (PRD_v2 §9.2) ────────────────────────────────────────────────────────
STREAK_TIMEZONE: str = "Asia/Kolkata"  # UTC+5:30, per PRD_v2 §9.2
STREAK_MIN_SETS_TO_COUNT: int = 1
STREAK_RESET_WINDOW_HOURS: int = 36  # buffer for timezone variance / late-night sessions
STREAK_MILESTONE_DAYS: tuple[int, ...] = (3, 7, 14, 30)
# Phase 3 behaviour (streak recovery), but schema-ready now per ADR-105's "full schema now,
# behaviour by phase" pattern — not gated out of this file.
STREAK_FREEZE_PER_MONTH: int = 1

# ─── Personal records (PRD_v2 §9.2) ───────────────────────────────────────────────
# A "most reps in a set" PR only counts if the set's form score exceeds this.
PR_REPS_MIN_FORM_SCORE: float = 7.0

# ─── Notifications (ADR-108) ──────────────────────────────────────────────────────
STREAK_RISK_PUSH_DEFAULT_TIME: str = "19:00"  # configurable per-user; this is the default
MAX_PUSH_NOTIFICATIONS_PER_DAY: int = 1

# ─── Session duration (PRD_v2 §8.2; DB: 001_initial_schema_v2.sql users table) ───
# UI offers a curated subset of the DB's wider allowed range (CHECK BETWEEN 5 AND 120) —
# not a conflict, just a smaller set of user-facing choices within a wider validated bound.
SESSION_DURATION_OPTIONS_MINUTES: tuple[int, ...] = (10, 15, 20, 30)
SESSION_DURATION_DEFAULT_MINUTES: int = 15

# ─── Fitness-level defaults (PRD_v2 §8.5) ─────────────────────────────────────────
# (default_sets, default_reps) per fitness_level. Keyed by the same literal values as
# app.core.schemas.FitnessLevel (import is safe: schemas.py has no imports from this module).
FITNESS_LEVEL_DEFAULT_SETS_REPS: dict[str, tuple[int, int]] = {
    "beginner": (2, 8),
    "intermediate": (3, 10),
    "advanced": (4, 12),
}

# ─── Form score bounds ────────────────────────────────────────────────────────────
# Deliberately NOT redefined here. Already enforced in two places — app.core.schemas
# (Field(ge=0.0, le=10.0)) and the SQL CHECK constraints in 001_initial_schema_v2.sql — and a
# third copy here would risk exactly the kind of threshold drift fixed in CHANGELOG 0.3.0.

# ─── Free tier ─────────────────────────────────────────────────────────────────────
# Documents current state (all 3 seeded MVP exercises are is_premium=false in
# 002_seed_exercises_v2.sql), not a hardcoded business rule about "3 free exercises" as a limit.
FREE_TIER_EXERCISE_IDS: tuple[str, ...] = ("squat", "pushup", "lunge")

# ─── Gate 0 (ADR-110) ──────────────────────────────────────────────────────────────
# Also imported by evals/gate0/aggregate.py so both share one source of truth.
GATE0_TARGET_ACCURACY: float = 0.90

# ─── Stage 0 eval gate floors (EVAL_HARNESS_STAGE0_SPEC.md §8) ───────────────────
# Single source of truth for the Stage-0 eval harness gate. Imported by
# evals/gate0/aggregate.py (like GATE0_TARGET_ACCURACY) — never re-hardcode these numbers in the
# harness or the spec docs; reference them by name.
PHANTOM_REPS_MUST_BE_ZERO: bool = True    # any rep on a phantom/empty clip -> hard fail
SUBJECT_LOCK_FLOOR: float = 0.99          # min fraction of frames tracking the right person

# Form flags are graded by fault severity (EXERCISE_LIBRARY.md §4: high | med | low).
# Precision floors guard against false accusations; high-severity must never accuse a good rep.
FORM_PRECISION_FLOOR_HIGH_SEV: float = 0.90
FORM_PRECISION_FLOOR_MED_SEV: float = 0.75
# Recall floors are precision-first: high-severity tolerates MORE misses (a lower recall bar) so it
# can hold its strict precision floor without over-flagging. low-severity has no enforced floor.
FORM_RECALL_FLOOR_HIGH_SEV: float = 0.60
FORM_RECALL_FLOOR_MED_SEV: float = 0.70

VIEW_ACC_MAX_GAP: float = 0.10            # max rep-acc spread across front/side/diagonal

# ─── Stage 1 detector: subject-lock (VISION_ARCHITECTURE.md Stage 1, fixes RC1) ──
# How the offline reference detector (evals/gate0/detector/) picks the initial locked subject
# when multiple people are visible at session start, and how it decides "lost" vs "still the same
# person returning after a blip". Never re-hardcode in detector code — import from here.
SUBJECT_SELECTION_RULE: str = "largest_bbox"  # "largest_bbox" | "most_central"
# Consecutive frames without a plausible match to the locked identity before the detector
# declares the subject lost and PAUSES rep counting (VISION_ARCHITECTURE.md: "pause, don't
# silently retarget"). ~0.3s at a nominal 30fps clip: long enough to ride out a single dropped
# detection / brief occlusion blip, short enough that a real disappearance is caught quickly.
# Reference-detector default -- revisit once real drop-out statistics exist from field data.
SUBJECT_LOST_FRAMES_THRESHOLD: int = 10
# Normalized [0,1] frame-fraction distance: how close a newly-detected person's bbox centroid
# must be to the locked subject's last-known centroid to be accepted as "the same person
# returning" rather than "a different person happens to be nearby". Deliberately tight -- the
# whole point of subject-lock is to never retarget to whoever is merely next-most-prominent.
SUBJECT_REID_MAX_CENTROID_DIST: float = 0.15

# ─── Stage 1 detector: rep-validity gate (VISION_ARCHITECTURE.md Stage 3, fixes RC2) ──
# A landmark below this visibility doesn't count as "seen" for plausibility/angle purposes.
MIN_KEYPOINT_VISIBILITY: float = 0.5
# Fraction of the detector's scoped landmark set (shoulders/elbows/wrists/hips/knees/ankles --
# see detector/keypoint_map.py) that must be visible for a frame to be treated as a plausible
# human at all. Below this: reject the frame outright (e.g. a heavily-occluded or non-human blob
# such as a bench mistaken for a person by an upstream detector).
MIN_VISIBLE_KEYPOINT_FRACTION: float = 0.6
# A plausible human's shin length (knee->ankle) vs thigh length (hip->knee) falls in this ratio
# band (real humans run roughly 0.9-1.1; this is deliberately generous to avoid false rejections
# from ordinary pose noise while still catching wildly wrong geometry).
HUMAN_LIMB_RATIO_MIN: float = 0.5
HUMAN_LIMB_RATIO_MAX: float = 2.0
# Plausible tempo band for one full rep cycle. Below MIN: too fast to be a real human rep (motion
# jitter). Above MAX: not one continuous rep (e.g. drifted or paused mid-motion). MAX is
# deliberately generous -- EVAL_STRATEGY.md case #6 requires a slow (3-0-1-0 tempo) rep to still
# register.
MIN_REP_DURATION_MS: int = 400
MAX_REP_DURATION_MS: int = 12000

# ─── Stage 1 detector: rep counter (VISION_ARCHITECTURE.md Stage 4, fixes RC4/RC6) ──
# Median-filter window (frames) over the primary joint-angle signal (knee angle for
# squat/lunge, elbow angle for pushup) before phase/valley detection, to absorb per-frame pose
# jitter.
REP_COUNTER_SMOOTHING_WINDOW_FRAMES: int = 5
# A phase reversal must clear this margin (degrees) before it's accepted as a genuine
# direction change, so noise near a local extremum doesn't register as multiple micro-reps.
REP_COUNTER_HYSTERESIS_DEG: float = 5.0
# Near-full-extension angle treated as "top" phase for knee/elbow-angle-driven exercises.
REP_COUNTER_TOP_ANGLE_DEG: float = 160.0
# An excursion (top angle - local minimum) smaller than this is fidget/noise, not a rep attempt --
# it must not count at all (this is the floor below "partial", not a partial-rep bar itself).
REP_MIN_EXCURSION_DEG: float = 20.0
# A countable-but-very-shallow rep still gets at least this form_score out of 10 rather than 0 --
# "counts with a lower score" (graded depth), not punished as if it were a fault-ridden rep.
GRADED_DEPTH_FORM_SCORE_FLOOR: float = 3.0
# Flat, deterministic form_score deduction per triggered fault flag on a rep (Stage-4's learned
# model replaces this with a calibrated score; this is the Stage-1 placeholder).
FORM_SCORE_PENALTY_PER_FLAG: float = 2.5

# ─── Stage 2 pose-model bake-off (VISION_ARCHITECTURE.md Stage 2 / §5, ROADMAP.md Stage 2) ──
# Single source of truth for which pose models the bake-off compares -- both
# evals/gate0/detector/pose_capture/ (which candidate to capture) and aggregate.py's
# --compare-pose-models table iterate this registry. No model name/weights/runtime is
# hardcoded anywhere else; add a new candidate here (and its keypoint_map.py mapping) to extend
# the bake-off.
#
# "name" is the single canonical identifier used everywhere: the keypoints.jsonl pose_model
# field, the golden/poses/<name>/ directory, and detector/keypoint_map.py's POSE_MODEL_LANDMARKS
# key. dimensionality is "2d" (image-plane only, z always null) or "3d" (world landmarks
# populate z) -- see VISION_ARCHITECTURE.md §2 on why 3D world landmarks are one of the
# candidates for fixing the front/side rep-count gap (RC5). approx_size_mb is None until someone
# actually installs the runtime and measures the weights file(s) -- never a guessed number; the
# bake-off table prints "n/a" rather than a fabricated size.
#
# ADR-300 (ARCHITECTURE.md): every candidate must yield ALL people in frame, not just top-1, or
# subject-lock (RC1) has nothing to choose among. multi_person is True for every candidate below
# -- a candidate that can't satisfy this is out of the bake-off per the ADR. person_detector names
# the external detector a top-down pose model is paired with (null for a natively multi-person
# model). multi_person_config carries the exact knobs a capture adapter needs to reproduce the
# multi-person configuration -- never re-derive/guess these from the adapter code.
POSE_MODEL_CANDIDATES: tuple[dict[str, Any], ...] = (
    {
        "name": "blazepose_33",
        "landmark_count": 33,
        "dimensionality": "3d",
        "runtime": "mediapipe",
        "weights_ref": "MediaPipe Tasks PoseLandmarker (BlazePose GHUM, 'full' complexity)",
        "approx_size_mb": 9.0,  # pose_landmarker_full float16 .task, live-measured 2026-09-01.
        "multi_person": True,
        "person_detector": None,  # natively multi-person via num_poses > 1.
        "multi_person_config": {"num_poses": 2},
    },
    {
        "name": "movenet_17",
        "landmark_count": 17,
        "dimensionality": "2d",
        "runtime": "tensorflow",
        # ADR-300: SinglePose Thunder (the pre-ADR-300 choice) returns exactly one pose and can't
        # feed subject-lock at all -- replaced with the MultiPose variant. Lightning (not Thunder)
        # is TF Hub's only MultiPose variant as of this bake-off; there is no MultiPose Thunder.
        "weights_ref": "TensorFlow Hub MoveNet MultiPose Lightning",
        "approx_size_mb": None,
        "multi_person": True,
        "person_detector": None,  # natively multi-person (fixed 6-instance output).
        "multi_person_config": {
            "variant": "multipose_lightning",
            "max_instances": 6,  # fixed by the model's output_0 shape [1, 6, 56].
            # Filters MultiPose's fixed 6 output slots down to slots the model actually
            # populated (score column 55 of each 56-wide row) -- a structural "is this slot a
            # real detection" gate, not a Stage-3 form-flagging confidence cutoff. Left at TF
            # Hub's own tutorial default; not tuned against golden-set data (PARALLEL_PLAN.md
            # blocks value tuning until real recordings land).
            "instance_score_threshold": 0.1,
        },
    },
    {
        "name": "rtmpose_halpe26",
        "landmark_count": 26,
        "dimensionality": "2d",
        "runtime": "rtmlib",
        # RTMPose-m over plain-COCO: Halpe-26 (the combined "Body8" training set) adds head/neck/
        # hip-center/toe/heel points, closer to BlazePose's richness -- see
        # evals/gate0/README.md's bake-off section for the reasoning behind this choice. Halpe-26
        # lives behind rtmlib's `BodyWithFeet` class specifically -- `Body` (despite the similar
        # name) loads plain-COCO-17 weights; live-verified 2026-09-01 (pose_capture/README.md).
        "weights_ref": "RTMPose-m, Halpe-26 (body7-halpe26 weights, mmpose model zoo, via rtmlib BodyWithFeet)",
        "approx_size_mb": None,
        "multi_person": True,
        "person_detector": "yolox (rtmlib-bundled, runs internally)",  # top-down.
        "multi_person_config": {"mode": "balanced"},
    },
)

# ─── Stage 3 flag-level hysteresis + visibility gating (SPRINT.md G2 "precision-first flagging";
# VISION_ERROR_ANALYSIS.md RC4 -- the field hip-sag false positive: a flag tripping on one noisy
# frame). detector/faults.py's per-frame rules stay exactly as-is; this governs WHEN a fault that
# rule finds is sustained enough to actually commit to a rep, and gates each flag's own evidence
# by ITS involved landmarks' visibility (distinct from MIN_VISIBLE_KEYPOINT_FRACTION's coarser
# whole-body plausibility check above).
#
# PLACEHOLDER VALUES -- these are NOT tuned against real data. They exist so the mechanism can be
# built, tested, and wired into the harness now; the real numbers come from the golden set
# (GOLDEN_SET_PROTOCOL.md §8) once it exists. Do not treat them as calibrated.
#
# A landmark below this visibility isn't usable evidence for a flag's rule on that frame.
FLAG_MIN_VISIBILITY: float = 0.5
# A rep needs at least this many visibility-passing (evaluable) frames for a given flag before the
# detector will assert OR deny it at all; below this the flag reports "insufficient evidence"
# rather than a guess from too little data (surfaced, never silently dropped).
FLAG_MIN_EVALUABLE_FRAMES: int = 3
# Fraction of a flag's evaluable frames in which the fault must be present before it commits to
# the rep -- fps-robust by design (chosen over a fixed frame count so the same config behaves
# consistently across devices/frame rates; the device x lighting matrix spans multiple real
# phones). Severity-keyed and precision-first (SPRINT.md G2): high-severity requires the LARGEST
# sustained fraction, trading missed faults for never falsely accusing a good rep on a safety-
# relevant flag; low-severity is the most lenient (advisory, already has no enforced P/R floor).
FLAG_HYSTERESIS_MIN_FRACTION_HIGH_SEV: float = 0.6
FLAG_HYSTERESIS_MIN_FRACTION_MED_SEV: float = 0.4
FLAG_HYSTERESIS_MIN_FRACTION_LOW_SEV: float = 0.3
# For a flag whose rule the exercise library declares bottom-phase-only (e.g. squat's
# shallow_depth: phase_detected_in == ["bottom"]) -- the fraction of THIS rep's OWN excursion
# range (top reference angle down to its minimum) treated as "the bottom phase" for sustained
# evaluation. Self-relative to the rep's own excursion, not the exercise's correct-depth
# threshold: a partial-depth rep still has a genuine bottom (its own minimum), even though that
# minimum never reaches the "correct" band -- gating on the correct-depth threshold instead would
# make a shallow rep's bottom-phase window empty and the flag permanently unassertable for
# exactly the reps it exists to catch.
FLAG_BOTTOM_PHASE_FRACTION: float = 0.2

# ─── Exercise library loader (CLAUDE.md §6) ───────────────────────────────────────
# kinetiq-v2/backend/app/core/config.py -> parents[3] == kinetiq-v2/
EXERCISE_LIBRARY_DIR: Path = Path(__file__).resolve().parents[3] / "exercises"


def load_exercise_library(directory: Path | None = None) -> dict[str, dict[str, Any]]:
    """Load every exercises/*.json file, keyed by exercise_id.

    This is the single mechanism for exposing per-exercise thresholds/cues/contraindications to
    the backend — see the module docstring for why they aren't duplicated as constants here.
    """
    lib_dir = directory or EXERCISE_LIBRARY_DIR
    library: dict[str, dict[str, Any]] = {}
    for path in sorted(lib_dir.glob("*.json")):
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        library[data["exercise_id"]] = data
    return library
