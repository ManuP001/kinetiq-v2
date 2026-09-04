#!/usr/bin/env python3
"""Unit tests for prototype_api/cues.py, against the REAL exercise library (not a fixture) --
this is what proves the library's cue text genuinely fits LIVE_CUE_MAX_WORDS (or doesn't).

squat.json's shallow_depth and pushup.json's shallow_pushup cues were originally found over the
word cap by this exact test file; both have since been shortened in the exercise library (a
separate, independent fix -- not this task's), so the regression tests below now assert they stay
under the cap rather than that they're over it. test_over_cap_cue_is_flagged_not_hidden covers the
over-word-cap MECHANISM itself against a synthetic fixture, so that coverage doesn't depend on the
real library's copy staying broken."""
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

    def test_squat_shallow_depth_cue_is_within_the_word_cap(self):
        # Was over-cap (10 words, "Sit a little deeper -- hip crease to knee level"); the
        # exercise library has since shortened it. Regression guard, not the over-cap mechanism
        # test -- see test_over_cap_cue_is_flagged_not_hidden for that, against a synthetic
        # fixture that doesn't depend on the real library's copy staying broken.
        result = cue_for_rep(SQUAT, ["shallow_depth"])
        self.assertIsNotNone(result.text)
        self.assertFalse(result.over_word_cap, result.text)

    def test_pushup_good_rep_and_elbow_flare_and_hip_sag_are_within_the_word_cap(self):
        for flags in ([], ["elbow_flare"], ["hip_sag"]):
            with self.subTest(flags=flags):
                result = cue_for_rep(PUSHUP, flags)
                self.assertIsNotNone(result.text)
                self.assertFalse(result.over_word_cap, result.text)

    def test_pushup_shallow_pushup_cue_is_within_the_word_cap(self):
        # Was over-cap (9 words, "Go a little lower -- elbows to 90 degrees"); the exercise
        # library has since shortened it. Regression guard, same reasoning as the squat test above.
        result = cue_for_rep(PUSHUP, ["shallow_pushup"])
        self.assertIsNotNone(result.text)
        self.assertFalse(result.over_word_cap, result.text)

    def test_over_cap_cue_is_flagged_not_hidden(self):
        # The over-word-cap MECHANISM itself, against a synthetic fixture -- doesn't depend on
        # any particular real exercise's cue text staying broken to keep testing this path.
        synthetic_exercise = {
            "coaching_cues": {
                "good_rep": "Nice rep",
                "flag_cues": {"some_flag": "This cue text is deliberately far too many words long"},
            }
        }
        result = cue_for_rep(synthetic_exercise, ["some_flag"])
        self.assertTrue(result.over_word_cap)
        self.assertIsNotNone(result.text)  # still returned, never hidden


if __name__ == "__main__":
    unittest.main()
