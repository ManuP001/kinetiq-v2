#!/usr/bin/env python3
"""Unit tests for detector/flag_hysteresis.py -- the flag-level temporal hysteresis +
visibility gate (SPRINT.md G2)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import gate_config  # noqa: E402
from detector.flag_hysteresis import (  # noqa: E402
    EXERCISE_SUSTAINED_FLAG_IDS,
    FlagHysteresisConfig,
    FlagOutcome,
    SUSTAINED_FLAG_IDS,
    evaluate_sustained_flag,
)
from detector.keypoint_map import POSE_MODEL_LANDMARKS  # noqa: E402

MOVENET = "movenet_17"

# A tight config with small, exact numbers, so tests reason about the mechanism rather than the
# real (placeholder) config.py values.
CFG = FlagHysteresisConfig(
    min_visibility=0.5,
    min_evaluable_frames=3,
    min_fraction_high_sev=0.6,
    min_fraction_med_sev=0.4,
    min_fraction_low_sev=0.2,
)

# hip_sag thresholds/landmarks for a straight-body vs. sagged-body pose, reused across tests.
THRESHOLDS = {"hip_sag_angle_min": 160}


def make_person(overrides, n=17, default_vis=0.9):
    """overrides: name -> (x, y, vis). Unlisted landmarks default to vis=default_vis so they
    don't accidentally starve a rule of visible evidence unless a test means to."""
    kp = [[0.5, 0.5, None, default_vis] for _ in range(n)]
    for name, (x, y, vis) in overrides.items():
        idx = POSE_MODEL_LANDMARKS[MOVENET][name]
        kp[idx] = [x, y, None, vis]
    return {"track_id": 0, "kp": kp, "box": [0.3, 0.2, 0.4, 0.6]}


def straight_body_frame(vis=0.9):
    """shoulder-hip-ankle in a straight line -- hip_sag_present() == False."""
    return (make_person({
        "left_shoulder": (0.3, 0.4, vis), "left_hip": (0.5, 0.4, vis), "left_ankle": (0.9, 0.4, vis),
        "right_shoulder": (0.3, 0.42, vis), "right_hip": (0.5, 0.42, vis), "right_ankle": (0.9, 0.42, vis),
    }), MOVENET)


def sagged_body_frame(vis=0.9):
    """hip dropped well below the shoulder-ankle line -- hip_sag_present() == True."""
    return (make_person({
        "left_shoulder": (0.3, 0.4, vis), "left_hip": (0.5, 0.75, vis), "left_ankle": (0.9, 0.4, vis),
        "right_shoulder": (0.3, 0.42, vis), "right_hip": (0.5, 0.77, vis), "right_ankle": (0.9, 0.42, vis),
    }), MOVENET)


class TestOneFrameFaultDoesNotFlag(unittest.TestCase):
    """The core SPRINT.md G2 fix: a fault present on only one frame out of many must NOT commit
    -- this is exactly the field hip-sag false positive."""

    def test_single_noisy_frame_among_clean_ones_is_absent(self):
        frames = [straight_body_frame() for _ in range(9)] + [sagged_body_frame()]
        outcome = evaluate_sustained_flag("hip_sag", frames, THRESHOLDS, "high", CFG)
        self.assertEqual(outcome, FlagOutcome.ABSENT)


class TestSustainedFaultDoesFlag(unittest.TestCase):
    def test_majority_sagged_frames_commits_the_flag(self):
        frames = [sagged_body_frame() for _ in range(8)] + [straight_body_frame() for _ in range(2)]
        outcome = evaluate_sustained_flag("hip_sag", frames, THRESHOLDS, "high", CFG)
        self.assertEqual(outcome, FlagOutcome.PRESENT)

    def test_exactly_at_the_required_fraction_commits(self):
        # med severity requires 0.4 -- 4 of 10 sagged frames should just clear it.
        frames = [sagged_body_frame() for _ in range(4)] + [straight_body_frame() for _ in range(6)]
        outcome = evaluate_sustained_flag("hip_sag", frames, THRESHOLDS, "med", CFG)
        self.assertEqual(outcome, FlagOutcome.PRESENT)

    def test_just_below_the_required_fraction_does_not_commit(self):
        frames = [sagged_body_frame() for _ in range(3)] + [straight_body_frame() for _ in range(7)]
        outcome = evaluate_sustained_flag("hip_sag", frames, THRESHOLDS, "med", CFG)
        self.assertEqual(outcome, FlagOutcome.ABSENT)


class TestSeverityChangesStrictness(unittest.TestCase):
    def test_same_evidence_passes_low_severity_but_not_high(self):
        # 3 of 10 sagged = 30% -- clears low (0.2), fails high (0.6).
        frames = [sagged_body_frame() for _ in range(3)] + [straight_body_frame() for _ in range(7)]
        low_outcome = evaluate_sustained_flag("hip_sag", frames, THRESHOLDS, "low", CFG)
        high_outcome = evaluate_sustained_flag("hip_sag", frames, THRESHOLDS, "high", CFG)
        self.assertEqual(low_outcome, FlagOutcome.PRESENT)
        self.assertEqual(high_outcome, FlagOutcome.ABSENT)

    def test_unknown_severity_raises(self):
        frames = [straight_body_frame()]
        with self.assertRaises(ValueError):
            evaluate_sustained_flag("hip_sag", frames, THRESHOLDS, "critical", CFG)


