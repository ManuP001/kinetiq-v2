#!/usr/bin/env python3
"""Unit tests for prototype_api/main.py's endpoint behavior: validation, reset, buffer-full,
privacy rejection. test_parity.py covers the detection-result-matches-run_detector property
separately -- these tests are about the HTTP contract around it."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from prototype_api.main import _buffers, app  # noqa: E402
from prototype_api.session_buffer import SessionBufferStore  # noqa: E402

FIXTURE = Path(__file__).resolve().parents[1] / "golden" / "pushup_bystander_001.keypoints.jsonl"


def _load_frames():
    with FIXTURE.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f]


class PrototypeApiTestCase(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.frames = _load_frames()


class TestAssessValidation(PrototypeApiTestCase):
    def test_unknown_exercise_id_is_rejected(self):
        resp = self.client.post("/prototype/assess", json={
            "session_id": "s", "exercise_id": "deadlift", "frames": [], "reset": True,
        })
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["error"], "unknown_exercise")

    def test_frame_missing_required_field_is_rejected(self):
        resp = self.client.post("/prototype/assess", json={
            "session_id": "s", "exercise_id": "squat",
            "frames": [{"t_ms": 0, "people": []}],  # missing pose_model
            "reset": True,
        })
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["error"], "invalid_frame")

    def test_malformed_keypoint_is_rejected(self):
        resp = self.client.post("/prototype/assess", json={
            "session_id": "s", "exercise_id": "squat",
            "frames": [{
                "t_ms": 0, "pose_model": "movenet_17",
                "people": [{"track_id": 0, "kp": [[0.5, 0.5]]}],  # only 2 of 4 values
            }],
            "reset": True,
        })
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["error"], "invalid_frame")

    def test_a_bad_frame_anywhere_in_the_batch_rejects_the_whole_request(self):
        # privacy/integrity: no partial application of an invalid batch.
        good = self.frames[0]
        resp = self.client.post("/prototype/assess", json={
            "session_id": "reject-whole-batch", "exercise_id": "pushup",
            "frames": [good, {"t_ms": 1}],  # second frame missing pose_model/people
            "reset": True,
        })
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(_buffers.get("reject-whole-batch"), [])

    def test_missing_session_id_is_a_422(self):
        resp = self.client.post("/prototype/assess", json={
            "exercise_id": "squat", "frames": [], "reset": True,
        })
        self.assertEqual(resp.status_code, 422)


class TestSessionLifecycle(PrototypeApiTestCase):
    def test_reset_clears_a_prior_buffer(self):
        session_id = "lifecycle-1"
        self.client.post("/prototype/assess", json={
            "session_id": session_id, "exercise_id": "pushup",
            "frames": self.frames, "reset": True,
        })
        self.assertEqual(len(_buffers.get(session_id)), len(self.frames))

        resp = self.client.post("/prototype/assess", json={
            "session_id": session_id, "exercise_id": "pushup", "frames": [], "reset": True,
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(_buffers.get(session_id), [])
        self.assertEqual(resp.json()["rep_count"], 0)

    def test_repeated_calls_without_reset_accumulate(self):
        session_id = "lifecycle-2"
        third = len(self.frames) // 3
        r1 = self.client.post("/prototype/assess", json={
            "session_id": session_id, "exercise_id": "pushup",
            "frames": self.frames[:third], "reset": True,
        })
        r2 = self.client.post("/prototype/assess", json={
            "session_id": session_id, "exercise_id": "pushup",
            "frames": self.frames[third:], "reset": False,
        })
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(len(_buffers.get(session_id)), len(self.frames))
        self.assertEqual(r2.json()["rep_count"], 2)

    def test_sessions_are_independent(self):
        self.client.post("/prototype/assess", json={
            "session_id": "indep-a", "exercise_id": "pushup",
            "frames": self.frames, "reset": True,
        })
        resp_b = self.client.post("/prototype/assess", json={
            "session_id": "indep-b", "exercise_id": "pushup", "frames": [], "reset": True,
        })
        self.assertEqual(resp_b.json()["rep_count"], 0)
        self.assertEqual(len(_buffers.get("indep-a")), len(self.frames))


class TestSessionBufferSafeguard(unittest.TestCase):
    def test_buffer_full_returns_413_and_appends_nothing(self):
        from prototype_api import main as main_module

        original_store = main_module._buffers
        main_module._buffers = SessionBufferStore(max_frames=3)
        try:
            client = TestClient(main_module.app)
            frames = [
                {"t_ms": i, "pose_model": "movenet_17",
                 "people": [{"track_id": 0, "kp": [[0.5, 0.5, None, 0.9]], "box": [0.4, 0.4, 0.2, 0.2]}]}
                for i in range(5)
            ]
            resp = client.post("/prototype/assess", json={
                "session_id": "overflow", "exercise_id": "squat", "frames": frames, "reset": True,
            })
            self.assertEqual(resp.status_code, 413)
            self.assertEqual(resp.json()["error"], "session_buffer_full")
            self.assertEqual(main_module._buffers.get("overflow"), [])
        finally:
            main_module._buffers = original_store


class TestCoachingCue(PrototypeApiTestCase):
    def test_no_completed_rep_yet_has_no_cue(self):
        resp = self.client.post("/prototype/assess", json={
            "session_id": "no-rep-yet", "exercise_id": "pushup",
            "frames": self.frames[:5], "reset": True,  # well short of a completed rep
        })
        body = resp.json()
        self.assertEqual(body["rep_count"], 0)
        self.assertIsNone(body["coaching_cue"])

    def test_clean_completed_rep_gets_the_good_rep_cue(self):
        resp = self.client.post("/prototype/assess", json={
            "session_id": "clean-rep", "exercise_id": "pushup",
            "frames": self.frames, "reset": True,
        })
        body = resp.json()
        self.assertEqual(body["rep_count"], 2)
        self.assertEqual(body["coaching_cue"], "Full range — great push-up")
        self.assertIsNone(body["cue_warning"])

    def test_over_cap_cue_is_flagged_not_hidden(self):
        import gate_config
        from prototype_api.cues import cue_for_rep

        squat = gate_config.load_exercise_library()["squat"]
        result = cue_for_rep(squat, ["shallow_depth"])
        self.assertTrue(result.over_word_cap)
        self.assertIsNotNone(result.text)  # still returned, never hidden


if __name__ == "__main__":
    unittest.main()
