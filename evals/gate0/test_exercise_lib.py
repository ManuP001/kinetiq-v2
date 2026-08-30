#!/usr/bin/env python3
"""Unit tests for exercise_lib.py, including the medium->med severity alias against the real
exercises/*.json data (EXERCISE_LIBRARY.md §4's cross-repo flag)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import exercise_lib  # noqa: E402


class TestNormalizeSeverity(unittest.TestCase):
    def test_medium_aliases_to_med(self):
        self.assertEqual(exercise_lib.normalize_severity("medium"), "med")

    def test_high_and_low_pass_through(self):
        self.assertEqual(exercise_lib.normalize_severity("high"), "high")
        self.assertEqual(exercise_lib.normalize_severity("low"), "low")

    def test_already_normalized_med_passes_through(self):
        self.assertEqual(exercise_lib.normalize_severity("med"), "med")

    def test_unknown_severity_raises(self):
        with self.assertRaises(exercise_lib.ExerciseLibraryError):
            exercise_lib.normalize_severity("critical")


class TestLoadFaultSeverities(unittest.TestCase):
    """Runs against the real kinetiq-v2/exercises/*.json -- confirms the alias actually bridges
    the "medium" the JSON files write today to the "med" the Stage-0 taxonomy expects."""

    def setUp(self):
        self.severities = exercise_lib.load_fault_severities()

    def test_known_exercises_present(self):
        for exercise_id in ("squat", "pushup", "lunge"):
            self.assertIn(exercise_id, self.severities)

    def test_all_severities_are_normalized(self):
        for exercise_id, faults in self.severities.items():
            for fault_id, severity in faults.items():
                self.assertIn(
                    severity, exercise_lib.VALID_SEVERITIES,
                    f"{exercise_id}.{fault_id} has non-normalized severity {severity!r}",
                )

    def test_squat_hip_and_knee_faults_have_expected_severity(self):
        # squat.json currently writes "high"/"medium" (not yet "med") -- this is the concrete
        # case the alias exists for.
        self.assertEqual(self.severities["squat"]["knee_cave_left"], "high")
        self.assertEqual(self.severities["squat"]["shallow_depth"], "med")

    def test_pushup_hip_sag_is_high_severity(self):
        self.assertEqual(self.severities["pushup"]["hip_sag"], "high")


if __name__ == "__main__":
    unittest.main()