class TestVisibilityGate(unittest.TestCase):
    def test_low_visibility_frames_are_not_counted_as_evidence(self):
        # sagged, but every frame's involved landmarks are below FLAG_MIN_VISIBILITY (0.5) --
        # none of it counts, so there's too little evidence to say anything.
        frames = [sagged_body_frame(vis=0.1) for _ in range(10)]
        outcome = evaluate_sustained_flag("hip_sag", frames, THRESHOLDS, "high", CFG)
        self.assertEqual(outcome, FlagOutcome.INSUFFICIENT_EVIDENCE)

    def test_a_mostly_low_visibility_rep_reads_insufficient_evidence_not_false_accusation(self):
        # only 2 visible frames (both clean) -- below min_evaluable_frames (3), even though what
        # little evidence exists says "clean". This must not silently become "absent" (a
        # confident-sounding "no fault"), it must say "insufficient evidence".
        frames = (
            [straight_body_frame(vis=0.9) for _ in range(2)]
            + [sagged_body_frame(vis=0.1) for _ in range(8)]
        )
        outcome = evaluate_sustained_flag("hip_sag", frames, THRESHOLDS, "high", CFG)
        self.assertEqual(outcome, FlagOutcome.INSUFFICIENT_EVIDENCE)

    def test_high_visibility_frames_still_count_normally(self):
        frames = [sagged_body_frame(vis=0.95) for _ in range(8)] + [straight_body_frame(vis=0.95) for _ in range(2)]
        outcome = evaluate_sustained_flag("hip_sag", frames, THRESHOLDS, "high", CFG)
        self.assertEqual(outcome, FlagOutcome.PRESENT)

    def test_mixed_visibility_only_counts_the_visible_ones(self):
        # 3 clearly-sagged+visible, 7 sagged-but-invisible -- only the 3 visible ones count, and
        # 3 evaluable frames all showing "present" clears every severity's fraction.
        frames = (
            [sagged_body_frame(vis=0.9) for _ in range(3)]
            + [sagged_body_frame(vis=0.1) for _ in range(7)]
        )
        outcome = evaluate_sustained_flag("hip_sag", frames, THRESHOLDS, "high", CFG)
        self.assertEqual(outcome, FlagOutcome.PRESENT)


class TestMissingLandmarksAreNotEvidence(unittest.TestCase):
    def test_frames_missing_the_rules_landmarks_entirely_dont_count(self):
        # knee_cave_left needs left_ankle/left_knee -- omit them (defaults to vis=0.9 at a
        # meaningless (0.5,0.5) position, which IS visible but not a genuine reading. Use a
        # separate fault (knee_cave) with a person that has no legs at all: empty kp array.
        empty_person = {"track_id": 0, "kp": [], "box": [0, 0, 1, 1]}
        frames = [(empty_person, MOVENET) for _ in range(10)]
        outcome = evaluate_sustained_flag(
            "knee_cave_left", frames, {"knee_cave_x": 0.05}, "high", CFG
        )
        self.assertEqual(outcome, FlagOutcome.INSUFFICIENT_EVIDENCE)


class TestUnknownFaultId(unittest.TestCase):
    def test_rep_aggregate_flags_are_not_covered_and_raise(self):
        # shallow_pushup/shallow_lunge are rep-aggregate -- deliberately not in SUSTAINED_FLAG_IDS.
        self.assertNotIn("shallow_pushup", SUSTAINED_FLAG_IDS)
        self.assertNotIn("shallow_lunge", SUSTAINED_FLAG_IDS)
        with self.assertRaises(KeyError):
            evaluate_sustained_flag("shallow_pushup", [], {}, "med", CFG)

    def test_totally_unknown_fault_id_raises(self):
        with self.assertRaises(KeyError):
            evaluate_sustained_flag("not_a_real_flag", [], {}, "med", CFG)


class TestDefaultConfigUsesGateConfigValues(unittest.TestCase):
    def test_default_config_matches_config_py(self):
        default_cfg = FlagHysteresisConfig()
        self.assertEqual(default_cfg.min_visibility, gate_config.FLAG_MIN_VISIBILITY)
        self.assertEqual(default_cfg.min_evaluable_frames, gate_config.FLAG_MIN_EVALUABLE_FRAMES)
        self.assertEqual(
            default_cfg.min_fraction_high_sev, gate_config.FLAG_HYSTERESIS_MIN_FRACTION_HIGH_SEV
        )


class TestSustainedFlagIdsCoverage(unittest.TestCase):
    def test_covers_exactly_the_per_frame_flags(self):
        # Pins the inventory so a flag can't be added or dropped without a deliberate edit here.
        # excess_torso_lean joined 2026-09-05 (squat + lunge) -- see faults.py's module docstring.
        self.assertEqual(
            set(SUSTAINED_FLAG_IDS),
            {
                "knee_cave_left",
                "knee_cave_right",
                "shallow_depth",
                "elbow_flare",
                "hip_sag",
                "excess_torso_lean",
            },
        )

    def test_every_exercise_flag_has_a_predicate(self):
        # EXERCISE_SUSTAINED_FLAG_IDS must never name a flag flag_hysteresis can't evaluate --
        # adapter.py iterates it directly, so a typo there would silently drop a fault.
        for exercise_id, flag_ids in EXERCISE_SUSTAINED_FLAG_IDS.items():
            for flag_id in flag_ids:
                self.assertIn(flag_id, SUSTAINED_FLAG_IDS, f"{exercise_id}.{flag_id}")

    def test_every_exercise_flag_exists_in_that_exercises_library_entry(self):
        # ... and must correspond to a real common_errors entry, or the severity lookup in
        # adapter.py finds nothing and the flag is skipped without anyone noticing.
        library = gate_config.load_exercise_library()
        for exercise_id, flag_ids in EXERCISE_SUSTAINED_FLAG_IDS.items():
            declared = {
                err["error_id"]
                for err in library[exercise_id]["reference_keypoints"]["common_errors"]
            }
            for flag_id in flag_ids:
                self.assertIn(flag_id, declared, f"{exercise_id}.{flag_id} not in the library")


if __name__ == "__main__":
    unittest.main()
