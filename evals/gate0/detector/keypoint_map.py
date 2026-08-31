#!/usr/bin/env python3
"""
evals/gate0/detector/keypoint_map.py

The cross-model keypoint mapping referenced by VISION_ARCHITECTURE.md §2 (originally the
COCO-17 <-> BlazePose-33 mapping flagged as missing by EVAL_HARNESS_STAGE0_SPEC.md's build
checklist; Stage 2 extends it to every pose-model bake-off candidate from config.py's
POSE_MODEL_CANDIDATES so run_detector is genuinely model-agnostic, per VISION_ARCHITECTURE.md
Stage 2: "document the ... mapping so features are model-agnostic").

Scope note: this maps the landmarks squat/pushup/lunge's phase and fault logic actually need --
shoulders, elbows, wrists, hips, knees, ankles, both sides (SCOPED_LANDMARK_NAMES) -- plus heel/
toe points where a model has them, for a future lunge toe-position rule
(exercises/lunge.json's currently-unimplemented front_knee_overextend). BlazePose has 33 total
landmarks, MoveNet/COCO has 17, RTMPose-Halpe26 has 26; most of BlazePose's and Halpe's extra
points (face detail, fingers) have no counterpart in the other models at all, so a literal 1:1
table across all landmarks doesn't exist -- what's needed, and what's here, is a named
landmark -> per-model index lookup. Extend this table if a later exercise needs a landmark not
listed.

Indices are the standard, published orderings for each model -- not something this harness
invented:
  - blazepose_33: MediaPipe BlazePose Pose Landmarker's 33-point order.
  - movenet_17: the COCO-17 keypoint order (also RTMPose's plain-COCO variant, if ever added).
  - rtmpose_halpe26: RTMPose-m trained on Halpe-26 (the combined "Body8" dataset, mmpose model
    zoo) -- indices 0-16 are COCO-17 verbatim (same order as movenet_17), 17-25 add head, neck,
    hip-center, and per-side big-toe/small-toe/heel. Chosen over plain-COCO RTMPose specifically
    for that extra richness (closer to BlazePose's point count) -- see gate0/README.md's
    bake-off section for the reasoning.
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
        "left_heel": 29, "right_heel": 30,
        "left_toe": 31, "right_toe": 32,  # BlazePose calls these *_FOOT_INDEX
    },
    "movenet_17": {
        "left_shoulder": 5, "right_shoulder": 6,
        "left_elbow": 7, "right_elbow": 8,
        "left_wrist": 9, "right_wrist": 10,
        "left_hip": 11, "right_hip": 12,
        "left_knee": 13, "right_knee": 14,
        "left_ankle": 15, "right_ankle": 16,
        # COCO-17 has no heel/toe landmarks -- left unmapped; get_point() returns None for them.
    },
    "rtmpose_halpe26": {
        # 0-16 identical to COCO-17/movenet_17's order.
        "left_shoulder": 5, "right_shoulder": 6,
        "left_elbow": 7, "right_elbow": 8,
        "left_wrist": 9, "right_wrist": 10,
        "left_hip": 11, "right_hip": 12,
        "left_knee": 13, "right_knee": 14,
        "left_ankle": 15, "right_ankle": 16,
        "left_heel": 24, "right_heel": 25,
        "left_toe": 20, "right_toe": 21,  # Halpe calls these *_BIG_TOE
    },
}

# The landmark set used for the human-plausibility visibility check (detector/plausibility.py) --
# deliberately the common/lowest-denominator set every candidate model has (heel/toe are extra,
# model-specific richness, not part of the plausibility gate).
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
