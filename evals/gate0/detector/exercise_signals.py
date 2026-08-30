#!/usr/bin/env python3
"""
evals/gate0/detector/exercise_signals.py

Per-exercise mapping from "which joint angle drives this exercise's phase machine" to actual
keypoints, and "what counts as full depth" per the exercise's own library entry. This is
structural/algorithmic code (which anatomical landmarks matter for which exercise), not a
tunable numeric threshold -- the numbers themselves (bottom-angle bands, x/z thresholds for
faults) still come from exercises/*.json, never restated here (CLAUDE.md §3).

Scope: squat, pushup, lunge only (ROADMAP.md Stage 1 is scoped to the 3 already-instrumented
exercises; the 11 requested additions are Stage 5, gated one at a time). Extending this table to
a new exercise means adding one PrimaryJoint entry and a bottom-threshold lookup for it -- both
called out explicitly if this raises KeyError for an unscoped exercise, rather than silently
guessing.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from detector.geometry import angle_deg
from detector.keypoint_map import get_point


@dataclass(frozen=True)
class PrimaryJoint:
    """The (proximal, vertex, distal) landmark-name triple whose angle at `vertex` drives this
    exercise's phase machine -- e.g. hip-knee-ankle for squat, so the knee angle is the signal."""
    left: Tuple[str, str, str]
    right: Tuple[str, str, str]


PRIMARY_JOINTS: Dict[str, PrimaryJoint] = {
    "squat": PrimaryJoint(
        left=("left_hip", "left_knee", "left_ankle"),
        right=("right_hip", "right_knee", "right_ankle"),
    ),
    "lunge": PrimaryJoint(
        left=("left_hip", "left_knee", "left_ankle"),
        right=("right_hip", "right_knee", "right_ankle"),
    ),
    "pushup": PrimaryJoint(
        left=("left_shoulder", "left_elbow", "left_wrist"),
        right=("right_shoulder", "right_elbow", "right_wrist"),
    ),
}

# Where each exercise's "correct bottom" angle band lives in its exercises/*.json entry -- the
# three files use two different shapes (CLAUDE.md's "one source of truth per value" holds; this
# is just reading two different existing shapes, not a new inconsistency introduced here).
_BOTTOM_ANGLE_MAX_LOOKUP = {
    # squat.json puts the bottom band under reference_keypoints.correct.key_angles.*_at_bottom.
    "squat": lambda ex: ex["reference_keypoints"]["correct"]["key_angles"][
        "left_knee_angle_at_bottom"
    ]["max"],
    # pushup.json / lunge.json put a single named bottom-max directly under thresholds.
    "pushup": lambda ex: ex["thresholds"]["depth_elbow_angle_max"],
    "lunge": lambda ex: ex["thresholds"]["front_knee_angle_bottom_max"],
}


def scoped_exercises() -> Tuple[str, ...]:
    return tuple(PRIMARY_JOINTS.keys())


def get_bottom_angle_max(exercise_id: str, exercise_json: Dict[str, Any]) -> float:
    """The angle (degrees) at/below which this exercise's primary joint counts as having
    reached full expected depth -- used only for graded-depth scoring, never for gating whether
    a rep counts at all (that's REP_MIN_EXCURSION_DEG in config.py)."""
    try:
        lookup = _BOTTOM_ANGLE_MAX_LOOKUP[exercise_id]
    except KeyError:
        raise KeyError(
            f"exercise_signals is scoped to {scoped_exercises()}; {exercise_id!r} needs its own "
            f"bottom-angle lookup added before Stage 1 can score it"
        ) from None
    return float(lookup(exercise_json))


def primary_angle(person: Dict[str, Any], pose_model: str, exercise_id: str) -> Optional[float]:
    """The exercise's primary joint angle for this person/frame, averaged over whichever side(s)
    have all three landmarks visible enough to compute an angle. None if neither side qualifies
    (get_point already returns None below MIN_KEYPOINT_VISIBILITY doesn't apply here -- visibility
    filtering is plausibility.py's job; this just needs the coordinates to exist)."""
    joints = PRIMARY_JOINTS.get(exercise_id)
    if joints is None:
        raise KeyError(
            f"exercise_signals is scoped to {scoped_exercises()}; {exercise_id!r} needs a "
            f"PrimaryJoint entry added before Stage 1 can compute its phase signal"
        )
    angles = []
    for triple in (joints.left, joints.right):
        points = [get_point(person, pose_model, name) for name in triple]
        if any(p is None for p in points):
            continue
        a, b, c = ((p[0], p[1]) for p in points)
        angles.append(angle_deg(a, b, c))
    if not angles:
        return None
    return sum(angles) / len(angles)
