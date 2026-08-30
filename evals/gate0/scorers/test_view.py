#!/usr/bin/env python3
"""Unit tests for scorers/view.py, over tiny synthetic clip stand-ins."""
from __future__ import annotations

import sys
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import gate_config  # noqa: E402
from scorers.view import score_view_robustness  # noqa: E402


@dataclass
class FakeClip:
    clip_id: str
    exercise: str
    clip_type: str
    view: Optional[str]
    actual_reps: int
    detected_reps: int


class TestScoreViewRobustness(unittest.TestCase):
    def test_perfect_accuracy_all_views_no_gap(self):
        clips = [
            FakeClip("s1", "squat", "normal", "front", 10, 10),
            FakeClip("s2", "squat", "normal", "side", 10, 10),
            FakeClip("s3", "squat", "normal", "diagonal", 10, 10),
        ]
        results = score_view_robustness(clips)
        self.assertAlmostEqual(results["squat"].gap, 0.0)
        self.assertTrue(results["squat"].passed(gate_config.VIEW_ACC_MAX_GAP))

    def test_large_gap_fails(self):
        clips = [
            FakeClip("s1", "squat", "normal", "front", 10, 10),   # 100%
            FakeClip("s2", "squat", "normal", "side", 10, 5),     # 50%
        ]
        results = score_view_robustness(clips)
        self.assertAlmostEqual(results["squat"].gap, 0.5)
        self.assertFalse(results["squat"].passed(gate_config.VIEW_ACC_MAX_GAP))

    def test_single_view_has_no_gap_and_vacuously_passes(self):
        clips = [FakeClip("s1", "squat", "normal", "front", 10, 10)]
        results = score_view_robustness(clips)
        self.assertIsNone(results["squat"].gap)
        self.assertTrue(results["squat"].passed())

    def test_non_normal_clips_are_excluded(self):
        clips = [FakeClip("b1", "squat", "phantom_bench", "diagonal", 0, 0)]
        results = score_view_robustness(clips)
        self.assertEqual(results, {})

    def test_unlabeled_view_is_excluded(self):
        clips = [FakeClip("s1", "squat", "normal", None, 10, 10)]
        results = score_view_robustness(clips)
        self.assertEqual(results, {})

    def test_zero_actual_with_zero_detected_is_perfect_accuracy(self):
        clips = [
            FakeClip("s1", "squat", "normal", "front", 0, 0),
            FakeClip("s2", "squat", "normal", "side", 0, 0),
        ]
        results = score_view_robustness(clips)
        self.assertAlmostEqual(results["squat"].accuracy_by_view["front"], 1.0)


if __name__ == "__main__":
    unittest.main()
