#!/usr/bin/env python3
"""Unit tests for detector/faults.py, against the real exercises/*.json thresholds."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import gate_config  # noqa: E402
from detector.faults import lunge_faults, pushup_faults, squat_faults  # noqa: E402
from detector.keypoint_map import POSE_MODEL_LANDMARKS  # noqa: E402

MOVENET = "movenet_17"


def make_person(overrides, n=17, default_vis=0.9):
    kp = [[0.5, 0.5, None, default_vis] for _ in range(n)]
    for name, (x, y) in overrides.items():
        idx = POSE_MODEL_LANDMARKS[MOVENET][name]
        kp[idx] = [x, y, None, default_vis]
    return {"track_id": 0, "kp": kp, "box": [0.3, 0.2, 0.4, 0.6]}


class TestSquatFaults(unittest.TestCase):
    def setUp(self):
        self.squat = gate_config.load_exercise_library()["squat"]

    def test_clean_squat_has_no_faults(self):
        # hip.y >= knee.y (hip at or below knee level, i.e. lower in the frame) = full depth.
        person = make_person({
            "left_hip": (0.45, 0.87), "left_knee": (0.45, 0.85), "left_ankle": (0.45, 0.95),
            "right_hip": (0.55, 0.87), "right_knee": (0.55, 0.85), "right_ankle": (0.55, 0.95),
        })
        self.assertEqual(squat_faults(person, MOVENET, self.squat), [])

    def test_knee_cave_left_detected(self):
        # left ankle drifts well medial of the left knee in x -- knee_cave_x threshold is 0.05.
        person = make_person({
            "left_hip": (0.45, 0.75), "left_knee": (0.45, 0.85), "left_ankle": (0.60, 0.95),
            "right_hip": (0.55, 0.75), "right_knee": (0.55, 0.85), "right_ankle": (0.55, 0.95),
        })
        self.assertIn("knee_cave_left", squat_faults(person, MOVENET, self.squat))

    def test_shallow_depth_detected_when_hip_above_knee(self):
        person = make_person({
            "left_hip": (0.45, 0.70), "left_knee": (0.45, 0.85), "left_ankle": (0.45, 0.95),
            "right_hip": (0.55, 0.70), "right_knee": (0.55, 0.85), "right_ankle": (0.55, 0.95),
        })
        self.assertIn("shallow_depth", squat_faults(person, MOVENET, self.squat))


class TestPushupFaults(unittest.TestCase):
    def setUp(self):
        self.pushup = gate_config.load_exercise_library()["pushup"]

    # Shared pose for the hip_sag/shallow_pushup tests: shoulder-hip-ankle in a straight line
    # (no hip_sag), elbow placed within ~25 degrees of the shoulder->hip axis (no elbow_flare --
    # its own trigger case is covered separately below). shallow_pushup is toggled purely via
    # the rep_min_angle parameter, which is the only thing that rule looks at.
    _STRAIGHT_BODY_NO_FLARE = {
        "left_shoulder": (0.3, 0.4), "left_elbow": (0.45, 0.47), "left_wrist": (0.6, 0.55),
        "left_hip": (0.5, 0.4), "left_ankle": (0.9, 0.4),
        "right_shoulder": (0.3, 0.42), "right_elbow": (0.45, 0.49), "right_wrist": (0.6, 0.57),
        "right_hip": (0.5, 0.42), "right_ankle": (0.9, 0.42),
    }

    def test_clean_pushup_has_no_faults(self):
        person = make_person(self._STRAIGHT_BODY_NO_FLARE)
        # rep_min_angle at/below depth_elbow_angle_max (95) -- a full-depth rep.
        flags = pushup_faults(person, MOVENET, self.pushup, rep_min_angle=80.0)
        self.assertEqual(flags, [])

    def test_shallow_pushup_detected(self):
        person = make_person(self._STRAIGHT_BODY_NO_FLARE)
        flags = pushup_faults(person, MOVENET, self.pushup, rep_min_angle=140.0)
        self.assertIn("shallow_pushup", flags)

    def test_elbow_flare_detected(self):
        person = make_person({
            "left_shoulder": (0.3, 0.4), "left_hip": (0.5, 0.4), "left_ankle": (0.9, 0.4),
            "left_elbow": (0.3, 0.6), "left_wrist": (0.3, 0.75),  # straight down: ~90 deg flare
            "right_shoulder": (0.3, 0.42), "right_hip": (0.5, 0.42), "right_ankle": (0.9, 0.42),
            "right_elbow": (0.3, 0.62), "right_wrist": (0.3, 0.77),
        })
        flags = pushup_faults(person, MOVENET, self.pushup, rep_min_angle=80.0)
        self.assertIn("elbow_flare", flags)

    def test_hip_sag_detected(self):
        # hips drop well below the shoulder-ankle line -> body_angle at hip is small.
        person = make_person({
            "left_shoulder": (0.3, 0.4), "left_hip": (0.5, 0.75), "left_ankle": (0.9, 0.4),
            "right_shoulder": (0.3, 0.42), "right_hip": (0.5, 0.77), "right_ankle": (0.9, 0.42),
            "left_elbow": (0.4, 0.5), "left_wrist": (0.35, 0.6),
            "right_elbow": (0.4, 0.52), "right_wrist": (0.35, 0.62),
        })
        flags = pushup_faults(person, MOVENET, self.pushup, rep_min_angle=80.0)
        self.assertIn("hip_sag", flags)


class TestLungeFaults(unittest.TestCase):
    def setUp(self):
        self.lunge = gate_config.load_exercise_library()["lunge"]

    def test_shallow_lunge_detected(self):
        self.assertEqual(lunge_faults(rep_min_angle=130.0, exercise_json=self.lunge), ["shallow_lunge"])

    def test_full_depth_lunge_has_no_shallow_flag(self):
        self.assertEqual(lunge_faults(rep_min_angle=85.0, exercise_json=self.lunge), [])

    def test_unresolved_faults_are_never_produced(self):
        # front_knee_cave / front_knee_overextend are deliberately unimplemented -- confirm the
        # module doesn't expose anything claiming to detect them.
        import detector.faults as faults_mod
        self.assertFalse(hasattr(faults_mod, "front_knee_cave"))


if __name__ == "__main__":
    unittest.main()
