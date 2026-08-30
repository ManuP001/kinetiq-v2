#!/usr/bin/env python3
"""Unit tests for scorers/rep_match.py -- EVAL_HARNESS_STAGE0_SPEC.md §11 requires: equal
counts, phantom (extra detected), missed (extra ground-truth), empty clip."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling modules, bare import

from rep_match import match_reps  # noqa: E402


class TestMatchReps(unittest.TestCase):
    def test_equal_counts(self):
        gt = ["gt1", "gt2", "gt3"]
        det = ["det1", "det2", "det3"]
        pairs = match_reps(gt, det)
        self.assertEqual(pairs, [("gt1", "det1"), ("gt2", "det2"), ("gt3", "det3")])

    def test_phantom_extra_detected(self):
        gt = ["gt1", "gt2"]
        det = ["det1", "det2", "det3"]
        pairs = match_reps(gt, det)
        self.assertEqual(len(pairs), 3)
        matched = [p for p in pairs if p[0] is not None and p[1] is not None]
        phantom = [p for p in pairs if p[0] is None]
        self.assertEqual(len(matched), 2)
        self.assertEqual(len(phantom), 1)
        self.assertEqual(phantom[0][1], "det3")

    def test_missed_extra_ground_truth(self):
        gt = ["gt1", "gt2", "gt3"]
        det = ["det1", "det2"]
        pairs = match_reps(gt, det)
        self.assertEqual(len(pairs), 3)
        matched = [p for p in pairs if p[0] is not None and p[1] is not None]
        missed = [p for p in pairs if p[1] is None]
        self.assertEqual(len(matched), 2)
        self.assertEqual(len(missed), 1)
        self.assertEqual(missed[0][0], "gt3")

    def test_empty_clip(self):
        self.assertEqual(match_reps([], []), [])

    def test_empty_gt_all_phantom(self):
        pairs = match_reps([], ["det1", "det2"])
        self.assertEqual(pairs, [(None, "det1"), (None, "det2")])

    def test_empty_det_all_missed(self):
        pairs = match_reps(["gt1", "gt2"], [])
        self.assertEqual(pairs, [("gt1", None), ("gt2", None)])

    def test_alignment_stays_monotonic(self):
        # 4 gt, 4 det, with a phantom in the middle and a miss near the end -- the matched
        # pairs must preserve relative order on both sides.
        gt = ["g1", "g2", "g3", "g4"]
        det = ["d1", "d2", "d3", "d4", "d5"]
        pairs = match_reps(gt, det)
        seen_gt = [p[0] for p in pairs if p[0] is not None]
        seen_det = [p[1] for p in pairs if p[1] is not None]
        self.assertEqual(seen_gt, gt)
        self.assertEqual(seen_det, det)


if __name__ == "__main__":
    unittest.main()
