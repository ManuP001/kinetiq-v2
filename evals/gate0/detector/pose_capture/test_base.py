#!/usr/bin/env python3
"""Unit tests for detector/pose_capture/base.py, using a fake in-memory adapter so no real ML
runtime is needed to test the writer/schema-validation/latency-measurement plumbing."""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, Iterator

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from detector.pose_capture.base import (  # noqa: E402
    PoseCaptureAdapter,
    PoseRuntimeUnavailable,
    capture_clip,
    dry_run_self_test,
)


class FakeAdapter(PoseCaptureAdapter):
    pose_model_name = "fake_model"

    def __init__(self, available=True, frames=None, wrong_pose_model=False):
        self._available = available
        self._frames = frames if frames is not None else [
            {"t_ms": 0, "pose_model": self.pose_model_name,
             "people": [{"track_id": 0, "kp": [[0.5, 0.5, None, 0.9]], "box": [0, 0, 1, 1]}]},
            {"t_ms": 33, "pose_model": self.pose_model_name,
             "people": [{"track_id": 0, "kp": [[0.51, 0.5, None, 0.9]], "box": [0, 0, 1, 1]}]},
        ]
        self._wrong_pose_model = wrong_pose_model

    def is_available(self) -> bool:
        return self._available

    def install_hint(self) -> str:
        return "pip install fake-runtime"

    def infer_frames(self, video_path: Path) -> Iterator[Dict[str, Any]]:
        if not self._available:
            raise PoseRuntimeUnavailable("fake runtime unavailable")
        for frame in self._frames:
            if self._wrong_pose_model:
                frame = dict(frame, pose_model="a_different_model")
            yield frame


class TestCaptureClip(unittest.TestCase):
    def setUp(self):
        self.golden_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.golden_dir, ignore_errors=True)

    def test_writes_keypoints_jsonl_matching_the_adapter_output(self):
        adapter = FakeAdapter()
        result = capture_clip(adapter, Path("fake.mp4"), self.golden_dir, "clip_001")

        self.assertEqual(result.frames_written, 2)
        expected_path = self.golden_dir / "poses" / "fake_model" / "clip_001.keypoints.jsonl"
        self.assertEqual(result.keypoints_path, expected_path)
        lines = expected_path.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(json.loads(lines[0])["t_ms"], 0)

    def test_writes_capture_meta_with_latency_and_env(self):
        adapter = FakeAdapter()
        result = capture_clip(adapter, Path("fake.mp4"), self.golden_dir, "clip_001")

        meta = json.loads(result.meta_path.read_text(encoding="utf-8"))
        self.assertEqual(meta["pose_model"], "fake_model")
        self.assertEqual(meta["frames_captured"], 2)
        self.assertIsNotNone(meta["avg_latency_ms_per_frame"])
        self.assertGreaterEqual(meta["avg_latency_ms_per_frame"], 0)
        self.assertIn("capture-machine, not on-device", meta["capture_env"])

    def test_unavailable_adapter_raises_and_writes_nothing(self):
        adapter = FakeAdapter(available=False)
        with self.assertRaises(PoseRuntimeUnavailable):
            capture_clip(adapter, Path("fake.mp4"), self.golden_dir, "clip_001")
        self.assertFalse((self.golden_dir / "poses").exists())

    def test_zero_frames_gives_none_latency_not_a_crash(self):
        adapter = FakeAdapter(frames=[])
        result = capture_clip(adapter, Path("fake.mp4"), self.golden_dir, "clip_001")
        self.assertEqual(result.frames_written, 0)
        self.assertIsNone(result.avg_latency_ms_per_frame)

    def test_malformed_frame_raises_before_corrupting_output(self):
        bad_frames = [{"t_ms": 0, "people": []}]  # missing pose_model
        adapter = FakeAdapter(frames=bad_frames)
        with self.assertRaises(ValueError):
            capture_clip(adapter, Path("fake.mp4"), self.golden_dir, "clip_001")

    def test_pose_model_mismatch_raises(self):
        adapter = FakeAdapter(wrong_pose_model=True)
        with self.assertRaises(ValueError):
            capture_clip(adapter, Path("fake.mp4"), self.golden_dir, "clip_001")

    def test_never_writes_or_references_the_video_path(self):
        adapter = FakeAdapter()
        capture_clip(adapter, Path("fake.mp4"), self.golden_dir, "clip_001")
        written_files = list(self.golden_dir.rglob("*"))
        for f in written_files:
            self.assertNotIn("fake.mp4", f.name)


class TestDryRunSelfTest(unittest.TestCase):
    def test_reports_unavailable_and_passes_schema_check(self):
        adapter = FakeAdapter(available=False)
        message = dry_run_self_test(adapter)
        self.assertIn("NOT available", message)
        self.assertIn("PASSED", message)
        self.assertIn("pip install fake-runtime", message)

    def test_reports_available_when_true(self):
        adapter = FakeAdapter(available=True)
        message = dry_run_self_test(adapter)
        self.assertIn("is available", message)

    def test_never_touches_a_real_directory(self):
        # dry_run_self_test takes no golden_dir at all -- confirm it doesn't create one as a
        # side effect regardless of cwd.
        before = set(Path(".").iterdir())
        dry_run_self_test(FakeAdapter())
        after = set(Path(".").iterdir())
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
