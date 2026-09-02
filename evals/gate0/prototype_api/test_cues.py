#!/usr/bin/env python3
"""Unit tests for prototype_api/cues.py, against the REAL exercise library (not a fixture) --
this is exactly what proves squat.json's shallow_depth cue is genuinely over the word cap."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import gate_config  # noqa: E402
from prototype_api.cues import cue_for_rep  # noqa: E402

SQUAT = gate_config.load_exercise_library()["squat"]
PUSHUP = gate_config.load_exercise_library()["pushup"]


class TestCueForRep(unittest.TestCase):
    def test_no_flags_returns_the_good_rep_cue(self):
        result = cue_for_rep(SQUAT, [])
        self.assertEqual(result.text, SQUAT["coaching_cues"]["good_rep"])
        self.assertFalse(result.over_word_cap)

    def test_one_flag_returns_that_flags_cue(self):
        result = cue_for_rep(SQUAT, ["knee_cave_left"])
        self.assertEqual(result.text, "Push your left knee out")
        self.assertFalse(result.over_word_cap)

    def test_first_flag_wins_when_multiple_are_committed(self):
        # positive-first / detector-order: never re-decided here, just flags[0].
        result = cue_for_rep(SQUAT, ["knee_cave_right", "shallow_depth"])
        self.assertEqual(result.text, "Push your right knee out")

    def test_unmapped_flag_returns_none_rather_than_guessing(self):
        result = cue_for_rep(SQUAT, ["not_a_real_flag"])
        self.assertIsNone(result.text)
        self.assertFalse(result.over_word_cap)

    def test_squat_shallow_depth_cue_is_over_the_word_cap(self):
        # The exact case the build task called out: squat.json's shallow_depth cue is over
        # LIVE_CUE_MAX_WORDS. Flagged here, not silently truncated.
        result = cue_for_rep(SQUAT, ["shallow_depth"])
        self.assertEqual(result.text, "Sit a little deeper — hip crease to knee level")
        self.assertTrue(result.over_word_cap)
        self.assertGreater(result.word_count, gate_config.LIVE_CUE_MAX_WORDS)

    def test_pushup_good_rep_and_elbow_flare_and_hip_sag_are_within_the_word_cap(self):
        for flags in ([], ["elbow_flare"], ["hip_sag"]):
            with self.subTest(flags=flags):
                result = cue_for_rep(PUSHUP, flags)
                self.assertIsNotNone(result.text)
                self.assertFalse(result.over_word_cap, result.text)

    def test_pushup_shallow_pushup_cue_is_also_over_the_word_cap(self):
        # A second real over-cap cue this word-cap check surfaces, not assumed away: "Go a
        # little lower — elbows to 90 degrees" is 9 words counting the em dash as a token (the
        # same len(text.split()) convention aggregate.py's Stage-0 assertion already uses).
        result = cue_for_rep(PUSHUP, ["shallow_pushup"])
        self.assertTrue(result.over_word_cap)
        self.assertIsNotNone(result.text)


if __name__ == "__main__":
    unittest.main()
