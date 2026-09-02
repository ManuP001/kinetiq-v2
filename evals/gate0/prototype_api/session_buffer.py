#!/usr/bin/env python3
"""
evals/gate0/prototype_api/session_buffer.py

In-memory, per-process, per-session keypoint-frame buffer for the live detector API. NOT a
production session store: single process, no persistence, no eviction beyond the
PROTOTYPE_SESSION_MAX_FRAMES safeguard and an explicit reset -- a process restart loses every
session, which is fine for step 1 of the live-vision-prototype build.

The API recomputes run_detector over the WHOLE accumulated buffer on every call (main.py) --
simple and correct for a prototype-length set, but O(frames-so-far) per request. The max-frames
safeguard here bounds that from growing without limit if a client keeps a session open
indefinitely; it is not a tuned product limit (config.py's PROTOTYPE_SESSION_MAX_FRAMES).
"""
from __future__ import annotations

import threading
from typing import Any, Dict, List

import gate_config


class SessionBufferFullError(RuntimeError):
    """Raised by append() instead of silently dropping frames -- a dropped frame would make the
    buffer's contents diverge from what the client believes it sent, which is exactly the kind of
    detector/consumer drift this whole prototype exists to avoid. The caller (main.py) turns this
    into a structured 4xx; nothing is appended when this raises."""


class SessionBufferStore:
    """Keyed by session_id. One process-wide lock, not per-session -- simple and correct at
    prototype request volume; a real product session store would need per-session locking (or a
    proper datastore) under real concurrency, out of scope here."""

    def __init__(self, max_frames: int = gate_config.PROTOTYPE_SESSION_MAX_FRAMES) -> None:
        self._max_frames = max_frames
        self._lock = threading.Lock()
        self._sessions: Dict[str, List[Dict[str, Any]]] = {}

    def get(self, session_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._sessions.get(session_id, []))

    def reset(self, session_id: str) -> None:
        with self._lock:
            self._sessions[session_id] = []

    def append(self, session_id: str, frames: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Appends frames (already schema-validated by the caller) to session_id's buffer and
        returns the new full buffer. Raises SessionBufferFullError, appending nothing, if this
        would exceed the max-frames safeguard."""
        with self._lock:
            existing = self._sessions.setdefault(session_id, [])
            if len(existing) + len(frames) > self._max_frames:
                raise SessionBufferFullError(
                    f"session {session_id!r}: {len(existing)} buffered + {len(frames)} new "
                    f"frame(s) would exceed PROTOTYPE_SESSION_MAX_FRAMES ({self._max_frames}); "
                    f"reset the session or send fewer frames per call"
                )
            existing.extend(frames)
            return list(existing)
