#!/usr/bin/env python3
"""
evals/gate0/prototype_api/schemas.py

The request/response envelope for POST /prototype/assess. `frames` is typed loosely (a list of
plain dicts) deliberately -- the Stage-0 keypoint-frame schema is validate_frame_schema's job
(golden_loader.py, EVAL_HARNESS_STAGE0_SPEC.md §5), not a second, independently-maintained
pydantic schema that could drift from it (CLAUDE.md §3: config/schema is a single source of
truth). main.py calls validate_frame_schema on every frame before anything else happens.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

# Mirrors detector/exercise_signals.scoped_exercises() -- the Stage-1 reference detector's scope
# (ROADMAP.md). Not imported directly to keep this module import-light (no detector/gate_config
# dependency just to define a request schema); main.py cross-checks against the real scope too.
SUPPORTED_EXERCISES = ("squat", "pushup", "lunge")


class AssessRequest(BaseModel):
    session_id: str = Field(min_length=1)
    exercise_id: str
    frames: List[Dict[str, Any]] = Field(default_factory=list)
    reset: bool = False


class AssessResponse(BaseModel):
    rep_count: int
    rep_in_progress: bool
    phase: str
    current_flags: List[str]
    insufficient_evidence: List[str]
    subject_lock_ok: bool
    coaching_cue: Optional[str] = None
    # Not part of the originally-specified 7-field contract -- added to satisfy "flag, don't
    # silently truncate" an over-LIVE_CUE_MAX_WORDS cue (cues.py). None on every normal response.
    cue_warning: Optional[str] = None


class ErrorResponse(BaseModel):
    error: str
    detail: str
