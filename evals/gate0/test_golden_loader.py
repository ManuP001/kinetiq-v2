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

from golden_loader import GoldenSetError, _load_detected, load_golden  # noqa: E402

FIXTURE_DIR = Path(__file__).resolve().parent / "golden"


def _write(dir_: Path, name: str, obj) -> None:
    (dir_ / name).write_text(json.dumps(obj), encoding="utf-8")


def _write_lines(dir_: Path, name: str, lines) -> None:
    (dir_ / name).write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")


class TestLoadGoldenOnFixture(unittest.TestCase):
    def test_loads_all_synthetic_clips(self):
        clips = load_golden(FIXTURE_DIR)
        self.assertEqual(len(clips), 8)
        by_id = {c.clip_id: c for c in clips}
        self.assertIn("squat_bench_phantom_001", by_id)
        self.assertEqual(by_id["squat_bench_phantom_001"].clip_type, "phantom_bench")
        self.assertEqual(by_id["squat_bench_phantom_001"].detected_reps, 0)
        self.assertEqual(by_id["pushup_phantom_empty_001"].clip_type, "phantom_empty")
        self.assertEqual(by_id["pushup_phantom_empty_001"].detected_reps, 0)

    def test_lunge_is_also_covered(self):
        clips = load_golden(FIXTURE_DIR)
        by_id = {c.clip_id: c for c in clips}
        clip = by_id["lunge_clean_001"]
        self.assertEqual(clip.exercise, "lunge")
        self.assertEqual(clip.detected_reps, clip.actual_reps)

    def test_pose_model_is_read_from_keypoints_file(self):
        clips = load_golden(FIXTURE_DIR)
        by_id = {c.clip_id: c for c in clips}
        self.assertEqual(by_id["pushup_good_side_001"].pose_model, "blazepose_33")
        self.assertEqual(by_id["pushup_bystander_001"].pose_model, "movenet_17")

    def test_bystander_clip_has_subject_lock_data(self):
        clips = load_golden(FIXTURE_DIR)
        by_id = {c.clip_id: c for c in clips}
        clip = by_id["pushup_bystander_001"]
        lock = clip.subject_lock
        self.assertEqual(lock["frames_total"], clip.subject_lock["frames_total"])
        self.assertGreater(lock["frames_total"], 0)
        # the detector locked the right person (subject_track_id 0) the whole clip.
        self.assertEqual(lock["frames_on_expected_subject"], lock["frames_total"])

    def test_scoped_exercises_are_computed_by_run_detector(self):
        # squat/pushup/lunge are all within detector.adapter's Stage-1 scope -- no clip should
        # need to fall back to a bootstrap detected.json.
        clips = load_golden(FIXTURE_DIR)
        for clip in clips:
            self.assertEqual(clip.detector_source, "run_detector", clip.clip_id)

    def test_seeded_faults_are_recovered_on_badform_clip(self):
        clips = load_golden(FIXTURE_DIR)
        by_id = {c.clip_id: c for c in clips}
        clip = by_id["squat_badform_001"]
        flagged = [r for r in clip.det_reps if r["flags"]]
        self.assertEqual(len(flagged), 2)  # matches the 2 seeded knee_cave reps

    def test_partial_depth_reps_still_count(self):
        clips = load_golden(FIXTURE_DIR)
        by_id = {c.clip_id: c for c in clips}
        clip = by_id["squat_partial_depth_001"]
        self.assertEqual(clip.detected_reps, clip.actual_reps)


class TestLoadDetectedFallback(unittest.TestCase):
    """_load_detected in isolation, for the bootstrap path -- no exercise in the current library
    is unscoped by the Stage-1 detector, so this can't be exercised through load_golden() with
    real data yet (it exists for a future exercise added before its own detector logic lands)."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_falls_back_to_bootstrap_file_for_an_unscoped_exercise(self):
        bootstrap = {
            "detected_reps": 3,
            "reps": [{"idx": i, "flags": [], "form_score": 8.0} for i in range(1, 4)],
            "subject_lock": {"frames_total": 100, "frames_on_expected_subject": 100},
            "coaching_cues": [],
        }
        _write(self.tmpdir, "unscoped_clip_001.detected.json", bootstrap)
        detected, source = _load_detected(
            "unscoped_clip_001", self.tmpdir, frames=[], exercise="deadlift", expected_track_id=0
        )
        self.assertEqual(source, "bootstrap")
        self.assertEqual(detected["detected_reps"], 3)

    def test_missing_bootstrap_file_for_an_unscoped_exercise_raises(self):
        with self.assertRaises(GoldenSetError):
            _load_detected(
                "missing_bootstrap_001", self.tmpdir, frames=[], exercise="deadlift",
                expected_track_id=0,
            )


class TestLoadGoldenValidation(unittest.TestCase):
    """Builds small broken copies of one fixture clip in a temp dir to exercise each failure
    path, rather than depending on the (valid-by-design) committed fixture staying broken."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.clip_id = "pushup_good_side_001"
        for suffix in (".labels.json", ".keypoints.jsonl"):
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

    def test_missing_detected_json_is_fine_for_a_detector_scoped_exercise(self):
        # pushup is within detector.adapter's Stage-1 scope -- no detected.json is needed at all
        # any more; run_detector recomputes it from the frozen keypoints (Stage-1 change from
        # Stage 0's bootstrap-only behaviour).
        _write(self.tmpdir, "MANIFEST.json", self.manifest)
        clips = load_golden(self.tmpdir)
        self.assertEqual(len(clips), 1)
        self.assertEqual(clips[0].detector_source, "run_detector")

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
