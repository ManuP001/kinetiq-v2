#!/usr/bin/env python3
"""Unit tests for detector/faults.py, against the real exercises/*.json thresholds."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import gate_config  # noqa: E402
from detector.faults import (  # noqa: E402
    elbow_flare_present,
    hip_sag_present,
    knee_cave_left_present,
    knee_cave_right_present,
    shallow_depth_present,
    shallow_lunge_present,
    shallow_pushup_present,
)
from detector.keypoint_map import POSE_MODEL_LANDMARKS  # noqa: E402

MOVENET = "movenet_17"


def make_person(overrides, n=17, default_vis=0.9):
    """overrides: name -> (x, y) or (x, y, vis)."""
    kp = [[0.5, 0.5, None, default_vis] for _ in range(n)]
    for name, values in overrides.items():
        x, y = values[0], values[1]
        vis = values[2] if len(values) > 2 else default_vis
        idx = POSE_MODEL_LANDMARKS[MOVENET][name]
        kp[idx] = [x, y, None, vis]
    return {"track_id": 0, "kp": kp, "box": [0.3, 0.2, 0.4, 0.6]}


class TestSquatPredicates(unittest.TestCase):
    def setUp(self):
        self.thresholds = gate_config.load_exercise_library()["squat"]["thresholds"]

    def test_clean_squat_has_no_faults(self):
        # hip.y >= knee.y (hip at or below knee level, i.e. lower in the frame) = full depth.
        person = make_person({
            "left_hip": (0.45, 0.87), "left_knee": (0.45, 0.85), "left_ankle": (0.45, 0.95),
            "right_hip": (0.55, 0.87), "right_knee": (0.55, 0.85), "right_ankle": (0.55, 0.95),
        })
        self.assertFalse(knee_cave_left_present(person, MOVENET, self.thresholds))
        self.assertFalse(knee_cave_right_present(person, MOVENET, self.thresholds))
        self.assertFalse(shallow_depth_present(person, MOVENET))

    def test_knee_cave_left_detected(self):
        # left ankle drifts well medial of the left knee in x -- knee_cave_x threshold is 0.05.
        person = make_person({
            "left_hip": (0.45, 0.75), "left_knee": (0.45, 0.85), "left_ankle": (0.60, 0.95),
        })
        self.assertTrue(knee_cave_left_present(person, MOVENET, self.thresholds))

    def test_knee_cave_right_detected(self):
        # rule: right_knee.x - right_ankle.x > threshold -- knee drifted medial (more positive x
        # here) of the ankle.
        person = make_person({
            "right_hip": (0.55, 0.75), "right_knee": (0.65, 0.85), "right_ankle": (0.55, 0.95),
        })
        self.assertTrue(knee_cave_right_present(person, MOVENET, self.thresholds))

    def test_shallow_depth_detected_when_hip_above_knee(self):
        person = make_person({
            "left_hip": (0.45, 0.70), "left_knee": (0.45, 0.85),
            "right_hip": (0.55, 0.70), "right_knee": (0.55, 0.85),
        })
        self.assertTrue(shallow_depth_present(person, MOVENET))

    def test_missing_landmarks_return_none_not_false(self):
        empty_person = {"track_id": 0, "kp": [], "box": [0, 0, 1, 1]}
        self.assertIsNone(knee_cave_left_present(empty_person, MOVENET, self.thresholds))
        self.assertIsNone(shallow_depth_present(empty_person, MOVENET))

    def test_visibility_below_floor_returns_none(self):
        person = make_person({
            "left_hip": (0.45, 0.75, 0.05), "left_knee": (0.45, 0.85, 0.05),
            "left_ankle": (0.60, 0.95, 0.05),
        })
        self.assertIsNone(
            knee_cave_left_present(person, MOVENET, self.thresholds, min_visibility=0.5)
        )
        # default (no min_visibility) ignores visibility, same as Stage-1 behaviour.
        self.assertTrue(knee_cave_left_present(person, MOVENET, self.thresholds))

    def test_missing_threshold_returns_none(self):
        person = make_person({"left_ankle": (0.6, 0.95), "left_knee": (0.45, 0.85)})
        self.assertIsNone(knee_cave_left_present(person, MOVENET, {}))


class TestPushupPredicates(unittest.TestCase):
    def setUp(self):
        self.thresholds = gate_config.load_exercise_library()["pushup"]["thresholds"]
        self.pushup = gate_config.load_exercise_library()["pushup"]

    # shoulder-hip-ankle in a straight line (no hip_sag), elbow within ~25 degrees of the
    # shoulder->hip axis (no elbow_flare -- its own trigger case is covered separately below).
    _STRAIGHT_BODY_NO_FLARE = {
        "left_shoulder": (0.3, 0.4), "left_elbow": (0.45, 0.47), "left_wrist": (0.6, 0.55),
        "left_hip": (0.5, 0.4), "left_ankle": (0.9, 0.4),
        "right_shoulder": (0.3, 0.42), "right_elbow": (0.45, 0.49), "right_wrist": (0.6, 0.57),
        "right_hip": (0.5, 0.42), "right_ankle": (0.9, 0.42),
    }

    def test_clean_pushup_has_no_faults(self):
        person = make_person(self._STRAIGHT_BODY_NO_FLARE)
        self.assertFalse(elbow_flare_present(person, MOVENET, self.thresholds))
        self.assertFalse(hip_sag_present(person, MOVENET, self.thresholds))

    def test_shallow_pushup_detected_from_rep_min_angle(self):
        # depth_elbow_angle_max is 95 -- 140 is well above (not deep enough).
        self.assertTrue(shallow_pushup_present(140.0, self.pushup))
        self.assertFalse(shallow_pushup_present(80.0, self.pushup))

    def test_elbow_flare_detected(self):
        person = make_person({
            "left_shoulder": (0.3, 0.4), "left_hip": (0.5, 0.4), "left_ankle": (0.9, 0.4),
            "left_elbow": (0.3, 0.6), "left_wrist": (0.3, 0.75),  # straight down: ~90 deg flare
            "right_shoulder": (0.3, 0.42), "right_hip": (0.5, 0.42), "right_ankle": (0.9, 0.42),
            "right_elbow": (0.3, 0.62), "right_wrist": (0.3, 0.77),
        })
        self.assertTrue(elbow_flare_present(person, MOVENET, self.thresholds))

    def test_hip_sag_detected(self):
        # hips drop well below the shoulder-ankle line -> body_angle at hip is small.
        person = make_person({
            "left_shoulder": (0.3, 0.4), "left_hip": (0.5, 0.75), "left_ankle": (0.9, 0.4),
            "right_shoulder": (0.3, 0.42), "right_hip": (0.5, 0.77), "right_ankle": (0.9, 0.42),
        })
        self.assertTrue(hip_sag_present(person, MOVENET, self.thresholds))

    def test_hip_sag_visibility_gate(self):
        person = make_person({
            "left_shoulder": (0.3, 0.4, 0.1), "left_hip": (0.5, 0.75, 0.1), "left_ankle": (0.9, 0.4, 0.1),
            "right_shoulder": (0.3, 0.42, 0.1), "right_hip": (0.5, 0.77, 0.1), "right_ankle": (0.9, 0.42, 0.1),
        })
        self.assertIsNone(hip_sag_present(person, MOVENET, self.thresholds, min_visibility=0.5))
        self.assertTrue(hip_sag_present(person, MOVENET, self.thresholds))  # unfiltered

    def test_one_visible_side_is_enough(self):
        # left side clean, right side genuinely absent (kp array too short to reach it) --
        # still evaluable via the left side alone (False, straight body).
        n = POSE_MODEL_LANDMARKS[MOVENET]["left_ankle"] + 1  # covers left_* only
        person = make_person({
            "left_shoulder": (0.3, 0.4), "left_hip": (0.5, 0.4), "left_ankle": (0.9, 0.4),
        }, n=n)
        self.assertFalse(hip_sag_present(person, MOVENET, self.thresholds))

    def test_missing_threshold_returns_none(self):
        person = make_person(self._STRAIGHT_BODY_NO_FLARE)
        self.assertIsNone(elbow_flare_present(person, MOVENET, {}))
        self.assertIsNone(hip_sag_present(person, MOVENET, {}))


class TestLungePredicates(unittest.TestCase):
    def setUp(self):
        self.lunge = gate_config.load_exercise_library()["lunge"]

    def test_shallow_lunge_detected(self):
        self.assertTrue(shallow_lunge_present(rep_min_angle=130.0, exercise_json=self.lunge))

    def test_full_depth_lunge_has_no_shallow_flag(self):
        self.assertFalse(shallow_lunge_present(rep_min_angle=85.0, exercise_json=self.lunge))

    def test_unresolved_faults_are_never_produced(self):
        # front_knee_cave / front_knee_overextend are deliberately unimplemented -- confirm the
        # module doesn't expose anything claiming to detect them.
        import detector.faults as faults_mod
        self.assertFalse(hasattr(faults_mod, "front_knee_cave_present"))


if __name__ == "__main__":
    unittest.main()
