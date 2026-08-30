#!/usr/bin/env python3
"""
evals/gate0/detector/subject_lock.py

Stage 1 of VISION_ARCHITECTURE.md: pick ONE subject at session start, track that identity across
frames, and never silently retarget to someone else. Deliberately independent of pose
plausibility (detector/plausibility.py) -- a false-positive "person" box (e.g. a bench) can be
locked here exactly like a real one; it's the separate rep-validity gate that then rejects every
frame of it. Ch 30: each specialist does one job.

Track-identity strategy (documented, not left implicit -- this is one of the two things the task
asked to be surfaced rather than silently hardcoded):

  - Prefer the stream's own track_id when it's stable (the locked person's track_id reappears
    frame to frame). Real trackers occasionally drop or reassign ids, so this alone isn't enough.
  - When the locked track_id is absent from a frame, re-associate by nearest bbox centroid to the
    locked subject's LAST KNOWN position, accepting a candidate only within
    SUBJECT_REID_MAX_CENTROID_DIST (config). This is deliberately tight: the whole point of
    subject-lock is that a closer/larger/more-central bystander must never steal the lock just by
    being more prominent than wherever the real subject last was. If two candidates are
    equally-close ties, the lower track_id wins (deterministic).
  - After SUBJECT_LOST_FRAMES_THRESHOLD (config) consecutive frames with no acceptable candidate
    (by either method), the subject is declared LOST and the session PAUSES: no further frames
    count towards rep detection until the same identity (by the position-based re-id check above,
    anchored to the last known position before the loss) is found again. A different person
    appearing during a pause is never adopted -- pausing, not silent retargeting, is the whole
    point (VISION_ARCHITECTURE.md Stage 1).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

import gate_config
from detector.geometry import bbox_area, bbox_centroid, distance


@dataclass
class FrameLock:
    """Per-frame subject-lock result."""
    person: Optional[Dict[str, Any]]  # the locked person's raw record this frame, or None
    track_id: Optional[int]
    paused: bool  # True if the subject is currently considered lost


def _select_initial_subject(
    people: Sequence[Dict[str, Any]], rule: str
) -> Optional[Dict[str, Any]]:
    if not people:
        return None
    if rule == "most_central":
        # Closest bbox centroid to the frame centre (0.5, 0.5), assuming normalized coordinates
        # (EVAL_HARNESS_STAGE0_SPEC.md keypoints are frame-normalized).
        return min(people, key=lambda p: distance(bbox_centroid(p["box"]), (0.5, 0.5)))
    if rule == "largest_bbox":
        return max(people, key=lambda p: bbox_area(p["box"]))
    raise ValueError(f"unknown SUBJECT_SELECTION_RULE {rule!r}")


def _find_by_track_id(people: Sequence[Dict[str, Any]], track_id: int) -> Optional[Dict[str, Any]]:
    for p in people:
        if p.get("track_id") == track_id:
            return p
    return None


def _find_by_reid(
    people: Sequence[Dict[str, Any]], last_centroid: tuple, max_dist: float
) -> Optional[Dict[str, Any]]:
    candidates = [
        (distance(bbox_centroid(p["box"]), last_centroid), p.get("track_id", 0), p)
        for p in people
    ]
    candidates = [c for c in candidates if c[0] <= max_dist]
    if not candidates:
        return None
    # Nearest first; lower track_id breaks an exact tie (deterministic).
    candidates.sort(key=lambda c: (c[0], c[1]))
    return candidates[0][2]


def track_subject(
    frames: Sequence[Dict[str, Any]],
    selection_rule: Optional[str] = None,
    lost_frames_threshold: Optional[int] = None,
    reid_max_centroid_dist: Optional[float] = None,
) -> List[FrameLock]:
    """Run subject-lock over a clip's frames (each frame a dict with a "people" list). Returns
    one FrameLock per input frame, in order."""
    rule = selection_rule if selection_rule is not None else gate_config.SUBJECT_SELECTION_RULE
    lost_threshold = (
        lost_frames_threshold
        if lost_frames_threshold is not None
        else gate_config.SUBJECT_LOST_FRAMES_THRESHOLD
    )
    max_dist = (
        reid_max_centroid_dist
        if reid_max_centroid_dist is not None
        else gate_config.SUBJECT_REID_MAX_CENTROID_DIST
    )

    results: List[FrameLock] = []
    locked_track_id: Optional[int] = None
    last_centroid: Optional[tuple] = None
    lost_streak = 0
    paused = False

    for frame in frames:
        people = frame.get("people", [])

        if locked_track_id is None:
            subject = _select_initial_subject(people, rule)
            if subject is None:
                results.append(FrameLock(person=None, track_id=None, paused=False))
                continue
            locked_track_id = subject.get("track_id")
            last_centroid = bbox_centroid(subject["box"])
            results.append(FrameLock(person=subject, track_id=locked_track_id, paused=False))
            lost_streak = 0
            continue

        found = _find_by_track_id(people, locked_track_id)
        if found is None and last_centroid is not None:
            found = _find_by_reid(people, last_centroid, max_dist)
            if found is not None:
                locked_track_id = found.get("track_id")  # re-id may hand back a new track_id

        if found is not None:
            last_centroid = bbox_centroid(found["box"])
            lost_streak = 0
            paused = False
            results.append(FrameLock(person=found, track_id=locked_track_id, paused=False))
        else:
            lost_streak += 1
            if lost_streak >= lost_threshold:
                paused = True
            results.append(FrameLock(person=None, track_id=locked_track_id, paused=paused))

    return results
