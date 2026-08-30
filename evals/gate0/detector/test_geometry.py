#!/usr/bin/env python3
"""Unit tests for detector/geometry.py."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from detector.geometry import (  # noqa: E402
    angle_deg,
    bbox_area,
    bbox_centroid,
    bbox_iou,
    median,
    median_filter,
)


class TestAngleDeg(unittest.TestCase):
    def test_straight_line_is_180(self):
        # a --- b --- c, all in a line -> fully extended
        self.assertAlmostEqual(angle_deg((0, 0), (1, 0), (2, 0)), 180.0, places=3)

    def test_right_angle_is_90(self):
        self.assertAlmostEqual(angle_deg((1, 0), (0, 0), (0, 1)), 90.0, places=3)

    def test_degenerate_point_returns_zero_not_crash(self):
        self.assertEqual(angle_deg((0, 0), (0, 0), (1, 1)), 0.0)


class TestMedian(unittest.TestCase):
    def test_odd_count(self):
        self.assertEqual(median([3, 1, 2]), 2)

    def test_even_count_averages_middle_two(self):
        self.assertEqual(median([1, 2, 3, 4]), 2.5)


class TestMedianFilter(unittest.TestCase):
    def test_smooths_a_single_spike(self):
        series = [100.0, 100.0, 5.0, 100.0, 100.0]  # spike at index 2
        out = median_filter(series, window=3)
        self.assertAlmostEqual(out[2], 100.0)  # spike absorbed by its neighbours

    def test_none_gap_with_no_valid_neighbours_stays_none(self):
        series = [None, None, None]
        out = median_filter(series, window=3)
        self.assertEqual(out, [None, None, None])

    def test_none_gap_with_some_valid_neighbours_is_filled(self):
        series = [10.0, None, 20.0]
        out = median_filter(series, window=3)
        self.assertIsNotNone(out[1])

    def test_rejects_zero_window(self):
        with self.assertRaises(ValueError):
            median_filter([1.0], window=0)


class TestBBoxHelpers(unittest.TestCase):
    def test_centroid(self):
        self.assertEqual(bbox_centroid([0, 0, 10, 20]), (5, 10))

    def test_area(self):
        self.assertEqual(bbox_area([0, 0, 4, 5]), 20)

    def test_iou_identical_boxes_is_one(self):
        box = [0.1, 0.1, 0.4, 0.6]
        self.assertAlmostEqual(bbox_iou(box, box), 1.0)

    def test_iou_disjoint_boxes_is_zero(self):
        self.assertEqual(bbox_iou([0, 0, 1, 1], [5, 5, 1, 1]), 0.0)

    def test_iou_partial_overlap(self):
        a = [0, 0, 2, 2]   # area 4
        b = [1, 1, 2, 2]   # area 4, overlap = 1x1 = 1
        # union = 4 + 4 - 1 = 7
        self.assertAlmostEqual(bbox_iou(a, b), 1 / 7)


if __name__ == "__main__":
    unittest.main()
