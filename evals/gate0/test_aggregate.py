#!/usr/bin/env python3
"""Unit tests for aggregate.py: the Stage-2 pose-model bake-off (--compare-pose-models) and the
Stage-3 golden-set report's insufficient-evidence summary."""
from __future__ import annotations

import io
import json
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from aggregate import (  # noqa: E402
    _fmt_pct,
    _pool_form_pr,
    print_pose_model_comparison,
    print_stage0_report,
    run_compare_pose_models,
)
from gate_config import POSE_MODEL_CANDIDATES  # noqa: E402
from golden_loader import load_golden  # noqa: E402
from scorers.form_pr import PR  # noqa: E402

FIXTURE_DIR = Path(__file__).resolve().parent / "golden"


class TestFmtPct(unittest.TestCase):
    def test_none_is_na(self):
        self.assertEqual(_fmt_pct(None), "n/a")

    def test_formats_a_fraction_as_percent(self):
        self.assertEqual(_fmt_pct(0.5), "50.0%")


class TestPoolFormPr(unittest.TestCase):
    def test_sums_tp_fp_fn_across_flags_and_exercises(self):
        per_exercise = {
            "squat": {"knee_cave_left": PR(tp=2, fp=1, fn=0), "shallow_depth": PR(tp=3, fp=0, fn=1)},
            "pushup": {"hip_sag": PR(tp=1, fp=0, fn=0)},
        }
        pooled = _pool_form_pr(per_exercise)
        self.assertEqual(pooled.tp, 6)
        self.assertEqual(pooled.fp, 1)
        self.assertEqual(pooled.fn, 1)

    def test_empty_input_is_a_vacuous_pr(self):
        pooled = _pool_form_pr({})
        self.assertIsNone(pooled.precision)
        self.assertIsNone(pooled.recall)


class TestPrintPoseModelComparisonOnFixture(unittest.TestCase):
    def test_runs_end_to_end_and_returns_true(self):
        out = io.StringIO()
        with redirect_stdout(out):
            result = print_pose_model_comparison(FIXTURE_DIR)
        self.assertTrue(result)
        text = out.getvalue()
        for candidate in POSE_MODEL_CANDIDATES:
            self.assertIn(candidate["name"], text)

    def test_rep_accuracy_is_identical_across_all_candidate_models(self):
        out = io.StringIO()
        with redirect_stdout(out):
            print_pose_model_comparison(FIXTURE_DIR)
        lines = [l for l in out.getvalue().splitlines() if "squat_bakeoff" not in l]
        rep_acc_lines = [l for l in lines if any(c["name"] in l for c in POSE_MODEL_CANDIDATES)]
        self.assertEqual(len(rep_acc_lines), len(POSE_MODEL_CANDIDATES))
        for line in rep_acc_lines:
            self.assertIn("100.0%", line)

    def test_synthetic_fixture_shows_na_latency_and_size(self):
        out = io.StringIO()
        with redirect_stdout(out):
            print_pose_model_comparison(FIXTURE_DIR)
        self.assertIn("n/a (synthetic)", out.getvalue())

    def test_never_prints_a_winner_declaration(self):
        out = io.StringIO()
        with redirect_stdout(out):
            print_pose_model_comparison(FIXTURE_DIR)
        text = out.getvalue().lower()
        for banned in ("winner:", "best model", "recommended model"):
            self.assertNotIn(banned, text)


class TestRunComparePoseModels(unittest.TestCase):
    def test_returns_zero_on_the_real_fixture(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = run_compare_pose_models(FIXTURE_DIR)
        self.assertEqual(code, 0)

    def test_nonexistent_dir_returns_nonzero(self):
        code = run_compare_pose_models(Path("this_dir_does_not_exist_hopefully"))
        self.assertNotEqual(code, 0)


class TestNoClipsIsNotAHardFailure(unittest.TestCase):
    """A candidate model with zero golden/poses/<model>/ clips (the normal state before
    GOLDEN_SET_PROTOCOL.md §8's data exists) must print informationally and still return True --
    it's the expected state right now, not an error."""

    def test_empty_golden_dir_with_only_a_manifest_returns_true(self):
        tmpdir = Path(tempfile.mkdtemp())
        try:
            (tmpdir / "MANIFEST.json").write_text(
                json.dumps({"schema_version": 1, "clips": []}), encoding="utf-8"
            )
            out = io.StringIO()
            with redirect_stdout(out):
                result = print_pose_model_comparison(tmpdir)
            self.assertTrue(result)
            self.assertIn("no golden/poses/", out.getvalue())
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


class TestHardFailure(unittest.TestCase):
    def test_broken_golden_set_returns_false(self):
        tmpdir = Path(tempfile.mkdtemp())
        try:
            pose_model = POSE_MODEL_CANDIDATES[0]["name"]
            clip_id = "squat_bakeoff_side_001"
            for suffix in (".labels.json",):
                shutil.copy(
                    FIXTURE_DIR / f"{clip_id}{suffix}", tmpdir / f"{clip_id}{suffix}"
                )
            labels = json.loads((tmpdir / f"{clip_id}.labels.json").read_text(encoding="utf-8"))
            labels["ground_truth"]["reps"][0]["faults"] = ["not_a_real_fault"]
            (tmpdir / f"{clip_id}.labels.json").write_text(json.dumps(labels), encoding="utf-8")

            poses_dir = tmpdir / "poses" / pose_model
            poses_dir.mkdir(parents=True)
            shutil.copy(
                FIXTURE_DIR / "poses" / pose_model / f"{clip_id}.keypoints.jsonl",
                poses_dir / f"{clip_id}.keypoints.jsonl",
            )

            out = io.StringIO()
            with redirect_stdout(out):
                result = print_pose_model_comparison(tmpdir)
            self.assertFalse(result)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


class TestInsufficientEvidenceSurfaced(unittest.TestCase):
    """Stage 3 (SPRINT.md G2): an insufficient-evidence flag must be surfaced in the printed
    report, not silently absent the way it would be if it just weren't in det.flags."""

    def test_report_shows_the_insufficient_evidence_section_when_present(self):
        clips = load_golden(FIXTURE_DIR)
        out = io.StringIO()
        with redirect_stdout(out):
            print_stage0_report(clips, mode="full")
        text = out.getvalue()
        self.assertIn("Insufficient evidence", text)
        self.assertIn("hip_sag", text.split("Insufficient evidence")[1])


if __name__ == "__main__":
    unittest.main()
