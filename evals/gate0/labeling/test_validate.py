#!/usr/bin/env python3
"""Unit tests for labeling/validate.py, over tiny hand-built golden/ fixtures -- a good clip, a
phantom clip, a clip with a bad fault id, and a clip whose exercise-library entry is missing a
severity (a temp exercise-library override, since the real exercises/*.json always have one)."""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from labeling.validate import validate_golden_set  # noqa: E402

GOOD_KEYPOINT_FRAME = {
    "t_ms": 0, "pose_model": "movenet_17",
    "people": [{"track_id": 0, "kp": [[0.5, 0.5, None, 0.9]], "box": [0.4, 0.4, 0.2, 0.2]}],
}


def _write_json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj), encoding="utf-8")


def _write_manifest(golden_dir: Path, rows: list) -> None:
    _write_json(golden_dir / "MANIFEST.json", {"schema_version": 1, "golden_version": "test", "clips": rows})


def _manifest_row(labels: dict) -> dict:
    return {
        "clip_id": labels["clip_id"],
        "exercise": labels["exercise"],
        "clip_type": labels["clip_type"],
        "view": labels["view"],
        "lighting": labels["lighting"],
        "fitness_level": labels["fitness_level"],
        "num_people_in_frame": labels["subject"]["num_people_in_frame"],
        "labeler": labels["labeler"],
        "pt_verified": labels["pt_verified"],
    }


def _write_clip(golden_dir: Path, labels: dict, keypoints_pose_model: str | None = "movenet_17") -> None:
    _write_json(golden_dir / f"{labels['clip_id']}.labels.json", labels)
    if keypoints_pose_model:
        kp_dir = golden_dir / "poses" / keypoints_pose_model
        kp_dir.mkdir(parents=True, exist_ok=True)
        frame = dict(GOOD_KEYPOINT_FRAME, pose_model=keypoints_pose_model)
        (kp_dir / f"{labels['clip_id']}.keypoints.jsonl").write_text(
            json.dumps(frame) + "\n", encoding="utf-8"
        )


def _good_normal_labels(clip_id="squat_clean_side_001", faults=None) -> dict:
    faults = faults if faults is not None else []
    return {
        "schema_version": 1, "clip_id": clip_id, "exercise": "squat", "clip_type": "normal",
        "view": "side", "lighting": "daylight", "fitness_level": "intermediate",
        "subject": {"expected": "user", "num_people_in_frame": 1, "subject_track_id": 0},
        "ground_truth": {"actual_reps": 1, "reps": [{"idx": 1, "faults": faults}]},
        "labeler": "PT-AR", "pt_verified": True,
    }


def _phantom_labels(clip_id="squat_bench_phantom_001") -> dict:
    return {
        "schema_version": 1, "clip_id": clip_id, "exercise": "squat", "clip_type": "phantom_bench",
        "view": "diagonal", "lighting": "daylight", "fitness_level": None,
        "subject": {"expected": "user", "num_people_in_frame": 0, "subject_track_id": None},
        "ground_truth": {"actual_reps": 0, "reps": []},
        "labeler": "PT-AR", "pt_verified": True,
    }


class LabelingValidateTestCase(unittest.TestCase):
    def setUp(self):
        self.golden_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.golden_dir, ignore_errors=True)


class TestGoodClip(LabelingValidateTestCase):
    def test_good_normal_clip_has_no_errors(self):
        labels = _good_normal_labels()
        _write_clip(self.golden_dir, labels)
        _write_manifest(self.golden_dir, [_manifest_row(labels)])

        report = validate_golden_set(self.golden_dir)

        self.assertTrue(report.ok, report.format())
        self.assertEqual(report.errors, [])

    def test_missing_keypoints_is_a_warning_not_an_error(self):
        labels = _good_normal_labels()
        _write_clip(self.golden_dir, labels, keypoints_pose_model=None)
        _write_manifest(self.golden_dir, [_manifest_row(labels)])

        report = validate_golden_set(self.golden_dir)

        self.assertTrue(report.ok)
        self.assertEqual(len(report.warnings), 1)
        self.assertIn("no keypoints", report.warnings[0].message)


class TestPhantomClip(LabelingValidateTestCase):
    def test_phantom_clip_with_zero_reps_has_no_errors(self):
        labels = _phantom_labels()
        _write_clip(self.golden_dir, labels)
        _write_manifest(self.golden_dir, [_manifest_row(labels)])

        report = validate_golden_set(self.golden_dir)

        self.assertTrue(report.ok, report.format())

    def test_phantom_clip_with_nonzero_actual_reps_errors(self):
        labels = _phantom_labels()
        labels["ground_truth"] = {"actual_reps": 3, "reps": [{"idx": 1, "faults": []}]}
        _write_clip(self.golden_dir, labels)
        _write_manifest(self.golden_dir, [_manifest_row(labels)])

        report = validate_golden_set(self.golden_dir)

        self.assertFalse(report.ok)
        self.assertTrue(any("actual_reps == 0" in i.message for i in report.errors))

    def test_bystander_without_subject_track_id_errors(self):
        labels = _phantom_labels(clip_id="pushup_bystander_001")
        labels["exercise"] = "pushup"
        labels["clip_type"] = "bystander"
        labels["subject"]["num_people_in_frame"] = 2
        labels["subject"]["subject_track_id"] = None
        _write_clip(self.golden_dir, labels)
        _write_manifest(self.golden_dir, [_manifest_row(labels)])

        report = validate_golden_set(self.golden_dir)

        self.assertFalse(report.ok)
        self.assertTrue(any("subject_track_id" in i.message for i in report.errors))


