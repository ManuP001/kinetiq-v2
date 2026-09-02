#!/usr/bin/env python3
"""Unit tests for scorers/phantom.py, over tiny synthetic clip stand-ins."""
from __future__ import annotations

import sys
import unittest
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scorers.phantom import score_phantom  # noqa: E402


@dataclass
class FakeClip:
    clip_id: str
    clip_type: str
    detected_reps: int


class TestScorePhantom(unittest.TestCase):
    def test_all_zero_passes(self):
        clips = [
            FakeClip("bench_001", "phantom_bench", 0),
            FakeClip("empty_001", "phantom_empty", 0),
        ]
        result = score_phantom(clips)
        self.assertEqual(result.checked, 2)
        self.assertTrue(result.passed)
        self.assertEqual(result.failures, [])

    def test_bystander_clips_are_ignored(self):
        # bystander is NOT phantom-like (EVAL_HARNESS_STAGE0_SPEC.md §5/§7): the user's real reps
        # are scored by subject-lock + rep-accuracy instead, never this zero-reps gate -- a real,
        # nonzero rep count on a bystander clip must never fail this scorer.
        clips = [FakeClip("bystander_001", "bystander", 12)]
        result = score_phantom(clips)
        self.assertEqual(result.checked, 0)
        self.assertTrue(result.passed)

    def test_nonzero_reps_fails_and_names_the_clip(self):
        clips = [
            FakeClip("bench_001", "phantom_bench", 0),
            FakeClip("bench_002", "phantom_bench", 6),  # the bench->6-reps bug
        ]
        result = score_phantom(clips)
        self.assertFalse(result.passed)
        self.assertEqual(result.failures, ["bench_002"])

    def test_normal_clips_are_ignored(self):
        clips = [FakeClip("squat_001", "normal", 10)]
        result = score_phantom(clips)
        self.assertEqual(result.checked, 0)
        self.assertTrue(result.passed)

    def test_empty_input_is_a_vacuous_pass(self):
        result = score_phantom([])
        self.assertEqual(result.checked, 0)
        self.assertTrue(result.passed)


if __name__ == "__main__":
    unittest.main()
