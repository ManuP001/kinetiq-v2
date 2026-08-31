#!/usr/bin/env python3
"""Unit tests for detector/pose_capture/cli.py."""
from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from detector.pose_capture.cli import main  # noqa: E402
from detector.pose_capture.registry import available_pose_models  # noqa: E402


class TestListCommand(unittest.TestCase):
    def test_lists_every_candidate_model(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = main(["--list"])
        self.assertEqual(code, 0)
        text = out.getvalue()
        for pose_model in available_pose_models():
            self.assertIn(pose_model, text)


class TestDryRunCommand(unittest.TestCase):
    def test_dry_run_succeeds_for_every_candidate_without_a_runtime(self):
        for pose_model in available_pose_models():
            out = io.StringIO()
            with redirect_stdout(out):
                code = main(["--model", pose_model, "--dry-run"])
            self.assertEqual(code, 0, pose_model)
            self.assertIn("Schema self-test: PASSED", out.getvalue())


class TestArgValidation(unittest.TestCase):
    def test_missing_model_errors(self):
        with self.assertRaises(SystemExit):
            main([])

    def test_missing_video_and_clip_id_for_a_real_capture_errors(self):
        with self.assertRaises(SystemExit):
            main(["--model", "movenet_17"])

    def test_unknown_model_choice_errors(self):
        with self.assertRaises(SystemExit):
            main(["--model", "not_a_real_model", "--dry-run"])


class TestCaptureCommandWithoutRuntime(unittest.TestCase):
    def test_capture_without_runtime_returns_nonzero_and_suggests_dry_run(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = main([
                "--model", "blazepose_33", "--video", "fake.mp4",
                "--clip-id", "test_001", "--golden", "/tmp/nonexistent_bakeoff_scratch",
            ])
        self.assertNotEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
