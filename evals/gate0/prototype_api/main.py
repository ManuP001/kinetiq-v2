#!/usr/bin/env python3
"""
evals/gate0/prototype_api/main.py

Thin FastAPI wrapper around the eval-validated run_detector (evals/gate0/detector/adapter.py) --
step 1 of the live-vision-prototype build (VISION_ARCHITECTURE.md). PRINCIPLE: one detector, two
consumers. This module imports and calls run_detector; it must never reimplement or fork a
detection rule -- every field in AssessResponse is either read straight off run_detector's
DetectedClip or (coaching_cue only) a plain text lookup into the exercise library, not new
detection logic. test_parity.py proves this: the API's result for a given frame sequence is
identical to calling run_detector directly on the same frames.

NOT the full /v2 product API: no auth, no DB, no persistence beyond an in-memory per-process
session buffer (session_buffer.py). NOT Stage-6 coaching (cues.py is explicitly interim).

Privacy invariant (CLAUDE.md §2): only keypoints ever cross the wire. Every frame in every
request is validated with the SAME validate_frame_schema golden_loader.py uses to freeze the
golden set -- a request carrying anything else (an image, a raw pixel/byte array) fails that
schema check (no "kp"/"t_ms"/"pose_model" shape) and is rejected with a structured 422 before it
ever reaches the detector.

Recompute-over-buffer latency: run_detector re-runs over the WHOLE accumulated session buffer on
every call (simplest-correct choice for a prototype-length set, per-call cost O(frames-so-far),
not O(new frames)). PROTOTYPE_SESSION_MAX_FRAMES (config.py) bounds how large that can grow.

CORS: the PWA client (kinetiq-demo3) is served from a different origin than this API (a static
host vs. wherever this process runs), so the browser enforces CORS on every request -- without it
enabled, every call fails before it reaches this code at all. PROTOTYPE_API_CORS_ORIGINS (env var,
comma-separated) controls allowed origins; defaults to "*" (allow any). This is a deliberate
prototype-only choice: there's no auth and no cookies, only keypoints cross this API, so an open
origin list doesn't expose anything sensitive -- do not carry "*" into the real /v2 product API.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import gate_config
from detector.adapter import run_detector
from detector.exercise_signals import scoped_exercises
from golden_loader import validate_frame_schema

from prototype_api.cues import CueResult, cue_for_rep
from prototype_api.schemas import AssessRequest, AssessResponse, RepResult
from prototype_api.session_buffer import SessionBufferFullError, SessionBufferStore

logger = logging.getLogger("prototype_api")

SUPPORTED_EXERCISES = scoped_exercises()  # single source: detector/exercise_signals.py

_CORS_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("PROTOTYPE_API_CORS_ORIGINS", "*").split(",")
    if origin.strip()
]

app = FastAPI(
    title="Kinetiq v3 -- prototype detector API",
    description=(
        "Step 1 of the live-vision-prototype build: a thin wrapper around the eval-validated "
        "run_detector. See evals/gate0/prototype_api/README.md for the full contract."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_methods=["POST"],
    allow_headers=["Content-Type"],
)

_buffers = SessionBufferStore()


class DetectorRequestError(ValueError):
    """A structured 4xx: bad exercise_id, a frame that fails validate_frame_schema, or a
    session's buffer exceeding PROTOTYPE_SESSION_MAX_FRAMES."""

    def __init__(self, status_code: int, error: str, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.error = error
        self.detail = detail


@app.exception_handler(DetectorRequestError)
async def _handle_detector_request_error(
    request: Request, exc: DetectorRequestError
) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"error": exc.error, "detail": exc.detail})


def _validate_frames(frames: List[Dict[str, Any]]) -> None:
    """Every frame must pass the SAME schema check the golden set is frozen against -- reused,
    not duplicated (import, don't reimplement). This is also what rejects a request that isn't
    keypoints (an image, raw pixels): anything without the kp/t_ms/pose_model shape fails here."""
    for i, frame in enumerate(frames):
        try:
            validate_frame_schema(frame, context=f"frame {i}")
        except ValueError as exc:
            raise DetectorRequestError(422, "invalid_frame", str(exc)) from exc


def _cue_warning(current_flags: List[str], cue: CueResult) -> str | None:
    if not cue.over_word_cap:
        return None
    flag_id = current_flags[0] if current_flags else "good_rep"
    return (
        f"cue for {flag_id!r} is {cue.word_count} words, over LIVE_CUE_MAX_WORDS "
        f"({gate_config.LIVE_CUE_MAX_WORDS}) -- exercise-library copy fix needed, not truncated"
    )


@app.post("/prototype/assess", response_model=AssessResponse)
def assess(body: AssessRequest) -> AssessResponse:
    if body.exercise_id not in SUPPORTED_EXERCISES:
        raise DetectorRequestError(
            422, "unknown_exercise",
            f"exercise_id must be one of {SUPPORTED_EXERCISES}, got {body.exercise_id!r}",
        )

    _validate_frames(body.frames)

    if body.reset:
        _buffers.reset(body.session_id)

    try:
        buffer = _buffers.append(body.session_id, body.frames)
    except SessionBufferFullError as exc:
        raise DetectorRequestError(413, "session_buffer_full", str(exc)) from exc

    detected = run_detector(buffer, body.exercise_id)

    last_rep = detected.reps[-1] if detected.reps else None
    current_flags = last_rep.flags if last_rep else []
    insufficient_evidence = last_rep.insufficient_evidence if last_rep else []

    if last_rep is not None:
        exercise_json = gate_config.load_exercise_library()[body.exercise_id]
        cue = cue_for_rep(exercise_json, current_flags)
    else:
        # No completed rep yet -- nothing to comment on. Showing "good_rep" text before the user
        # has done anything would be premature, not positive-first.
        cue = CueResult(text=None, over_word_cap=False, word_count=0)

    if cue.over_word_cap:
        logger.warning(
            "cue for exercise=%s flags=%s exceeds LIVE_CUE_MAX_WORDS (%d): %d words: %r",
            body.exercise_id, current_flags, gate_config.LIVE_CUE_MAX_WORDS, cue.word_count, cue.text,
        )

    subject_lock_ok = bool(
        detected.subject_track_sequence and detected.subject_track_sequence[-1] is not None
    )

    return AssessResponse(
        rep_count=detected.detected_reps,
        rep_in_progress=detected.rep_in_progress,
        phase=detected.phase,
        current_flags=current_flags,
        insufficient_evidence=insufficient_evidence,
        subject_lock_ok=subject_lock_ok,
        coaching_cue=cue.text,
        cue_warning=_cue_warning(current_flags, cue),
        reps=[
            RepResult(idx=r.idx, flags=r.flags, insufficient_evidence=r.insufficient_evidence)
            for r in detected.reps
        ],
    )
