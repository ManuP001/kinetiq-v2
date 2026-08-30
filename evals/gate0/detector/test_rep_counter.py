#!/usr/bin/env python3
"""Unit tests for detector/rep_counter.py."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from detector.rep_counter import RepCounterConfig, count_reps  # noqa: E402

# Smoothing off (window=1) for most tests so exact input angles pass straight through and the
# assertions are about the valley/tempo logic, not the median filter (that's tested separately
# in test_geometry.py).
CFG = RepCounterConfig(
    smoothing_window_frames=1,
    hysteresis_deg=5.0,
    top_angle_deg=160.0,
    min_excursion_deg=20.0,
    min_rep_duration_ms=200,
    max_rep_duration_ms=5000,
)


def series(pairs):
    """[(t_ms, angle), ...] -> samples list, angle may be None for a gap."""
    return list(pairs)


class TestCountReps(unittest.TestCase):
    def test_single_clean_rep(self):
        samples = series([
            (0, 175), (100, 175), (200, 120), (300, 80), (400, 120), (500, 175), (600, 175),
        ])
        events = count_reps(samples, CFG)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].idx, 1)
        self.assertAlmostEqual(events[0].min_angle_deg, 80)
        self.assertAlmostEqual(events[0].top_ref_deg, 175)

    def test_two_sequential_reps(self):
        samples = series([
            (0, 175), (200, 80), (400, 175), (600, 80), (800, 175),
        ])
        events = count_reps(samples, CFG)
        self.assertEqual([e.idx for e in events], [1, 2])

    def test_small_wobble_below_min_excursion_is_not_a_rep(self):
        # dips only 10 degrees -- below the 20-degree min_excursion floor.
        samples = series([(0, 175), (100, 165), (200, 175)])
        events = count_reps(samples, CFG)
        self.assertEqual(events, [])

    def test_too_fast_excursion_is_rejected_by_tempo_gate(self):
        # full-depth excursion but completes in 10ms -- far below min_rep_duration_ms (200).
        samples = series([(0, 175), (5, 80), (10, 175)])
        events = count_reps(samples, CFG)
        self.assertEqual(events, [])

    def test_slow_rep_still_registers(self):
        # a genuinely slow (3-0-1-0 tempo) rep, well within max_rep_duration_ms (5000).
        samples = series([(0, 175), (2000, 80), (4500, 175)])
        events = count_reps(samples, CFG)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].duration_ms, 4500)

    def test_too_slow_excursion_is_rejected_by_tempo_gate(self):
        samples = series([(0, 175), (10000, 80), (20000, 175)])
        events = count_reps(samples, CFG)
        self.assertEqual(events, [])

    def test_partial_depth_rep_still_counts_with_smaller_excursion(self):
        # only reaches 130 (a 45-degree excursion) instead of a deep 80 -- still well above
        # min_excursion_deg (20), so it must count, just with a shallower min_angle_deg.
        samples = series([(0, 175), (200, 130), (400, 175)])
        events = count_reps(samples, CFG)
        self.assertEqual(len(events), 1)
        self.assertAlmostEqual(events[0].min_angle_deg, 130)
        self.assertAlmostEqual(events[0].excursion_deg, 45)

    def test_none_gap_mid_descent_does_not_break_the_excursion(self):
        samples = series([(0, 175), (100, 120), (200, None), (300, 80), (400, 175)])
        events = count_reps(samples, CFG)
        self.assertEqual(len(events), 1)
        self.assertAlmostEqual(events[0].min_angle_deg, 80)

    def test_never_reaching_top_again_never_closes_the_rep(self):
        samples = series([(0, 175), (200, 80), (400, 140)])  # ascends but stalls below top_angle
        events = count_reps(samples, CFG)
        self.assertEqual(events, [])

    def test_empty_input(self):
        self.assertEqual(count_reps([], CFG), [])

    def test_default_config_uses_gate_config_values(self):
        default_cfg = RepCounterConfig()
        import gate_config
        self.assertEqual(default_cfg.top_angle_deg, gate_config.REP_COUNTER_TOP_ANGLE_DEG)


if __name__ == "__main__":
    unittest.main()
