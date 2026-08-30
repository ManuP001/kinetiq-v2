#!/usr/bin/env python3
"""Unit tests for scorers/subject_lock.py, over tiny synthetic clip stand-ins."""
from __future__ import annotations

import sys
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import gate_config  # noqa: E402
from scorers.subject_lock import score_subject_lock  # noqa: E402


@dataclass
class FakeClip:
    clip_id: str
    subject_num_people_in_frame: Optional[int]
    subject_lock: Optional[Dict[str, Any]] = field(default=None)


class TestScoreSubjectLock(unittest.TestCase):
    def test_single_person_clips_are_ignored(self):
        clips = [FakeClip("c1", 1, {"frames_total": 100, "frames_on_expected_subject": 50})]
        result = score_subject_lock(clips)
        self.assertEqual(result.per_clip, {})
        self.assertIsNone(result.mean)
        self.assertTrue(result.passed())  # vacuous pass, no multi-person clips

    def test_multi_person_clip_above_floor_passes(self):
        clips = [FakeClip("bystander_001", 2, {"frames_total": 900, "frames_on_expected_subject": 894})]
        result = score_subject_lock(clips)
        self.assertAlmostEqual(result.per_clip["bystander_001"], 894 / 900)
        self.assertTrue(result.passed(gate_config.SUBJECT_LOCK_FLOOR))

    def test_multi_person_clip_below_floor_fails(self):
        clips = [FakeClip("bystander_002", 2, {"frames_total": 900, "frames_on_expected_subject": 700})]
        result = score_subject_lock(clips)
        self.assertFalse(result.passed(gate_config.SUBJECT_LOCK_FLOOR))

    def test_one_bad_clip_fails_even_if_mean_is_fine(self):
        clips = [
            FakeClip("good", 2, {"frames_total": 100, "frames_on_expected_subject": 100}),
            FakeClip("bad", 2, {"frames_total": 100, "frames_on_expected_subject": 50}),
        ]
        result = score_subject_lock(clips)
        self.assertGreaterEqual(result.mean, 0.5)  # mean looks OK-ish
        self.assertFalse(result.passed(gate_config.SUBJECT_LOCK_FLOOR))  # but "bad" alone fails

    def test_missing_subject_lock_data_is_skipped(self):
        clips = [FakeClip("c1", 2, None)]
        result = score_subject_lock(clips)
        self.assertEqual(result.per_clip, {})

    def test_empty_input(self):
        result = score_subject_lock([])
        self.assertIsNone(result.mean)
        self.assertTrue(result.passed())


if __name__ == "__main__":
    unittest.main()
