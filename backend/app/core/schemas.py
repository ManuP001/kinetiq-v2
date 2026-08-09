"""
backend/app/core/schemas.py

Canonical Pydantic v2 schemas for the Kinetiq v2 backend.
Single source of truth for the TypeScript types in apps/mobile/src/types/generated.ts.

See API_CONTRACTS.md for the full TypeScript <-> Python contract and ARCHITECTURE.md for the
ADRs these schemas implement. DO NOT add business logic here — schemas are pure data definitions.

v2 changes vs v1:
  - 33-keypoint skeleton (MediaPipe full), up from 17.
  - DerivedFeatures: keypoint-derived numerics for the advisory model layer (ADR-100/101).
  - score_source on assessments/results (deterministic | model_assisted).
  - Health context, equipment, preferred time/duration on the user profile (PRD_v2 §8).
  - PersonalRecord, contraindications, weekly summary, home payload.
"""

from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field

# ─── Literal aliases (kept in one place; mirror the SQL ENUMs) ──────────────────

ExerciseId = Literal["squat", "pushup", "lunge"]
FitnessLevel = Literal["beginner", "intermediate", "advanced"]
ScoreSource = Literal["deterministic", "model_assisted"]
Phase = Literal["ascending", "descending", "bottom", "top", "standing", "unknown"]
HealthCondition = Literal[
    "knee_injury", "back_injury", "shoulder_injury", "hypertension", "diabetes", "none"
]
Equipment = Literal["none", "dumbbells", "resistance_bands", "pull_up_bar", "barbell"]
RecordType = Literal["form_score", "reps_per_set", "total_reps_session"]


# ─── Shared ─────────────────────────────────────────────────────────────────────

class KeyPoint(BaseModel):
    landmark_index: int = Field(ge=0, le=32)  # MediaPipe full-body 33-point skeleton
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    z: float
    visibility: float = Field(ge=0.0, le=1.0)


class DerivedFeatures(BaseModel):
    """Keypoint-derived numerics for the advisory model layer. Never image data (ADR-101)."""
    left_knee_angle: float | None = None
    right_knee_angle: float | None = None
    left_elbow_angle: float | None = None
    right_elbow_angle: float | None = None
    torso_lean_deg: float | None = None
    tempo_ms: int | None = None
    symmetry: float | None = Field(default=None, ge=0.0, le=1.0)
    range_of_motion: float | None = None


# ─── Coaching ───────────────────────────────────────────────────────────────────

class CoachingCue(BaseModel):
    cue_text: str
    cue_type: Literal[
        "form_correction", "encouragement", "set_summary", "safety_warning", "camera_guidance"
    ]
    confidence_level: Literal["directive", "suggestion"]


class ExerciseCoachingCues(BaseModel):
    setup: str
    execution: str
    good_rep: str
    set_complete_no_flags: str
    set_complete_with_flags: str
    flag_cues: dict[str, str] = Field(default_factory=dict)  # keyed by flag_id


# ─── Vision Agent ───────────────────────────────────────────────────────────────

class VisionInput(BaseModel):
    user_id: str
    session_id: str
    exercise_id: ExerciseId
    frame_keypoints: list[KeyPoint] = Field(min_length=17, max_length=33)
    derived_features: DerivedFeatures | None = None
    timestamp_ms: int
    rep_completed: bool = False
    set_completed: bool = False
    current_rep: int = Field(default=0, ge=0)
    current_set: int = Field(default=1, ge=1)


class FormAssessment(BaseModel):
    rep_count: int = Field(ge=0)
    rep_in_progress: bool
    confidence: float = Field(ge=0.0, le=1.0)
    form_flags: list[str]
    form_score: float = Field(ge=0.0, le=10.0)
    score_source: ScoreSource = "deterministic"  # hot path is always deterministic (ADR-100)
    phase: Phase
    coaching_cue: CoachingCue | None = None
    trace_id: str


class CoachingInput(BaseModel):
    session_id: str
    exercise_id: ExerciseId
    form_assessment: FormAssessment
    rep_completed: bool
    set_completed: bool
    coaching_cues: ExerciseCoachingCues
    health_context: list[HealthCondition] = Field(default_factory=list)  # coaching modifier (PRD_v2 §8.4)
    recent_form_summary: str | None = None  # Memory Agent input (Phase 2)
    trace_id: str


