#!/usr/bin/env python3
"""
evals/gate0/detector/faults.py

Deterministic form-flag rules, transliterated from each exercise's own
reference_keypoints.correct.common_errors[].keypoint_signature.rule string into executable
Python. This is the existing rule set "as-is" (per the Stage-1 task brief) -- no new fault
semantics, no threshold tuning. Thresholds are read from the exercise's own thresholds block,
never restated here (CLAUDE.md §3).

Scope, deliberately not exhaustive:
  - squat: knee_cave_left, knee_cave_right, shallow_depth -- all three have a complete,
    unambiguous rule + threshold in squat.json.
  - pushup: elbow_flare, hip_sag, shallow_pushup -- same.
  - lunge: shallow_lunge only. lunge.json's front_knee_cave / front_knee_overextend are marked
    status: "unresolved_spec_conflict" in the library itself (conflicting with Vision_Contract,
    "not implemented in kinetiq-demo2 pending trainer/PT-confirmed semantics") -- this reference
    detector leaves them unimplemented for the same reason the existing product does, rather than
    inventing a resolution to a conflict this task didn't ask it to resolve.

Evaluated once per rep, at the rep's local-minimum-angle frame (its "worst point" / deepest
point) -- a Stage-1 simplification; full per-frame temporal fault tracking across a rep's whole
trajectory is Stage 4/5 territory (the learned form model).
"""
from __future__ import annotations

from typing import Any, Dict, List

from detector.geometry import angle_deg
from detector.keypoint_map import get_point


def _knee_cave_faults(person: Dict[str, Any], pose_model: str, thresholds: Dict[str, Any]) -> List[str]:
    """squat.json: left/right knee collapsing medially past the ankle in x."""
    flags = []
    threshold = thresholds.get("knee_cave_x")
    if threshold is None:
        return flags
    left_ankle = get_point(person, pose_model, "left_ankle")
    left_knee = get_point(person, pose_model, "left_knee")
    if left_ankle and left_knee and (left_ankle[0] - left_knee[0]) > threshold:
        flags.append("knee_cave_left")
    right_knee = get_point(person, pose_model, "right_knee")
    right_ankle = get_point(person, pose_model, "right_ankle")
    if right_knee and right_ankle and (right_knee[0] - right_ankle[0]) > threshold:
        flags.append("knee_cave_right")
    return flags


def _squat_shallow_depth(person: Dict[str, Any], pose_model: str) -> List[str]:
    """squat.json: "left_hip.y < left_knee.y AND right_hip.y < right_knee.y at bottom" --
    hip numerically above (smaller y than) knee level means depth wasn't reached."""
    left_hip = get_point(person, pose_model, "left_hip")
    left_knee = get_point(person, pose_model, "left_knee")
    right_hip = get_point(person, pose_model, "right_hip")
    right_knee = get_point(person, pose_model, "right_knee")
    if not all((left_hip, left_knee, right_hip, right_knee)):
        return []
    if left_hip[1] < left_knee[1] and right_hip[1] < right_knee[1]:
        return ["shallow_depth"]
    return []


def squat_faults(person: Dict[str, Any], pose_model: str, exercise_json: Dict[str, Any]) -> List[str]:
    thresholds = exercise_json.get("thresholds", {})
    return _knee_cave_faults(person, pose_model, thresholds) + _squat_shallow_depth(person, pose_model)


def _pushup_elbow_flare(person: Dict[str, Any], pose_model: str, thresholds: Dict[str, Any]) -> List[str]:
    """pushup.json: angle(shoulder, elbow, torso_midline) > elbow_flare_deg. "torso_midline" is
    not itself a landmark; the local torso segment (same-side shoulder->hip) is used as the
    reference axis for the angle at the elbow -- a documented interpretation, not an invented
    threshold (the threshold value itself still comes from thresholds.elbow_flare_deg)."""
    threshold = thresholds.get("elbow_flare_deg")
    if threshold is None:
        return []
    flags = []
    for side in ("left", "right"):
        shoulder = get_point(person, pose_model, f"{side}_shoulder")
        elbow = get_point(person, pose_model, f"{side}_elbow")
        hip = get_point(person, pose_model, f"{side}_hip")
        if not all((shoulder, elbow, hip)):
            continue
        # Angle at the shoulder between the torso axis (shoulder->hip) and the upper arm
        # (shoulder->elbow) -- large angle means the elbow has flared away from the torso.
        flare_angle = angle_deg((hip[0], hip[1]), (shoulder[0], shoulder[1]), (elbow[0], elbow[1]))
        if flare_angle > threshold:
            flags.append("elbow_flare")
            break  # one flag per rep regardless of how many sides trip it
    return flags


def _pushup_hip_sag(person: Dict[str, Any], pose_model: str, thresholds: Dict[str, Any]) -> List[str]:
    """pushup.json: angle(shoulder, hip, ankle) < hip_sag_angle_min -- the body line bending at
    the hip below a near-straight angle."""
    threshold = thresholds.get("hip_sag_angle_min")
    if threshold is None:
        return []
    for side in ("left", "right"):
        shoulder = get_point(person, pose_model, f"{side}_shoulder")
        hip = get_point(person, pose_model, f"{side}_hip")
        ankle = get_point(person, pose_model, f"{side}_ankle")
        if not all((shoulder, hip, ankle)):
            continue
        body_angle = angle_deg(
            (shoulder[0], shoulder[1]), (hip[0], hip[1]), (ankle[0], ankle[1])
        )
        if body_angle < threshold:
            return ["hip_sag"]
    return []


def pushup_faults(
    person: Dict[str, Any], pose_model: str, exercise_json: Dict[str, Any], rep_min_angle: float
) -> List[str]:
    """rep_min_angle is the rep's minimum smoothed elbow angle (its deepest point), already
    computed by the rep counter -- pushup.json's shallow_pushup rule
    ("elbow_angle_at_bottom > depth_elbow_angle_max") is about the whole rep's depth, not a
    single frame's pose, so it's evaluated against that rather than the per-frame person record."""
    thresholds = exercise_json.get("thresholds", {})
    flags = _pushup_elbow_flare(person, pose_model, thresholds) + _pushup_hip_sag(
        person, pose_model, thresholds
    )
    depth_max = thresholds.get("depth_elbow_angle_max")
    if depth_max is not None and rep_min_angle > depth_max:
        flags.append("shallow_pushup")
    return flags


def lunge_faults(rep_min_angle: float, exercise_json: Dict[str, Any]) -> List[str]:
    """Only shallow_lunge is implemented -- see module docstring for why front_knee_cave /
    front_knee_overextend are deliberately left out."""
    threshold = exercise_json.get("thresholds", {}).get("front_knee_angle_bottom_max")
    if threshold is not None and rep_min_angle > threshold:
        return ["shallow_lunge"]
    return []
