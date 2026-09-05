#!/usr/bin/env python3
"""
evals/gate0/detector/faults.py

Deterministic form-flag rules, transliterated from each exercise's own
reference_keypoints.correct.common_errors[].keypoint_signature.rule string into executable
Python. This is the existing rule set "as-is" (per the Stage-1 task brief) -- no new fault
semantics, no threshold tuning. Thresholds are read from the exercise's own thresholds block,
never restated here (CLAUDE.md §3).

Scope, deliberately not exhaustive:
  - squat: knee_cave_left, knee_cave_right, shallow_depth, excess_torso_lean -- all four have a
    complete, unambiguous rule + threshold in squat.json.
  - pushup: elbow_flare, hip_sag, shallow_pushup -- same.
  - lunge: shallow_lunge and excess_torso_lean. lunge.json's front_knee_cave /
    front_knee_overextend are marked status: "unresolved_spec_conflict" in the library itself
    (conflicting with Vision_Contract, "not implemented in kinetiq-demo2 pending trainer/PT-
    confirmed semantics") -- this reference detector leaves them unimplemented for the same reason
    the existing product does, rather than inventing a resolution to a conflict this task didn't
    ask it to resolve.

excess_torso_lean was added later than the rest (2026-09-05) to close a real spec/code gap found by
the CODE_SPEC_MAP.md audit: EXERCISE_LIBRARY.md §3 lists torso lean among both squat's and lunge's
key faults, GOLDEN_SET_PROTOCOL.md §7 tells the PT to label it, and RECORDING_SHOTLIST.md items 15
and 18 deliberately SEED it on lunge clips -- but no common_errors entry existed, so the detector
could never flag it and every seeded instance would have scored as a miss. The rule and both
thresholds were transliterated from kinetiq-demo2's shipped implementation, not invented.

Two kinds of function here:

  - PER-FRAME PREDICATES (knee_cave_left_present, hip_sag_present, etc.) -- one boolean rule per
    fault id, each returning Optional[bool]: True/False if evaluable this frame, None if the
    landmarks it needs aren't present (or, when `min_visibility` is given, aren't visible enough)
    at all. detector/flag_hysteresis.py (Stage 3) calls these once per frame across a rep's
    window to decide whether a fault was SUSTAINED (SPRINT.md G2), rather than a one-frame trip.
    Every predicate takes an optional `min_visibility` parameter (default None = no visibility
    filtering) so the SAME per-side loop serves both a plain "does this rule fire on this
    person record" check and flag_hysteresis.py's visibility-gated evaluation -- for a dual-side
    rule (elbow_flare, hip_sag) this avoids a second, independently-maintained "which side is
    visible" check that could silently disagree about which side's data to trust.
  - REP-AGGREGATE PREDICATES (shallow_pushup_present, shallow_lunge_present) -- compared against
    the rep's overall smoothed minimum angle (from rep_counter.py, already temporally smoothed),
    not any single frame's landmarks. No visibility parameter -- there's no per-frame landmark
    evidence to gate, and no hysteresis either; a rep either was shallow overall or it wasn't.

detector/adapter.py is the only caller: it evaluates the per-frame predicates via
flag_hysteresis.evaluate_sustained_flag() (one call per SUSTAINED_FLAG_IDS entry the exercise
has) and the rep-aggregate predicates directly, then combines both into the rep's final flags.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from detector.geometry import angle_deg, midpoint, torso_lean_deg
from detector.keypoint_map import get_point


def _visible_point(
    person: Dict[str, Any], pose_model: str, name: str, min_visibility: Optional[float]
):
    """get_point(), plus an optional visibility floor: None if the landmark is missing OR (when
    min_visibility is given) below it. min_visibility=None means existence-only (no visibility
    check) -- the default for every predicate below."""
    point = get_point(person, pose_model, name)
    if point is None:
        return None
    if min_visibility is not None and point[3] < min_visibility:
        return None
    return point


def knee_cave_left_present(
    person: Dict[str, Any],
    pose_model: str,
    thresholds: Dict[str, Any],
    min_visibility: Optional[float] = None,
) -> Optional[bool]:
    """squat.json: left knee collapsing medially past the ankle in x."""
    threshold = thresholds.get("knee_cave_x")
    if threshold is None:
        return None
    ankle = _visible_point(person, pose_model, "left_ankle", min_visibility)
    knee = _visible_point(person, pose_model, "left_knee", min_visibility)
    if ankle is None or knee is None:
        return None
    return (ankle[0] - knee[0]) > threshold


def knee_cave_right_present(
    person: Dict[str, Any],
    pose_model: str,
    thresholds: Dict[str, Any],
    min_visibility: Optional[float] = None,
) -> Optional[bool]:
    """squat.json: right knee collapsing medially past the ankle in x."""
    threshold = thresholds.get("knee_cave_x")
    if threshold is None:
        return None
    knee = _visible_point(person, pose_model, "right_knee", min_visibility)
    ankle = _visible_point(person, pose_model, "right_ankle", min_visibility)
    if knee is None or ankle is None:
        return None
    return (knee[0] - ankle[0]) > threshold


def shallow_depth_present(
    person: Dict[str, Any], pose_model: str, min_visibility: Optional[float] = None
) -> Optional[bool]:
    """squat.json: "left_hip.y < left_knee.y AND right_hip.y < right_knee.y at bottom" --
    hip numerically above (smaller y than) knee level means depth wasn't reached. No threshold
    parameter -- this rule compares landmarks to each other, not to a configured value."""
    left_hip = _visible_point(person, pose_model, "left_hip", min_visibility)
    left_knee = _visible_point(person, pose_model, "left_knee", min_visibility)
    right_hip = _visible_point(person, pose_model, "right_hip", min_visibility)
    right_knee = _visible_point(person, pose_model, "right_knee", min_visibility)
    if not all((left_hip, left_knee, right_hip, right_knee)):
        return None
    return left_hip[1] < left_knee[1] and right_hip[1] < right_knee[1]


def elbow_flare_present(
    person: Dict[str, Any],
    pose_model: str,
    thresholds: Dict[str, Any],
    min_visibility: Optional[float] = None,
) -> Optional[bool]:
    """pushup.json: angle(shoulder, elbow, torso_midline) > elbow_flare_deg. "torso_midline" is
    not itself a landmark; the local torso segment (same-side shoulder->hip) is used as the
    reference axis for the angle at the elbow -- a documented interpretation, not an invented
    threshold (the threshold value itself still comes from thresholds.elbow_flare_deg). True if
    EITHER side trips; None only if NEITHER side has enough visible landmarks to judge at all."""
    threshold = thresholds.get("elbow_flare_deg")
    if threshold is None:
        return None
    any_evaluable = False
    for side in ("left", "right"):
        shoulder = _visible_point(person, pose_model, f"{side}_shoulder", min_visibility)
        elbow = _visible_point(person, pose_model, f"{side}_elbow", min_visibility)
        hip = _visible_point(person, pose_model, f"{side}_hip", min_visibility)
        if not all((shoulder, elbow, hip)):
            continue
        any_evaluable = True
        # Angle at the shoulder between the torso axis (shoulder->hip) and the upper arm
        # (shoulder->elbow) -- large angle means the elbow has flared away from the torso.
        flare_angle = angle_deg((hip[0], hip[1]), (shoulder[0], shoulder[1]), (elbow[0], elbow[1]))
        if flare_angle > threshold:
            return True
    return False if any_evaluable else None


def hip_sag_present(
    person: Dict[str, Any],
    pose_model: str,
    thresholds: Dict[str, Any],
    min_visibility: Optional[float] = None,
) -> Optional[bool]:
    """pushup.json: angle(shoulder, hip, ankle) < hip_sag_angle_min -- the body line bending at
    the hip below a near-straight angle. True if EITHER side trips; None only if NEITHER side has
    enough visible landmarks to judge at all."""
    threshold = thresholds.get("hip_sag_angle_min")
    if threshold is None:
        return None
    any_evaluable = False
    for side in ("left", "right"):
        shoulder = _visible_point(person, pose_model, f"{side}_shoulder", min_visibility)
        hip = _visible_point(person, pose_model, f"{side}_hip", min_visibility)
        ankle = _visible_point(person, pose_model, f"{side}_ankle", min_visibility)
        if not all((shoulder, hip, ankle)):
            continue
        any_evaluable = True
        body_angle = angle_deg(
            (shoulder[0], shoulder[1]), (hip[0], hip[1]), (ankle[0], ankle[1])
        )
        if body_angle < threshold:
            return True
    return False if any_evaluable else None


def excess_torso_lean_present(
    person: Dict[str, Any],
    pose_model: str,
    thresholds: Dict[str, Any],
    min_visibility: Optional[float] = None,
) -> Optional[bool]:
    """squat.json / lunge.json: torso deviation from vertical > torso_lean_max_deg.

    Unlike elbow_flare / hip_sag, this is NOT an either-side rule: torso lean is a midline
    measurement (shoulder midpoint vs hip midpoint), so one side's landmarks are not a valid
    substitute for both -- a single visible shoulder tells you nothing about where the torso's
    centre line is. All four landmarks are therefore required, and anything less returns None
    (insufficient evidence), which flag_hysteresis.py surfaces rather than guessing from.

    Threshold comes from each exercise's own thresholds block (squat 45deg, lunge 20deg -- both
    already present in the library and both matching kinetiq-demo2's shipped values); the geometry
    is geometry.torso_lean_deg, transliterated from demo2's own implementation.
    """
    threshold = thresholds.get("torso_lean_max_deg")
    if threshold is None:
        return None
    left_shoulder = _visible_point(person, pose_model, "left_shoulder", min_visibility)
    right_shoulder = _visible_point(person, pose_model, "right_shoulder", min_visibility)
    left_hip = _visible_point(person, pose_model, "left_hip", min_visibility)
    right_hip = _visible_point(person, pose_model, "right_hip", min_visibility)
    if not all((left_shoulder, right_shoulder, left_hip, right_hip)):
        return None
    shoulder_mid = midpoint((left_shoulder[0], left_shoulder[1]), (right_shoulder[0], right_shoulder[1]))
    hip_mid = midpoint((left_hip[0], left_hip[1]), (right_hip[0], right_hip[1]))
    return torso_lean_deg(shoulder_mid, hip_mid) > threshold


def shallow_pushup_present(rep_min_angle: float, exercise_json: Dict[str, Any]) -> bool:
    """pushup.json: elbow_angle_at_bottom > depth_elbow_angle_max. Rep-aggregate -- see module
    docstring for why this has no visibility parameter and never goes through hysteresis."""
    depth_max = exercise_json.get("thresholds", {}).get("depth_elbow_angle_max")
    return depth_max is not None and rep_min_angle > depth_max


def shallow_lunge_present(rep_min_angle: float, exercise_json: Dict[str, Any]) -> bool:
    """lunge.json: front_knee_angle_at_bottom > front_knee_angle_bottom_max. Rep-aggregate, like
    shallow_pushup_present -- see module docstring. Only shallow_lunge is implemented for lunge;
    front_knee_cave / front_knee_overextend are marked status: "unresolved_spec_conflict" in
    lunge.json itself, so this reference detector leaves them unimplemented too."""
    threshold = exercise_json.get("thresholds", {}).get("front_knee_angle_bottom_max")
    return threshold is not None and rep_min_angle > threshold
