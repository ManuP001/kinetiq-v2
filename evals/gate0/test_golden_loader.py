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

from golden_loader import GoldenSetError, _load_detected, load_golden, load_golden_poses  # noqa: E402

FIXTURE_DIR = Path(__file__).resolve().parent / "golden"


def _write(dir_: Path, name: str, obj) -> None:
    (dir_ / name).write_text(json.dumps(obj), encoding="utf-8")


def _write_lines(dir_: Path, name: str, lines) -> None:
    (dir_ / name).write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")


class TestLoadGoldenOnFixture(unittest.TestCase):
    def test_loads_all_synthetic_clips(self):
        clips = load_golden(FIXTURE_DIR)
        self.assertEqual(len(clips), 11)
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


class TestFlagHysteresisFixtures(unittest.TestCase):
    """Stage 3 (SPRINT.md G2): the exact scenario the field hip-sag false positive was --
    proven end-to-end through the harness, not just detector/test_flag_hysteresis.py's unit
    tests over synthetic frame lists."""

    def setUp(self):
        self.by_id = {c.clip_id: c for c in load_golden(FIXTURE_DIR)}

    def test_one_noisy_frame_does_not_flag(self):
        clip = self.by_id["pushup_noisy_hipsag_side_001"]
        self.assertEqual(clip.detected_reps, 1)
        self.assertNotIn("hip_sag", clip.det_reps[0]["flags"])
        self.assertEqual(clip.gt_reps[0]["faults"], [])  # PT confirmed clean

    def test_sustained_fault_does_flag(self):
        clip = self.by_id["pushup_sustained_hipsag_side_001"]
        self.assertEqual(clip.detected_reps, 1)
        self.assertIn("hip_sag", clip.det_reps[0]["flags"])
        self.assertEqual(clip.gt_reps[0]["faults"], ["hip_sag"])

    def test_low_visibility_reads_insufficient_evidence_not_an_accusation(self):
        clip = self.by_id["pushup_lowvis_hipsag_side_001"]
        self.assertEqual(clip.detected_reps, 1)
        self.assertNotIn("hip_sag", clip.det_reps[0]["flags"])
        self.assertIn("hip_sag", clip.det_reps[0]["insufficient_evidence"])


class TestLoadGoldenPoses(unittest.TestCase):
    """Stage 2: golden/poses/<model>/squat_bakeoff_side_001.keypoints.jsonl, one clip captured
    under all 3 candidate pose models, sharing the single model-independent labels.json
    (GOLDEN_SET_PROTOCOL.md §2)."""

    def test_unknown_pose_model_returns_empty_list(self):
        self.assertEqual(load_golden_poses(FIXTURE_DIR, "some_future_model"), [])

    def test_loads_the_bakeoff_clip_for_each_candidate_model(self):
        for pose_model in ("blazepose_33", "movenet_17", "rtmpose_halpe26"):
            clips = load_golden_poses(FIXTURE_DIR, pose_model)
            self.assertEqual(len(clips), 1, pose_model)
            self.assertEqual(clips[0].clip_id, "squat_bakeoff_side_001")
            self.assertEqual(clips[0].pose_model, pose_model)

    def test_flat_layout_clips_are_not_picked_up(self):
        # squat_badform_001 etc. only exist as flat golden/<clip_id>.keypoints.jsonl -- they
        # must not leak into a poses/<model>/ result just because they share a golden_dir.
        clips = load_golden_poses(FIXTURE_DIR, "blazepose_33")
        clip_ids = {c.clip_id for c in clips}
        self.assertNotIn("squat_badform_001", clip_ids)

    def test_run_detector_output_is_identical_across_models_for_equivalent_skeletons(self):
        by_model = {
            pose_model: load_golden_poses(FIXTURE_DIR, pose_model)[0]
            for pose_model in ("blazepose_33", "movenet_17", "rtmpose_halpe26")
        }
        reference = by_model["movenet_17"]
        for pose_model, clip in by_model.items():
            self.assertEqual(clip.detected_reps, reference.detected_reps, pose_model)
            self.assertEqual(clip.det_reps, reference.det_reps, pose_model)

    def test_pose_model_directory_frame_mismatch_raises(self):
        tmpdir = Path(tempfile.mkdtemp())
        try:
            shutil.copy(
                FIXTURE_DIR / "squat_bakeoff_side_001.labels.json",
                tmpdir / "squat_bakeoff_side_001.labels.json",
            )
            wrong_dir = tmpdir / "poses" / "movenet_17"
            wrong_dir.mkdir(parents=True)
            # copy blazepose_33's file (declares pose_model "blazepose_33") into the movenet_17
            # directory -- a directory/frame mismatch.
            shutil.copy(
                FIXTURE_DIR / "poses" / "blazepose_33" / "squat_bakeoff_side_001.keypoints.jsonl",
                wrong_dir / "squat_bakeoff_side_001.keypoints.jsonl",
            )
            with self.assertRaises(GoldenSetError):
                load_golden_poses(tmpdir, "movenet_17")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


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
        labels["clip_type"] = "phantom_empty"
        labels["ground_truth"]["actual_reps"] = 3
        _write(self.tmpdir, f"{self.clip_id}.labels.json", labels)
        _write(self.tmpdir, "MANIFEST.json", self.manifest)
        with self.assertRaises(GoldenSetError):
            load_golden(self.tmpdir)

    def test_bystander_with_nonzero_actual_reps_does_not_raise(self):
        # bystander is NOT phantom-like (EVAL_HARNESS_STAGE0_SPEC.md §5/§7,
        # EXERCISE_LIBRARY.md §5, ROADMAP.md): the user's real rep count is > 0 by construction.
        labels = self._labels()
        labels["clip_type"] = "bystander"
        labels["ground_truth"]["actual_reps"] = 3
        _write(self.tmpdir, f"{self.clip_id}.labels.json", labels)
        _write(self.tmpdir, "MANIFEST.json", self.manifest)
        clips = load_golden(self.tmpdir)
        self.assertEqual(clips[0].clip_type, "bystander")
        self.assertEqual(clips[0].actual_reps, 3)

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
