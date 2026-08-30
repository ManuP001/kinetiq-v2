#!/usr/bin/env python3
"""
evals/gate0/detector/keypoint_map.py

The COCO-17 <-> BlazePose-33 keypoint mapping referenced by VISION_ARCHITECTURE.md §2 and
flagged as missing by EVAL_HARNESS_STAGE0_SPEC.md's build checklist ("the harness's 'map to a
common feature set' step depends on it").

Scope note: this maps only the landmarks Stage 1 actually needs -- shoulders, elbows, wrists,
hips, knees, ankles, both sides -- because that's everything squat/pushup/lunge's phase and fault
logic touches (ROADMAP.md Stage 1 is scoped to those three exercises; the 11 requested additions
are Stage 5, gated one at a time). BlazePose has 33 total landmarks and MoveNet/COCO has 17; most
of BlazePose's extra points (face detail, fingers, feet) have no COCO-17 counterpart at all, so a
literal 1:1 33<->17 table doesn't exist -- what's needed, and what's here, is a named landmark ->
per-model index lookup. Extend this table if a later exercise needs a landmark not listed (e.g.
foot_index/heel for a toe-position rule).

Indices are the standard, published orderings for each model (MediaPipe BlazePose Pose Landmarker;
MoveNet's COCO-17 keypoint order) -- not something this harness invented.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

# name -> landmark index, per pose model.
POSE_MODEL_LANDMARKS: Dict[str, Dict[str, int]] = {
    "blazepose_33": {
        "left_shoulder": 11, "right_shoulder": 12,
        "left_elbow": 13, "right_elbow": 14,
        "left_wrist": 15, "right_wrist": 16,
        "left_hip": 23, "right_hip": 24,
        "left_knee": 25, "right_knee": 26,
        "left_ankle": 27, "right_ankle": 28,
    },
    "movenet_17": {
        "left_shoulder": 5, "right_shoulder": 6,
        "left_elbow": 7, "right_elbow": 8,
        "left_wrist": 9, "right_wrist": 10,
        "left_hip": 11, "right_hip": 12,
        "left_knee": 13, "right_knee": 14,
        "left_ankle": 15, "right_ankle": 16,
    },
}

# The landmark set used for the human-plausibility visibility check (detector/plausibility.py) --
# deliberately the same scoped set as above, both sides.
SCOPED_LANDMARK_NAMES: Tuple[str, ...] = tuple(POSE_MODEL_LANDMARKS["movenet_17"].keys())

Point = Tuple[float, float, Optional[float], float]  # (x, y, z_or_None, visibility)


def known_pose_models() -> Tuple[str, ...]:
    return tuple(POSE_MODEL_LANDMARKS.keys())


def get_point(person: Dict[str, Any], pose_model: str, name: str) -> Optional[Point]:
    """The named landmark's [x, y, z, vis] for this person, or None if the pose model is
    unmapped, the name isn't in the scoped table, or the person has too few keypoints."""
    landmarks = POSE_MODEL_LANDMARKS.get(pose_model)
    if landmarks is None or name not in landmarks:
        return None
    idx = landmarks[name]
    kp: List[Any] = person.get("kp", [])
    if idx >= len(kp):
        return None
    x, y, z, vis = kp[idx]
    return (x, y, z, vis)
