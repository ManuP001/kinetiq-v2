#!/usr/bin/env python3
"""
evals/gate0/detector/adapter.py

The `run_detector(keypoints_stream, exercise_id, config) -> DetectedClip` adapter
(EVAL_HARNESS_STAGE0_SPEC.md §5, deferred to Stage 1 by §12). Orchestrates the specialists in
VISION_ARCHITECTURE.md order:

  1. subject-lock (Stage 1)          -- who is the subject, per frame, or None/paused.
  2. rep-validity gate (Stage 3)     -- human-plausibility per frame; a locked-but-implausible
                                         frame (e.g. a bench a naive detector boxed as a person)
                                         contributes no signal, regardless of lock status.
  3. rep counter (Stage 4)           -- valley-detection FSM over the surviving angle signal.
  4. deterministic form-flag rules   -- unchanged "as-is" rule set (Stage 4/5 learned model is
                                         out of scope here), evaluated at each rep's deepest point.
  5. deterministic safety veto (5b)  -- a rep the validity gate rejected can never be
                                         resurrected by anything downstream; there is nothing
                                         downstream of the validity gate that CAN override it,
                                         which is the veto property by construction, not an
                                         extra check bolted on.

run_detector itself never sees ground truth (no labels, no "expected subject") -- it can only
know what a real detector could know: the keypoints stream, the exercise, and config. Comparing
its chosen subject identity against a golden clip's labeled "expected" subject is a *grading*
step and deliberately lives outside this function (see score_subject_lock_against_expected
below) -- smuggling the answer key into the detector would make the eval meaningless.

Determinism: every step here is a pure function of its inputs (no randomness, no wall-clock, no
I/O) -- the same keypoints_stream always produces the same DetectedClip.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

import gate_config
from detector.exercise_signals import get_bottom_angle_max, primary_angle, scoped_exercises
from detector.faults import lunge_faults, pushup_faults, squat_faults
from detector.plausibility import PlausibilityConfig, is_plausible_human
from detector.rep_counter import RepCounterConfig, count_reps
from detector.subject_lock import track_subject

DETECTOR_VERSION = "kinetiq-v3-stage1-reference"


@dataclass(frozen=True)
class DetectorConfig:
    """Bundles every Stage-1 tunable in one place so run_detector's `config` parameter can
    override behaviour end-to-end (e.g. for a threshold-sensitivity sweep) without touching
    global config.py. Every field defaults from config.py via gate_config."""
    subject_selection_rule: str = gate_config.SUBJECT_SELECTION_RULE
    subject_lost_frames_threshold: int = gate_config.SUBJECT_LOST_FRAMES_THRESHOLD
    subject_reid_max_centroid_dist: float = gate_config.SUBJECT_REID_MAX_CENTROID_DIST
    plausibility: PlausibilityConfig = field(default_factory=PlausibilityConfig)
    rep_counter: RepCounterConfig = field(default_factory=RepCounterConfig)
    graded_depth_form_score_floor: float = gate_config.GRADED_DEPTH_FORM_SCORE_FLOOR
    form_score_penalty_per_flag: float = gate_config.FORM_SCORE_PENALTY_PER_FLAG


@dataclass
class DetectedRep:
    idx: int
    flags: List[str]
    form_score: float


@dataclass
class DetectedClip:
    detected_reps: int
    reps: List[DetectedRep]
    frames_total: int
    subject_track_sequence: List[Optional[int]]  # per-frame locked track_id, or None
    coaching_cues: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "detected_reps": self.detected_reps,
            "reps": [
                {"idx": r.idx, "flags": r.flags, "form_score": r.form_score} for r in self.reps
            ],
            "coaching_cues": self.coaching_cues,
        }


def _evaluate_faults(
    exercise_id: str,
    person: Dict[str, Any],
    pose_model: str,
    exercise_json: Dict[str, Any],
    rep_min_angle: float,
) -> List[str]:
    if exercise_id == "squat":
        return squat_faults(person, pose_model, exercise_json)
    if exercise_id == "pushup":
        return pushup_faults(person, pose_model, exercise_json, rep_min_angle)
    if exercise_id == "lunge":
        return lunge_faults(rep_min_angle, exercise_json)
    raise KeyError(
        f"detector.faults is scoped to {scoped_exercises()}; {exercise_id!r} needs its own "
        f"fault evaluator added before Stage 1 can score its form"
    )


def _nearest_valid_frame(
    frame_lookup: Dict[int, tuple], t_ms: int
) -> tuple:
    """The person/pose_model at t_ms, or -- if that exact timestamp has no valid entry -- the
    nearest one that does. This matters because the smoothed angle signal (median_filter) can
    report its minimum at a timestamp whose OWN raw frame was a gap (implausible/unlocked),
    filled in only via its neighbours; there is still a real nearby frame worth evaluating form
    faults against, so we use it rather than silently emitting no flags at all."""
    if t_ms in frame_lookup:
        return frame_lookup[t_ms]
    if not frame_lookup:
        return (None, None)
    nearest_t = min(frame_lookup, key=lambda t: abs(t - t_ms))
    return frame_lookup[nearest_t]


def _depth_form_score(
    top_ref_deg: float, min_angle_deg: float, bottom_max_deg: float, config: DetectorConfig
) -> float:
    """Graded depth (EVAL_STRATEGY.md case #5): a countable rep always scores somewhere in
    [floor, 10] based on how close it got to the exercise's own correct-bottom band, never 0 just
    for being shallow -- a fault-flag penalty is applied separately, on top of this."""
    span = top_ref_deg - bottom_max_deg
    if span <= 0:
        depth_fraction = 1.0
    else:
        depth_fraction = (top_ref_deg - min_angle_deg) / span
    depth_fraction = max(0.0, min(1.0, depth_fraction))
    floor = config.graded_depth_form_score_floor
    return floor + (10.0 - floor) * depth_fraction


def run_detector(
    keypoints_stream: Sequence[Dict[str, Any]],
    exercise_id: str,
    config: Optional[DetectorConfig] = None,
) -> DetectedClip:
    """keypoints_stream: parsed keypoints.jsonl frames, in ascending t_ms order (each a dict with
    t_ms/pose_model/people, per EVAL_HARNESS_STAGE0_SPEC.md §5). Deterministic: same input,
    same output."""
    cfg = config or DetectorConfig()
    frames = list(keypoints_stream)
    frames_total = len(frames)

    exercise_json = gate_config.load_exercise_library().get(exercise_id)
    if exercise_json is None:
        raise KeyError(f"{exercise_id!r} is not in the exercise library")

    locks = track_subject(
        frames,
        selection_rule=cfg.subject_selection_rule,
        lost_frames_threshold=cfg.subject_lost_frames_threshold,
        reid_max_centroid_dist=cfg.subject_reid_max_centroid_dist,
    )

    subject_track_sequence: List[Optional[int]] = []
    samples: List[tuple] = []  # (t_ms, angle_or_None)
    frame_lookup: Dict[int, tuple] = {}  # t_ms -> (person, pose_model)

    for frame, lock in zip(frames, locks):
        subject_track_sequence.append(lock.track_id if lock.person is not None else None)

        t_ms = frame["t_ms"]
        pose_model = frame.get("pose_model")
        angle: Optional[float] = None
        if lock.person is not None and is_plausible_human(lock.person, pose_model, cfg.plausibility):
            angle = primary_angle(lock.person, pose_model, exercise_id)
            if angle is not None:
                frame_lookup[t_ms] = (lock.person, pose_model)
        samples.append((t_ms, angle))

    rep_events = count_reps(samples, cfg.rep_counter)
    bottom_max_deg = get_bottom_angle_max(exercise_id, exercise_json)

    reps: List[DetectedRep] = []

    for event in rep_events:
        person, pose_model = _nearest_valid_frame(frame_lookup, event.min_angle_t)
        flags = (
            _evaluate_faults(exercise_id, person, pose_model, exercise_json, event.min_angle_deg)
            if person is not None
            else []
        )
        score = _depth_form_score(event.top_ref_deg, event.min_angle_deg, bottom_max_deg, cfg)
        score -= cfg.form_score_penalty_per_flag * len(flags)
        score = max(0.0, min(10.0, score))
        reps.append(DetectedRep(idx=event.idx, flags=flags, form_score=round(score, 1)))

    return DetectedClip(
        detected_reps=len(reps),
        reps=reps,
        frames_total=frames_total,
        subject_track_sequence=subject_track_sequence,
        # Coaching-cue generation is VISION_ARCHITECTURE.md Stage 6 (the coaching generator),
        # not Stage 1 -- always empty here rather than reusing the exercise library's flag_cues
        # text (which isn't guaranteed to fit the Stage-0 cue-length assertion and isn't this
        # detector's job to author or select).
        coaching_cues=[],
    )


def score_subject_lock_against_expected(
    detected: DetectedClip, expected_track_id: Optional[int]
) -> Dict[str, int]:
    """Harness-side grading only (EVAL_HARNESS_STAGE0_SPEC.md's detected.json subject_lock
    field): compares the detector's autonomously-chosen per-frame identity against the golden
    label's ground-truth subject_track_id. NOT part of run_detector -- a real detector has no
    "expected" identity to compare against, only the one it locked onto. If our
    SUBJECT_SELECTION_RULE picks the wrong person (e.g. a bystander with a bigger box), this is
    exactly where that shows up as a subject-lock failure."""
    frames_total = len(detected.subject_track_sequence)
    if expected_track_id is None:
        return {"frames_total": frames_total, "frames_on_expected_subject": frames_total}
    on_expected = sum(1 for t in detected.subject_track_sequence if t == expected_track_id)
    return {"frames_total": frames_total, "frames_on_expected_subject": on_expected}
