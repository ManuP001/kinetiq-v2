#!/usr/bin/env python3
"""Unit tests for labeling/export.py: CSV templates -> labels.json + MANIFEST.json."""
from __future__ import annotations

import csv
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from labeling.csv_schema import LabelExportError  # noqa: E402
from labeling.export import build_clip_labels, export_labels  # noqa: E402


def _write_csv(path: Path, header: tuple, rows: list) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for row in rows:
            writer.writerow(row)


CLIP_HEADER = (
    "clip_id", "exercise", "clip_type", "view", "lighting", "fitness_level",
    "actual_reps", "num_people_in_frame", "subject_track_id", "labeler", "pt_verified",
)
REP_HEADER = ("clip_id", "rep_idx", "faults")


class TestExportLabels(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_good_normal_clip_exports_valid_labels_and_manifest(self):
        clips_csv = self.tmpdir / "clips.csv"
        reps_csv = self.tmpdir / "reps.csv"
        _write_csv(clips_csv, CLIP_HEADER, [
            ("squat_clean_side_001", "squat", "normal", "side", "daylight", "intermediate",
             "2", "1", "", "PT-AR", "true"),
        ])
        _write_csv(reps_csv, REP_HEADER, [
            ("squat_clean_side_001", "1", ""),
            ("squat_clean_side_001", "2", "knee_cave_left"),
        ])
        golden_dir = self.tmpdir / "golden"

        written = export_labels(clips_csv, reps_csv, golden_dir)

        self.assertEqual(len(written), 1)
        labels = json.loads((golden_dir / "squat_clean_side_001.labels.json").read_text())
        self.assertEqual(labels["clip_id"], "squat_clean_side_001")
        self.assertEqual(labels["exercise"], "squat")
        self.assertEqual(labels["view"], "side")
        self.assertEqual(labels["subject"], {
            "expected": "user", "num_people_in_frame": 1, "subject_track_id": None,
        })
        self.assertEqual(labels["ground_truth"]["actual_reps"], 2)
        self.assertEqual(labels["ground_truth"]["reps"], [
            {"idx": 1, "faults": []},
            {"idx": 2, "faults": ["knee_cave_left"]},
        ])
        self.assertTrue(labels["pt_verified"])

        manifest = json.loads((golden_dir / "MANIFEST.json").read_text())
        self.assertEqual(len(manifest["clips"]), 1)
        self.assertEqual(manifest["clips"][0]["clip_id"], "squat_clean_side_001")
        self.assertEqual(manifest["clips"][0]["num_people_in_frame"], 1)

    def test_phantom_clip_needs_no_rep_rows(self):
        clips_csv = self.tmpdir / "clips.csv"
        reps_csv = self.tmpdir / "reps.csv"
        _write_csv(clips_csv, CLIP_HEADER, [
            ("squat_bench_phantom_001", "squat", "phantom_bench", "diagonal", "daylight", "",
             "0", "0", "", "PT-AR", "true"),
        ])
        _write_csv(reps_csv, REP_HEADER, [])
        golden_dir = self.tmpdir / "golden"

        export_labels(clips_csv, reps_csv, golden_dir)

        labels = json.loads((golden_dir / "squat_bench_phantom_001.labels.json").read_text())
        self.assertEqual(labels["ground_truth"], {"actual_reps": 0, "reps": []})
        self.assertEqual(labels["view"], "diagonal")
        self.assertIsNone(labels["fitness_level"])  # blank cell -> None

    def test_bystander_clip_carries_subject_track_id_and_real_reps(self):
        # bystander is NOT phantom-like (EVAL_HARNESS_STAGE0_SPEC.md §5/§7): the user really
        # exercises with a real rep count while a second person is in frame.
        clips_csv = self.tmpdir / "clips.csv"
        reps_csv = self.tmpdir / "reps.csv"
        _write_csv(clips_csv, CLIP_HEADER, [
            ("pushup_bystander_002", "pushup", "bystander", "front", "dim_room", "beginner",
             "2", "2", "0", "PT-AR", "true"),
        ])
        _write_csv(reps_csv, REP_HEADER, [
            ("pushup_bystander_002", "1", ""),
            ("pushup_bystander_002", "2", ""),
        ])
        golden_dir = self.tmpdir / "golden"

        export_labels(clips_csv, reps_csv, golden_dir)

        labels = json.loads((golden_dir / "pushup_bystander_002.labels.json").read_text())
        self.assertEqual(labels["subject"]["subject_track_id"], 0)
        self.assertEqual(labels["subject"]["num_people_in_frame"], 2)
        self.assertEqual(labels["ground_truth"]["actual_reps"], 2)
        self.assertEqual(len(labels["ground_truth"]["reps"]), 2)

    def test_reexport_replaces_only_the_matching_manifest_row(self):
        clips_csv = self.tmpdir / "clips.csv"
        reps_csv = self.tmpdir / "reps.csv"
        golden_dir = self.tmpdir / "golden"
        _write_csv(clips_csv, CLIP_HEADER, [
            ("clip_a", "squat", "normal", "side", "daylight", "beginner",
             "1", "1", "", "PT-AR", "false"),
        ])
        _write_csv(reps_csv, REP_HEADER, [("clip_a", "1", "")])
        export_labels(clips_csv, reps_csv, golden_dir)

        _write_csv(clips_csv, CLIP_HEADER, [
            ("clip_b", "pushup", "normal", "side", "daylight", "beginner",
             "1", "1", "", "PT-AR", "false"),
        ])
        _write_csv(reps_csv, REP_HEADER, [("clip_b", "1", "")])
        export_labels(clips_csv, reps_csv, golden_dir)

        manifest = json.loads((golden_dir / "MANIFEST.json").read_text())
        ids = {row["clip_id"] for row in manifest["clips"]}
        self.assertEqual(ids, {"clip_a", "clip_b"})

    def test_duplicate_clip_id_raises(self):
        clips_csv = self.tmpdir / "clips.csv"
        reps_csv = self.tmpdir / "reps.csv"
        _write_csv(clips_csv, CLIP_HEADER, [
            ("dup", "squat", "normal", "side", "daylight", "beginner", "1", "1", "", "PT", "true"),
            ("dup", "squat", "normal", "side", "daylight", "beginner", "1", "1", "", "PT", "true"),
        ])
        _write_csv(reps_csv, REP_HEADER, [])
        with self.assertRaises(LabelExportError):
            export_labels(clips_csv, reps_csv, self.tmpdir / "golden")

    def test_rep_row_with_unknown_clip_id_raises(self):
        clips_csv = self.tmpdir / "clips.csv"
        reps_csv = self.tmpdir / "reps.csv"
        _write_csv(clips_csv, CLIP_HEADER, [
            ("clip_a", "squat", "normal", "side", "daylight", "beginner",
             "1", "1", "", "PT", "true"),
        ])
        _write_csv(reps_csv, REP_HEADER, [("clip_ghost", "1", "")])
        with self.assertRaises(LabelExportError):
            export_labels(clips_csv, reps_csv, self.tmpdir / "golden")

    def test_missing_column_raises(self):
        clips_csv = self.tmpdir / "clips.csv"
        with clips_csv.open("w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(("clip_id", "exercise"))  # missing most columns
        reps_csv = self.tmpdir / "reps.csv"
        _write_csv(reps_csv, REP_HEADER, [])
        with self.assertRaises(LabelExportError):
            export_labels(clips_csv, reps_csv, self.tmpdir / "golden")


class TestBuildClipLabels(unittest.TestCase):
    def test_missing_clip_id_raises(self):
        with self.assertRaises(LabelExportError):
            build_clip_labels({"exercise": "squat"}, [])


if __name__ == "__main__":
    unittest.main()
