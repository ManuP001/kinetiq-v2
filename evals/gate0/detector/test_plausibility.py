#!/usr/bin/env python3
"""Unit tests for detector/plausibility.py."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import gate_config  # noqa: E402
from detector.keypoint_map import POSE_MODEL_LANDMARKS  # noqa: E402
from detector.plausibility import is_plausible_human, visible_fraction  # noqa: E402

MOVENET = "movenet_17"


def make_person(overrides, n=17, default_vis=0.05):
    """A movenet_17 person with every landmark at low visibility except the named overrides
    (name -> (x, y, vis))."""
    kp = [[0.5, 0.5, None, default_vis] for _ in range(n)]
    for name, (x, y, vis) in overrides.items():
        idx = POSE_MODEL_LANDMARKS[MOVENET][name]
        kp[idx] = [x, y, None, vis]
    return {"track_id": 0, "kp": kp, "box": [0.3, 0.2, 0.4, 0.6]}


FULL_VIS_HUMAN = {
    "left_shoulder": (0.4, 0.3, 0.95), "right_shoulder": (0.6, 0.3, 0.95),
    "left_elbow": (0.35, 0.45, 0.95), "right_elbow": (0.65, 0.45, 0.95),
    "left_wrist": (0.3, 0.6, 0.95), "right_wrist": (0.7, 0.6, 0.95),
    "left_hip": (0.45, 0.5, 0.95), "right_hip": (0.55, 0.5, 0.95),
    "left_knee": (0.45, 0.7, 0.95), "right_knee": (0.55, 0.7, 0.95),
    "left_ankle": (0.45, 0.9, 0.95), "right_ankle": (0.55, 0.9, 0.95),
}


class TestVisibleFraction(unittest.TestCase):
    def test_fully_visible_human_is_one(self):
        person = make_person(FULL_VIS_HUMAN)
        self.assertAlmostEqual(visible_fraction(person, MOVENET), 1.0)

    def test_all_low_visibility_is_zero(self):
        person = make_person({})
        self.assertEqual(visible_fraction(person, MOVENET), 0.0)


class TestIsPlausibleHuman(unittest.TestCase):
    def test_fully_visible_human_proportions_pass(self):
        person = make_person(FULL_VIS_HUMAN)
        self.assertTrue(is_plausible_human(person, MOVENET))

    def test_mostly_invisible_bench_like_blob_fails(self):
        # Only 2 of 12 scoped landmarks visible -- well under MIN_VISIBLE_KEYPOINT_FRACTION.
        person = make_person({
            "left_hip": (0.5, 0.5, 0.9),
            "right_hip": (0.55, 0.5, 0.9),
        })
        self.assertLess(
            visible_fraction(person, MOVENET), gate_config.MIN_VISIBLE_KEYPOINT_FRACTION
        )
        self.assertFalse(is_plausible_human(person, MOVENET))

    def test_implausible_limb_ratio_fails_even_with_full_visibility(self):
        bad = dict(FULL_VIS_HUMAN)
        # Shin ten times longer than thigh on both legs -- outside the plausible band, even
        # though every landmark is fully visible.
        bad["left_knee"] = (0.45, 0.501, 0.95)
        bad["right_knee"] = (0.55, 0.501, 0.95)
        person = make_person(bad)
        self.assertTrue(visible_fraction(person, MOVENET) >= gate_config.MIN_VISIBLE_KEYPOINT_FRACTION)
        self.assertFalse(is_plausible_human(person, MOVENET))

    def test_unknown_pose_model_has_zero_visibility_and_fails(self):
        person = make_person(FULL_VIS_HUMAN)
        self.assertFalse(is_plausible_human(person, "some_future_model"))


if __name__ == "__main__":
    unittest.main()
