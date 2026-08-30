#!/usr/bin/env python3
"""Unit tests for detector/subject_lock.py."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from detector.subject_lock import track_subject  # noqa: E402


def person(track_id, box):
    return {"track_id": track_id, "kp": [], "box": box}


def frame(people):
    return {"people": people}


class TestInitialSelection(unittest.TestCase):
    def test_largest_bbox_rule(self):
        frames = [frame([person(0, [0.1, 0.1, 0.1, 0.1]), person(1, [0.5, 0.5, 0.4, 0.4])])]
        result = track_subject(frames, selection_rule="largest_bbox")
        self.assertEqual(result[0].track_id, 1)

    def test_most_central_rule(self):
        frames = [frame([
            person(0, [0.0, 0.0, 0.1, 0.1]),      # far corner
            person(1, [0.45, 0.45, 0.1, 0.1]),    # near centre
        ])]
        result = track_subject(frames, selection_rule="most_central")
        self.assertEqual(result[0].track_id, 1)

    def test_empty_frame_has_no_lock(self):
        result = track_subject([frame([])])
        self.assertIsNone(result[0].person)
        self.assertIsNone(result[0].track_id)

    def test_unknown_rule_raises(self):
        with self.assertRaises(ValueError):
            track_subject([frame([person(0, [0, 0, 1, 1])])], selection_rule="coin_flip")


class TestStableTrackId(unittest.TestCase):
    def test_follows_the_same_track_id_across_frames(self):
        frames = [
            frame([person(0, [0.4, 0.4, 0.2, 0.2])]),
            frame([person(0, [0.41, 0.4, 0.2, 0.2]), person(1, [0.0, 0.0, 0.5, 0.5])]),
        ]
        result = track_subject(frames, selection_rule="largest_bbox")
        # frame 1: only track_id 0 present -> locked. frame 2: track_id 1 has the bigger box but
        # the lock must stay on 0 (never retarget to a more-prominent newcomer).
        self.assertEqual([r.track_id for r in result], [0, 0])


class TestReidAfterTrackIdChange(unittest.TestCase):
    def test_reacquires_same_person_at_a_new_track_id_via_centroid_proximity(self):
        frames = [
            frame([person(0, [0.4, 0.4, 0.2, 0.2])]),
            frame([person(7, [0.41, 0.41, 0.2, 0.2])]),  # id changed, position barely moved
        ]
        result = track_subject(frames, selection_rule="largest_bbox", reid_max_centroid_dist=0.15)
        self.assertEqual(result[1].track_id, 7)
        self.assertIsNotNone(result[1].person)

    def test_does_not_reacquire_a_distant_person_with_a_new_track_id(self):
        frames = [
            frame([person(0, [0.1, 0.1, 0.1, 0.1])]),
            frame([person(9, [0.8, 0.8, 0.1, 0.1])]),  # far away -- a different person
        ]
        result = track_subject(frames, selection_rule="largest_bbox", reid_max_centroid_dist=0.15)
        self.assertIsNone(result[1].person)


class TestPauseOnLostSubject(unittest.TestCase):
    def test_short_dropout_is_not_a_pause(self):
        frames = (
            [frame([person(0, [0.4, 0.4, 0.2, 0.2])])]
            + [frame([])] * 2  # 2 missed frames, threshold is 5
            + [frame([person(0, [0.4, 0.4, 0.2, 0.2])])]
        )
        result = track_subject(frames, lost_frames_threshold=5)
        self.assertFalse(any(r.paused for r in result))

    def test_long_dropout_triggers_pause(self):
        frames = (
            [frame([person(0, [0.4, 0.4, 0.2, 0.2])])]
            + [frame([])] * 6  # exceeds threshold of 5
        )
        result = track_subject(frames, lost_frames_threshold=5)
        self.assertTrue(result[-1].paused)

    def test_never_retargets_to_a_different_person_while_paused(self):
        frames = (
            [frame([person(0, [0.1, 0.1, 0.1, 0.1])])]
            + [frame([person(1, [0.7, 0.7, 0.4, 0.4])])] * 8  # a big, prominent bystander appears
        )
        result = track_subject(frames, lost_frames_threshold=5, reid_max_centroid_dist=0.15)
        # locked identity is still track_id 0's position -- never adopts track_id 1.
        for r in result[1:]:
            self.assertIsNone(r.person)

    def test_resumes_when_the_original_subject_returns_after_a_pause(self):
        frames = (
            [frame([person(0, [0.4, 0.4, 0.2, 0.2])])]
            + [frame([])] * 6                                    # pause triggers
            + [frame([person(0, [0.41, 0.41, 0.2, 0.2])])]        # same person, same position
        )
        result = track_subject(frames, lost_frames_threshold=5, reid_max_centroid_dist=0.15)
        self.assertTrue(result[6].paused)  # still paused at frame index 6 (6th missed frame)
        self.assertIsNotNone(result[-1].person)  # re-acquired on return
        self.assertFalse(result[-1].paused)


if __name__ == "__main__":
    unittest.main()
