#!/usr/bin/env python3
"""Unit tests for detector/keypoint_map.py -- per-model landmark index mappings (Stage 2: the
bake-off's model-agnostic feature layer, VISION_ARCHITECTURE.md §2)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import gate_config  # noqa: E402
from detector.keypoint_map import (  # noqa: E402
    POSE_MODEL_LANDMARKS,
    SCOPED_LANDMARK_NAMES,
    get_point,
    known_pose_models,
)


def make_person(n, overrides):
    kp = [[0.0, 0.0, None, 0.0] for _ in range(n)]
    for idx, point in overrides.items():
        kp[idx] = list(point)
    return {"track_id": 0, "kp": kp, "box": [0, 0, 1, 1]}


class TestKnownIndices(unittest.TestCase):
    """Pins the exact, published indices for each model -- a regression here means a silent
    data-correctness bug (the wrong landmark being read as e.g. "left_knee")."""

    def test_blazepose_33_core_indices(self):
        m = POSE_MODEL_LANDMARKS["blazepose_33"]
        self.assertEqual(m["left_shoulder"], 11)
        self.assertEqual(m["right_shoulder"], 12)
        self.assertEqual(m["left_hip"], 23)
        self.assertEqual(m["right_hip"], 24)
        self.assertEqual(m["left_knee"], 25)
        self.assertEqual(m["right_knee"], 26)
        self.assertEqual(m["left_ankle"], 27)
        self.assertEqual(m["right_ankle"], 28)
        self.assertEqual(m["left_heel"], 29)
        self.assertEqual(m["right_heel"], 30)
        self.assertEqual(m["left_toe"], 31)
        self.assertEqual(m["right_toe"], 32)

    def test_movenet_17_core_indices(self):
        m = POSE_MODEL_LANDMARKS["movenet_17"]
        self.assertEqual(m["left_shoulder"], 5)
        self.assertEqual(m["right_shoulder"], 6)
        self.assertEqual(m["left_hip"], 11)
        self.assertEqual(m["right_hip"], 12)
        self.assertEqual(m["left_knee"], 13)
        self.assertEqual(m["right_knee"], 14)
        self.assertEqual(m["left_ankle"], 15)
        self.assertEqual(m["right_ankle"], 16)

    def test_movenet_17_has_no_foot_landmarks(self):
        m = POSE_MODEL_LANDMARKS["movenet_17"]
        self.assertNotIn("left_heel", m)
        self.assertNotIn("left_toe", m)

    def test_rtmpose_halpe26_core_indices_match_coco17_order(self):
        # Halpe-26's first 17 points are COCO-17 verbatim -- same indices as movenet_17.
        rtm = POSE_MODEL_LANDMARKS["rtmpose_halpe26"]
        movenet = POSE_MODEL_LANDMARKS["movenet_17"]
        for name in SCOPED_LANDMARK_NAMES:
            self.assertEqual(rtm[name], movenet[name], name)

    def test_rtmpose_halpe26_foot_indices(self):
        m = POSE_MODEL_LANDMARKS["rtmpose_halpe26"]
        self.assertEqual(m["left_heel"], 24)
        self.assertEqual(m["right_heel"], 25)
        self.assertEqual(m["left_toe"], 20)
        self.assertEqual(m["right_toe"], 21)


class TestGetPoint(unittest.TestCase):
    def test_returns_the_right_landmark(self):
        person = make_person(17, {13: (0.4, 0.6, None, 0.9)})
        point = get_point(person, "movenet_17", "left_knee")
        self.assertEqual(point, (0.4, 0.6, None, 0.9))

    def test_unknown_pose_model_returns_none(self):
        person = make_person(17, {})
        self.assertIsNone(get_point(person, "some_future_model", "left_knee"))

    def test_name_not_in_this_models_table_returns_none(self):
        person = make_person(17, {})
        self.assertIsNone(get_point(person, "movenet_17", "left_heel"))

    def test_too_few_keypoints_returns_none_not_indexerror(self):
        person = {"track_id": 0, "kp": [[0, 0, None, 0.5]], "box": [0, 0, 1, 1]}
        self.assertIsNone(get_point(person, "movenet_17", "left_ankle"))


class TestCandidateRegistryConsistency(unittest.TestCase):
    """Every pose model listed in config.py's bake-off registry must have a keypoint_map entry,
    and vice versa isn't required (a model can be mapped before it's registered) -- but a
    registered candidate with no mapping would silently break run_detector for that model."""

    def test_every_registered_candidate_has_a_keypoint_mapping(self):
        for candidate in gate_config.POSE_MODEL_CANDIDATES:
            self.assertIn(candidate["name"], POSE_MODEL_LANDMARKS)

    def test_every_registered_candidate_maps_the_full_scoped_set(self):
        for candidate in gate_config.POSE_MODEL_CANDIDATES:
            mapping = POSE_MODEL_LANDMARKS[candidate["name"]]
            for name in SCOPED_LANDMARK_NAMES:
                self.assertIn(name, mapping, f"{candidate['name']} missing {name!r}")

    def test_known_pose_models_includes_every_registered_candidate(self):
        known = set(known_pose_models())
        for candidate in gate_config.POSE_MODEL_CANDIDATES:
            self.assertIn(candidate["name"], known)


if __name__ == "__main__":
    unittest.main()
