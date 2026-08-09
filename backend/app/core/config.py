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