# ─── Progress / Gamification ────────────────────────────────────────────────────

class PersonalRecord(BaseModel):
    record_type: RecordType
    exercise_id: str
    value: float
    is_new: bool = False


class SessionSummaryInput(BaseModel):
    user_id: str
    session_id: str
    exercise_id: str
    sets_completed: int = Field(ge=0)
    total_reps: int = Field(ge=0)
    avg_form_score: float = Field(ge=0.0, le=10.0)
    form_flags: dict[str, int] = Field(default_factory=dict)
    duration_seconds: int = Field(ge=0)
    trace_id: str


class SessionResult(BaseModel):
    session_id: str
    avg_form_score: float
    form_flags: dict[str, int]
    streak_day: int
    streak_updated: bool
    personal_records: list[PersonalRecord] = Field(default_factory=list)
    form_score_delta_vs_last: float | None = None  # powers Day-1->Day-2 moment (BR-6)
    completed_at: str  # ISO-8601
    error: str | None = None
    trace_id: str


# ─── Exercise Library ───────────────────────────────────────────────────────────

class Contraindication(BaseModel):
    condition: HealthCondition
    flag: bool
    modification: str
    show_on: list[Literal["exercise_detail", "live_session_start"]]


class Exercise(BaseModel):
    id: str
    name: str
    demo_video_url: str | None = None
    target_muscles: list[str]
    difficulty: FitnessLevel
    equipment: list[str]
    is_premium: bool = False
    coaching_cues: ExerciseCoachingCues | None = None
    estimated_duration_seconds: int | None = None
    active_contraindications: list[Contraindication] = Field(default_factory=list)


# ─── User profile / personalisation (PRD_v2 §8) ────────────────────────────────

class UserProfile(BaseModel):
    fitness_level: FitnessLevel
    goals: list[str] = Field(default_factory=list)
    health_context: list[HealthCondition] = Field(default_factory=list)
    equipment_available: list[Equipment] = Field(default_factory=list)
    preferred_session_time: str | None = None  # "HH:MM"
    preferred_session_duration_minutes: int = Field(default=15, ge=5, le=120)


class HomePayload(BaseModel):
    current_streak: int
    longest_streak: int
    week_dots: list[bool]
    completed_today: bool
    welcome_message: str
    recent_prs: list[PersonalRecord] = Field(default_factory=list)


class WeeklySummary(BaseModel):
    week_of: str  # ISO date
    narrative: str
    sessions_this_week: int
    sessions_prev_week: int
    best_form_score: dict[str, float | str] | None = None
    top_flag: dict[str, int | str] | None = None
    streak_day: int
    challenge: dict[str, str] | None = None


# ─── API request/response wrappers ──────────────────────────────────────────────

class AppliedPersonalisation(BaseModel):
    default_sets: int
    default_reps: int
    health_modifiers: list[HealthCondition] = Field(default_factory=list)


class StartSessionRequest(BaseModel):
    exercise_id: ExerciseId
    sets_target: int = Field(default=3, ge=1, le=10)
    reps_per_set_target: int = Field(default=10, ge=1, le=50)


class StartSessionResponse(BaseModel):
    session_id: str
    exercise_id: str
    started_at: str  # ISO-8601
    applied_personalisation: AppliedPersonalisation
    trace_id: str


class AssessRequest(BaseModel):
    """Inbound body for POST /v2/sessions/{session_id}/assess.
    Narrower than VisionInput — user_id/exercise_id come from session state."""
    frame_keypoints: list[KeyPoint] = Field(min_length=17, max_length=33)
    derived_features: DerivedFeatures | None = None
    timestamp_ms: int
    rep_completed: bool = False
    set_completed: bool = False
    current_rep: int = Field(default=0, ge=0)
    current_set: int = Field(default=1, ge=1)


class CompleteSessionRequest(BaseModel):
    sets_completed: int = Field(ge=0)
    total_reps: int = Field(ge=0)
    duration_seconds: int = Field(ge=0)


class UpdateProfileRequest(BaseModel):
    fitness_level: FitnessLevel | None = None
    goals: list[str] | None = None
    health_context: list[HealthCondition] | None = None
    equipment_available: list[Equipment] | None = None
    preferred_session_time: str | None = None
    preferred_session_duration_minutes: int | None = Field(default=None, ge=5, le=120)


class ErrorResponse(BaseModel):
    error: str
    code: str
    trace_id: str
