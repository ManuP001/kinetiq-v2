#!/usr/bin/env python3
"""Unit tests for prototype_api/session_buffer.py."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from prototype_api.session_buffer import SessionBufferFullError, SessionBufferStore  # noqa: E402


class TestSessionBufferStore(unittest.TestCase):
    def setUp(self):
        self.store = SessionBufferStore(max_frames=5)

    def test_unknown_session_is_an_empty_buffer(self):
        self.assertEqual(self.store.get("nope"), [])

    def test_append_accumulates_across_calls(self):
        self.store.append("s1", [{"t_ms": 0}])
        self.store.append("s1", [{"t_ms": 100}])
        self.assertEqual(self.store.get("s1"), [{"t_ms": 0}, {"t_ms": 100}])

    def test_append_returns_the_full_buffer(self):
        self.store.append("s1", [{"t_ms": 0}])
        result = self.store.append("s1", [{"t_ms": 100}])
        self.assertEqual(result, [{"t_ms": 0}, {"t_ms": 100}])

    def test_reset_clears_the_session(self):
        self.store.append("s1", [{"t_ms": 0}])
        self.store.reset("s1")
        self.assertEqual(self.store.get("s1"), [])

    def test_reset_does_not_affect_other_sessions(self):
        self.store.append("s1", [{"t_ms": 0}])
        self.store.append("s2", [{"t_ms": 0}])
        self.store.reset("s1")
        self.assertEqual(self.store.get("s2"), [{"t_ms": 0}])

    def test_exceeding_max_frames_raises_and_appends_nothing(self):
        self.store.append("s1", [{"t_ms": i} for i in range(4)])
        with self.assertRaises(SessionBufferFullError):
            self.store.append("s1", [{"t_ms": 4}, {"t_ms": 5}])  # 4 + 2 > 5
        self.assertEqual(len(self.store.get("s1")), 4)  # unchanged, nothing partially appended

    def test_exactly_at_max_frames_is_allowed(self):
        result = self.store.append("s1", [{"t_ms": i} for i in range(5)])
        self.assertEqual(len(result), 5)

    def test_get_returns_a_copy_not_the_live_list(self):
        self.store.append("s1", [{"t_ms": 0}])
        snapshot = self.store.get("s1")
        snapshot.append({"t_ms": 999})
        self.assertEqual(len(self.store.get("s1")), 1)


if __name__ == "__main__":
    unittest.main()
