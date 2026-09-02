#!/usr/bin/env python3
"""Unit tests for labeling/templates.py: blank CSV writer + fault-id listing against the real
exercise library (read-only; never modifies exercises/*.json)."""
from __future__ import annotations

import csv
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from labeling.csv_schema import CLIP_COLUMNS, REP_COLUMNS  # noqa: E402
from labeling.templates import fault_ids_by_exercise, format_fault_ids, write_templates  # noqa: E402


class TestWriteTemplates(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_writes_header_only_csvs_matching_the_schema(self):
        clips_path, reps_path = write_templates(self.tmpdir)

        with clips_path.open(newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))
        self.assertEqual(len(rows), 1)
        self.assertEqual(tuple(rows[0]), CLIP_COLUMNS)

        with reps_path.open(newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))
        self.assertEqual(len(rows), 1)
        self.assertEqual(tuple(rows[0]), REP_COLUMNS)

    def test_creates_missing_out_dir(self):
        out_dir = self.tmpdir / "nested" / "label_work"
        write_templates(out_dir)
        self.assertTrue(out_dir.is_dir())


class TestFaultIdsByExercise(unittest.TestCase):
    def test_squat_faults_come_from_the_real_exercise_library(self):
        by_exercise = fault_ids_by_exercise()
        self.assertIn("squat", by_exercise)
        self.assertIn("knee_cave_left", by_exercise["squat"])
        self.assertIn("shallow_depth", by_exercise["squat"])

    def test_format_fault_ids_for_known_exercise(self):
        text = format_fault_ids("pushup")
        self.assertIn("hip_sag", text)

    def test_format_fault_ids_for_unknown_exercise_names_known_ones(self):
        text = format_fault_ids("not_a_real_exercise")
        self.assertIn("unknown exercise", text)
        self.assertIn("squat", text)


if __name__ == "__main__":
    unittest.main()
