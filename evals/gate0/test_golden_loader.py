#!/usr/bin/env python3
"""Unit tests for golden_loader.py: the real synthetic fixture must load cleanly, and common
schema violations must raise GoldenSetError with a message naming the clip."""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from golden_loader import GoldenSetError, load_golden  # noqa: E402

FIXTURE_DIR = Path(__file__).resolve().parent / "golden"


def _write(dir_: Path, name: str, obj) -> None:
    (dir_ / name).write_text(json.dumps(obj), encoding="utf-8")


def _write_lines(dir_: Path, name: str, lines) -> None:
    (dir_ / name).write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")


class TestLoadGoldenOnFixture(unittest.TestCase):
    def test_loads_all_synthetic_clips(self):
        clips = load_golden(FIXTURE_DIR)
        self.assertEqual(len(clips), 4)
        by_id = {c.clip_id: c for c in clips}
        self.assertIn("squat_bench_phantom_001", by_id)
        self.assertEqual(by_id["squat_bench_phantom_001"].clip_type, "phantom_bench")
        self.assertEqual(by_id["squat_bench_phantom_001"].detected_reps, 0)

    def test_pose_model_is_read_from_keypoints_file(self):
        clips = load_golden(FIXTURE_DIR)
        by_id = {c.clip_id: c for c in clips}
        self.assertEqual(by_id["pushup_good_side_001"].pose_model, "blazepose_33")
        self.assertEqual(by_id["pushup_bystander_001"].pose_model, "movenet_17")

    def test_bystander_clip_has_subject_lock_data(self):
        clips = load_golden(FIXTURE_DIR)
        by_id = {c.clip_id: c for c in clips}
        lock = by_id["pushup_bystander_001"].subject_lock
        self.assertEqual(lock["frames_total"], 900)


class TestLoadGoldenValidation(unittest.TestCase):
    """Builds small broken copies of one fixture clip in a temp dir to exercise each failure
    path, rather than depending on the (valid-by-design) committed fixture staying broken."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.clip_id = "pushup_good_side_001"
        for suffix in (".labels.json", ".detected.json", ".keypoints.jsonl"):
            shutil.copy(FIXTURE_DIR / f"{self.clip_id}{suffix}", self.tmpdir / f"{self.clip_id}{suffix}")
        self.manifest = json.loads((FIXTURE_DIR / "MANIFEST.json").read_text(encoding="utf-8"))
        self.manifest["clips"] = [
            c for c in self.manifest["clips"] if c["clip_id"] == self.clip_id
        ]

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _labels(self):
        return json.loads((self.tmpdir / f"{self.clip_id}.labels.json").read_text(encoding="utf-8"))

    def test_unknown_fault_id_raises(self):
        labels = self._labels()
        labels["ground_truth"]["reps"][0]["faults"] = ["not_a_real_fault"]
        _write(self.tmpdir, f"{self.clip_id}.labels.json", labels)
        _write(self.tmpdir, "MANIFEST.json", self.manifest)
        with self.assertRaises(GoldenSetError):
            load_golden(self.tmpdir)

    def test_unknown_clip_type_raises(self):
        labels = self._labels()
        labels["clip_type"] = "not_a_real_clip_type"
        _write(self.tmpdir, f"{self.clip_id}.labels.json", labels)
        _write(self.tmpdir, "MANIFEST.json", self.manifest)
        with self.assertRaises(GoldenSetError):
            load_golden(self.tmpdir)

    def test_phantom_like_clip_with_nonzero_actual_reps_raises(self):
        labels = self._labels()
        labels["clip_type"] = "bystander"
        labels["ground_truth"]["actual_reps"] = 3
        _write(self.tmpdir, f"{self.clip_id}.labels.json", labels)
        _write(self.tmpdir, "MANIFEST.json", self.manifest)
        with self.assertRaises(GoldenSetError):
            load_golden(self.tmpdir)

    def test_missing_detected_json_raises(self):
        (self.tmpdir / f"{self.clip_id}.detected.json").unlink()
        _write(self.tmpdir, "MANIFEST.json", self.manifest)
        with self.assertRaises(GoldenSetError):
            load_golden(self.tmpdir)

    def test_malformed_keypoint_raises(self):
        _write_lines(self.tmpdir, f"{self.clip_id}.keypoints.jsonl", [
            {"t_ms": 0, "pose_model": "movenet_17",
             "people": [{"track_id": 0, "kp": [[0.1, 0.2]]}]},  # only 2 elements, need 4
        ])
        _write(self.tmpdir, "MANIFEST.json", self.manifest)
        with self.assertRaises(GoldenSetError):
            load_golden(self.tmpdir)

    def test_unknown_exercise_raises(self):
        labels = self._labels()
        labels["exercise"] = "not_a_real_exercise"
        _write(self.tmpdir, f"{self.clip_id}.labels.json", labels)
        _write(self.tmpdir, "MANIFEST.json", self.manifest)
        with self.assertRaises(GoldenSetError):
            load_golden(self.tmpdir)


if __name__ == "__main__":
    unittest.main()
