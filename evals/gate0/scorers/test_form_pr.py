#!/usr/bin/env python3
"""Unit tests for scorers/form_pr.py -- TP/FP/FN counting (incl. the phantom->FP and
missed->FN edge cases) and severity-floor gating."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

# evals/gate0/ on sys.path: needed for `import gate_config` and the `scorers.` package import.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import gate_config  # noqa: E402
from scorers.form_pr import (  # noqa: E402
    PR,
    gate_flag,
    gate_form_pr,
    score_clip_form_pr,
)


def gt(idx, faults):
    return {"idx": idx, "faults": faults}


def det(idx, flags):
    return {"idx": idx, "flags": flags}


class TestScoreClipFormPr(unittest.TestCase):
    def test_true_positive_and_true_negative(self):
        gt_reps = [gt(1, []), gt(2, ["hip_sag"])]
        det_reps = [det(1, []), det(2, ["hip_sag"])]
        per_flag = score_clip_form_pr(gt_reps, det_reps)
        self.assertEqual(per_flag["hip_sag"].tp, 1)
        self.assertEqual(per_flag["hip_sag"].fp, 0)
        self.assertEqual(per_flag["hip_sag"].fn, 0)

    def test_false_positive_on_matched_pair(self):
        # detector accuses a genuinely clean rep -- false accusation.
        gt_reps = [gt(1, [])]
        det_reps = [det(1, ["hip_sag"])]
        per_flag = score_clip_form_pr(gt_reps, det_reps)
        self.assertEqual(per_flag["hip_sag"].fp, 1)
        self.assertEqual(per_flag["hip_sag"].tp, 0)

    def test_false_negative_on_matched_pair(self):
        # a real fault the detector didn't flag.
        gt_reps = [gt(1, ["hip_sag"])]
        det_reps = [det(1, [])]
        per_flag = score_clip_form_pr(gt_reps, det_reps)
        self.assertEqual(per_flag["hip_sag"].fn, 1)
        self.assertEqual(per_flag["hip_sag"].tp, 0)

    def test_phantom_rep_flag_counts_as_false_positive(self):
        # extra detected rep beyond ground truth, carrying a flag -- fabricated fault.
        gt_reps = [gt(1, [])]
        det_reps = [det(1, []), det(2, ["hip_sag"])]
        per_flag = score_clip_form_pr(gt_reps, det_reps)
        self.assertEqual(per_flag["hip_sag"].fp, 1)
        self.assertEqual(per_flag["hip_sag"].tp, 0)
        self.assertEqual(per_flag["hip_sag"].fn, 0)

    def test_missed_rep_fault_counts_as_false_negative(self):
        # extra ground-truth rep the detector never produced, that had a real fault.
        gt_reps = [gt(1, []), gt(2, ["hip_sag"])]
        det_reps = [det(1, [])]
        per_flag = score_clip_form_pr(gt_reps, det_reps)
        self.assertEqual(per_flag["hip_sag"].fn, 1)
        self.assertEqual(per_flag["hip_sag"].tp, 0)
        self.assertEqual(per_flag["hip_sag"].fp, 0)

    def test_empty_clip_yields_no_flags(self):
        self.assertEqual(score_clip_form_pr([], []), {})


class TestGateFlag(unittest.TestCase):
    def test_high_severity_uses_high_floors(self):
        pr = PR(tp=9, fp=1, fn=6)  # precision .90, recall .60
        result = gate_flag(pr, "high")
        self.assertEqual(result.precision_floor, gate_config.FORM_PRECISION_FLOOR_HIGH_SEV)
        self.assertEqual(result.recall_floor, gate_config.FORM_RECALL_FLOOR_HIGH_SEV)
        self.assertAlmostEqual(result.precision, 0.9)
        self.assertAlmostEqual(result.recall, 0.6)
        self.assertTrue(result.precision_pass)
        self.assertTrue(result.recall_pass)

    def test_high_severity_fails_below_precision_floor(self):
        pr = PR(tp=8, fp=2, fn=0)  # precision .80 < .90 floor
        result = gate_flag(pr, "high")
        self.assertFalse(result.precision_pass)
        self.assertFalse(result.passed)

    def test_med_severity_uses_med_floors(self):
        pr = PR(tp=3, fp=1, fn=1)  # precision .75, recall .75
        result = gate_flag(pr, "med")
        self.assertEqual(result.precision_floor, gate_config.FORM_PRECISION_FLOOR_MED_SEV)
        self.assertEqual(result.recall_floor, gate_config.FORM_RECALL_FLOOR_MED_SEV)
        self.assertTrue(result.precision_pass)
        self.assertTrue(result.recall_pass)

    def test_low_severity_has_no_floor_and_always_passes(self):
        pr = PR(tp=0, fp=10, fn=10)  # would fail any real floor
        result = gate_flag(pr, "low")
        self.assertIsNone(result.precision_floor)
        self.assertIsNone(result.recall_floor)
        self.assertTrue(result.passed)

    def test_no_observations_is_a_vacuous_pass(self):
        result = gate_flag(PR(), "high")
        self.assertIsNone(result.precision)
        self.assertIsNone(result.recall)
        self.assertTrue(result.passed)


class TestGateFormPr(unittest.TestCase):
    def test_unknown_flag_raises(self):
        per_exercise = {"squat": {"mystery_flag": PR(tp=1)}}
        with self.assertRaises(ValueError):
            gate_form_pr(per_exercise, severities={"squat": {}})

    def test_looks_up_severity_per_flag(self):
        per_exercise = {
            "squat": {
                "knee_cave_left": PR(tp=9, fp=1, fn=6),  # high
                "shallow_depth": PR(tp=3, fp=1, fn=1),  # med
            }
        }
        severities = {"squat": {"knee_cave_left": "high", "shallow_depth": "med"}}
        gated = gate_form_pr(per_exercise, severities)
        self.assertEqual(gated["squat"]["knee_cave_left"].severity, "high")
        self.assertEqual(gated["squat"]["shallow_depth"].severity, "med")


if __name__ == "__main__":
    unittest.main()
