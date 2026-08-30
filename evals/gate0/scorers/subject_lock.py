#!/usr/bin/env python3
"""
evals/gate0/scorers/subject_lock.py

Subject-lock accuracy (EVAL_HARNESS_STAGE0_SPEC.md §7, EVAL_STRATEGY.md §7): over every
multi-person golden clip, what fraction of frames stayed locked onto the ground-truth subject.

Frame counts come from the detector's own bootstrap self-report
(detected.json's subject_lock.{frames_total, frames_on_expected_subject}) -- Stage 0 does not
re-run tracking over keypoints.jsonl itself; that needs the Stage-1 detector adapter
(EVAL_HARNESS_STAGE0_SPEC.md §12).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Optional

import gate_config


@dataclass
class SubjectLockResult:
    per_clip: Dict[str, float] = field(default_factory=dict)  # clip_id -> fraction locked

    @property
    def mean(self) -> Optional[float]:
        if not self.per_clip:
            return None
        return sum(self.per_clip.values()) / len(self.per_clip)

    def passed(self, floor: Optional[float] = None) -> bool:
        """Every multi-person clip must individually clear the floor
        (EXERCISE_LIBRARY.md §5: 'Subject-lock >=99% ... on its multi-person clips') -- one
        badly-tracked clip isn't rescued by averaging with good ones."""
        if floor is None:
            floor = gate_config.SUBJECT_LOCK_FLOOR
        if not self.per_clip:
            return True  # vacuous pass: no multi-person clips to check
        return all(frac >= floor for frac in self.per_clip.values())


def score_subject_lock(clips: Iterable[Any]) -> SubjectLockResult:
    result = SubjectLockResult()
    for clip in clips:
        num_people = clip.subject_num_people_in_frame
        if num_people is None or num_people < 2:
            continue
        lock = clip.subject_lock
        if not lock or not lock.get("frames_total"):
            continue
        result.per_clip[clip.clip_id] = lock["frames_on_expected_subject"] / lock["frames_total"]
    return result
