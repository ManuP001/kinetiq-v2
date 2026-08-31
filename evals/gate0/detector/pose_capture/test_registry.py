#!/usr/bin/env python3
"""Unit tests for detector/pose_capture/registry.py."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import gate_config  # noqa: E402
from detector.pose_capture.base import PoseCaptureAdapter  # noqa: E402
from detector.pose_capture.blazepose_adapter import BlazePoseAdapter  # noqa: E402
from detector.pose_capture.movenet_adapter import MoveNetAdapter  # noqa: E402
from detector.pose_capture.registry import available_pose_models, get_adapter  # noqa: E402
from detector.pose_capture.rtmpose_adapter import RTMPoseAdapter  # noqa: E402


class TestAvailablePoseModels(unittest.TestCase):
    def test_matches_every_registered_candidate(self):
        registered = {c["name"] for c in gate_config.POSE_MODEL_CANDIDATES}
        self.assertEqual(set(available_pose_models()), registered)


class TestGetAdapter(unittest.TestCase):
    def test_returns_the_right_adapter_type(self):
        self.assertIsInstance(get_adapter("blazepose_33"), BlazePoseAdapter)
        self.assertIsInstance(get_adapter("movenet_17"), MoveNetAdapter)
        self.assertIsInstance(get_adapter("rtmpose_halpe26"), RTMPoseAdapter)

    def test_every_adapter_names_itself_correctly(self):
        for pose_model in available_pose_models():
            adapter = get_adapter(pose_model)
            self.assertIsInstance(adapter, PoseCaptureAdapter)
            self.assertEqual(adapter.pose_model_name, pose_model)

    def test_unknown_model_raises_key_error(self):
        with self.assertRaises(KeyError):
            get_adapter("some_future_model")

    def test_is_available_never_raises(self):
        # the whole point of is_available() is that it's safe to call with none of the ML
        # runtimes installed -- confirm none of the 3 real adapters raise here.
        for pose_model in available_pose_models():
            adapter = get_adapter(pose_model)
            try:
                adapter.is_available()
            except Exception as exc:  # noqa: BLE001
                self.fail(f"{pose_model}.is_available() raised {exc!r}")

    def test_install_hint_is_nonempty_for_every_adapter(self):
        for pose_model in available_pose_models():
            hint = get_adapter(pose_model).install_hint()
            self.assertIsInstance(hint, str)
            self.assertGreater(len(hint), 0)


if __name__ == "__main__":
    unittest.main()