class TestBadFaultId(LabelingValidateTestCase):
    def test_unknown_fault_id_is_reported_with_clip_and_rep(self):
        labels = _good_normal_labels(faults=["not_a_real_fault"])
        _write_clip(self.golden_dir, labels)
        _write_manifest(self.golden_dir, [_manifest_row(labels)])

        report = validate_golden_set(self.golden_dir)

        self.assertFalse(report.ok)
        bad = [i for i in report.errors if "not_a_real_fault" in i.message]
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0].clip_id, "squat_clean_side_001")
        self.assertEqual(bad[0].rep_idx, 1)

    def test_rep_count_mismatch_is_reported(self):
        labels = _good_normal_labels()
        labels["ground_truth"]["actual_reps"] = 3  # only 1 rep row present
        _write_clip(self.golden_dir, labels)
        _write_manifest(self.golden_dir, [_manifest_row(labels)])

        report = validate_golden_set(self.golden_dir)

        self.assertFalse(report.ok)
        self.assertTrue(any("rep row" in i.message for i in report.errors))


class TestClipMissingSeverity(LabelingValidateTestCase):
    """A fault used in labels.json whose exercise-library entry has no severity at all --
    exercise_lib.load_fault_severities() must raise, and the validator must surface that as a
    top-level issue rather than crashing. Uses a temp exercise-library override, never the real
    exercises/*.json (which always declare a severity today)."""

    def setUp(self):
        super().setUp()
        self.lib_dir = Path(tempfile.mkdtemp())
        (self.lib_dir / "fake_exercise.json").write_text(json.dumps({
            "exercise_id": "fake_exercise",
            "reference_keypoints": {
                "common_errors": [{"error_id": "some_fault"}]  # no "severity" key
            },
        }), encoding="utf-8")

    def tearDown(self):
        super().tearDown()
        shutil.rmtree(self.lib_dir, ignore_errors=True)

    def test_missing_severity_surfaces_as_a_top_level_error(self):
        labels = _good_normal_labels()
        labels["exercise"] = "fake_exercise"
        labels["ground_truth"]["reps"][0]["faults"] = ["some_fault"]
        _write_clip(self.golden_dir, labels)
        _write_manifest(self.golden_dir, [_manifest_row(labels)])

        report = validate_golden_set(self.golden_dir, exercise_lib_dir=self.lib_dir)

        self.assertFalse(report.ok)
        self.assertTrue(any(i.clip_id == "EXERCISE_LIBRARY" for i in report.errors))


class TestManifestAgreement(LabelingValidateTestCase):
    def test_manifest_labels_field_disagreement_is_reported(self):
        labels = _good_normal_labels()
        row = _manifest_row(labels)
        row["lighting"] = "dim_room"  # deliberately drifted from labels.json's "daylight"
        _write_clip(self.golden_dir, labels)
        _write_manifest(self.golden_dir, [row])

        report = validate_golden_set(self.golden_dir)

        self.assertFalse(report.ok)
        self.assertTrue(any("lighting" in i.message for i in report.errors))

    def test_labels_file_without_manifest_entry_is_reported(self):
        labels = _good_normal_labels()
        _write_clip(self.golden_dir, labels)
        _write_manifest(self.golden_dir, [])

        report = validate_golden_set(self.golden_dir)

        self.assertFalse(report.ok)
        self.assertTrue(any("not listed in MANIFEST" in i.message for i in report.errors))

    def test_manifest_entry_without_labels_file_is_reported(self):
        labels = _good_normal_labels()
        _write_manifest(self.golden_dir, [_manifest_row(labels)])

        report = validate_golden_set(self.golden_dir)

        self.assertFalse(report.ok)
        self.assertTrue(any("no <clip_id>.labels.json" in i.message for i in report.errors))


class TestKeypointsSchema(LabelingValidateTestCase):
    def test_malformed_keypoint_frame_is_reported(self):
        labels = _good_normal_labels()
        _write_json(self.golden_dir / f"{labels['clip_id']}.labels.json", labels)
        _write_manifest(self.golden_dir, [_manifest_row(labels)])
        kp_dir = self.golden_dir / "poses" / "movenet_17"
        kp_dir.mkdir(parents=True)
        bad_frame = {"t_ms": 0, "pose_model": "movenet_17",
                     "people": [{"track_id": 0, "kp": [[0.5, 0.5]]}]}  # kp point too short
        (kp_dir / f"{labels['clip_id']}.keypoints.jsonl").write_text(
            json.dumps(bad_frame) + "\n", encoding="utf-8"
        )

        report = validate_golden_set(self.golden_dir)

        self.assertFalse(report.ok)
        self.assertTrue(any("[x, y, z, vis]" in i.message for i in report.errors))


if __name__ == "__main__":
    unittest.main()
