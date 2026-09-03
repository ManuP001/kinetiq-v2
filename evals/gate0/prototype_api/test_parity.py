#!/usr/bin/env python3
"""
evals/gate0/prototype_api/test_parity.py

The core proof of "one detector, two consumers" (main.py's module docstring): for a given
keypoint sequence, the API's result MUST be identical to calling run_detector directly on the
same frames. If this test ever fails, the API has drifted from the detector -- by construction a
bug (the API adds detection behavior of its own), never an acceptable feature.

Runs over two real golden fixtures (pushup, with 2 real reps + a bystander; squat, with seeded
knee_cave faults) so the parity property is checked against genuinely different exercises/flags,
not just one happy path.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from detector.adapter import run_detector  # noqa: E402
from prototype_api.main import _buffers, app  # noqa: E402

GOLDEN_DIR = Path(__file__).resolve().parents[1] / "golden"
PUSHUP_FIXTURE = GOLDEN_DIR / "pushup_bystander_001.keypoints.jsonl"
SQUAT_FIXTURE = GOLDEN_DIR / "squat_badform_001.keypoints.jsonl"


def _load_frames(path: Path):
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def _expected_fields(direct):
    last_rep = direct.reps[-1] if direct.reps else None
    return {
        "rep_count": direct.detected_reps,
        "rep_in_progress": direct.rep_in_progress,
        "phase": direct.phase,
        "current_flags": last_rep.flags if last_rep else [],
        "insufficient_evidence": last_rep.insufficient_evidence if last_rep else [],
        "subject_lock_ok": bool(
            direct.subject_track_sequence and direct.subject_track_sequence[-1] is not None
        ),
        "reps": [
            {"idx": r.idx, "flags": r.flags, "insufficient_evidence": r.insufficient_evidence}
            for r in direct.reps
        ],
    }


class TestApiMatchesRunDetectorDirectly(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def _assert_parity(self, session_id: str, exercise_id: str, frames, *, reset: bool = True):
        direct = run_detector(frames, exercise_id)
        resp = self.client.post("/prototype/assess", json={
            "session_id": session_id, "exercise_id": exercise_id, "frames": frames, "reset": reset,
        })
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        expected = _expected_fields(direct)
        for field, value in expected.items():
            self.assertEqual(body[field], value, f"{field}: api={body[field]!r} direct={value!r}")
        return direct, body

    def test_full_pushup_buffer_matches_run_detector(self):
        frames = _load_frames(PUSHUP_FIXTURE)
        self._assert_parity("parity-pushup-full", "pushup", frames)

    def test_full_squat_buffer_matches_run_detector(self):
        frames = _load_frames(SQUAT_FIXTURE)
        self._assert_parity("parity-squat-full", "squat", frames)

    def test_partial_mid_rep_buffer_matches_run_detector_on_the_same_prefix(self):
        frames = _load_frames(PUSHUP_FIXTURE)[:12]  # mid-descent, no closed rep yet
        direct, body = self._assert_parity("parity-pushup-partial", "pushup", frames)
        self.assertEqual(direct.detected_reps, 0)
        self.assertTrue(direct.rep_in_progress)  # confirms this case actually exercises phase

    def test_incremental_batches_match_a_single_full_call(self):
        # the same frames, split across three separate requests -- proves recompute-over-buffer
        # gives the identical answer regardless of how the client chunks its batches, matching
        # run_detector called once over the whole accumulated sequence.
        frames = _load_frames(PUSHUP_FIXTURE)
        third = len(frames) // 3
        batches = [frames[:third], frames[third:2 * third], frames[2 * third:]]

        session_id = "parity-pushup-incremental"
        resp = None
        for i, batch in enumerate(batches):
            resp = self.client.post("/prototype/assess", json={
                "session_id": session_id, "exercise_id": "pushup",
                "frames": batch, "reset": (i == 0),
            })
            self.assertEqual(resp.status_code, 200)

        direct = run_detector(frames, "pushup")
        body = resp.json()
        expected = _expected_fields(direct)
        for field, value in expected.items():
            self.assertEqual(body[field], value)

    def test_reset_makes_the_api_match_run_detector_on_only_the_post_reset_frames(self):
        frames = _load_frames(PUSHUP_FIXTURE)
        session_id = "parity-reset"
        self.client.post("/prototype/assess", json={
            "session_id": session_id, "exercise_id": "pushup", "frames": frames, "reset": True,
        })
        # reset + a short prefix -- the pre-reset buffer must not leak into this result.
        prefix = frames[:12]
        self._assert_parity(session_id, "pushup", prefix, reset=True)

    def tearDown(self):
        # keep sessions from leaking state into other test modules sharing the same process-wide
        # _buffers instance (test_main.py, this module).
        for sid in (
            "parity-pushup-full", "parity-squat-full", "parity-pushup-partial",
            "parity-pushup-incremental", "parity-reset",
        ):
            _buffers.reset(sid)


if __name__ == "__main__":
    unittest.main()
