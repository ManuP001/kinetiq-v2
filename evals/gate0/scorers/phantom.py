#!/usr/bin/env python3
"""
evals/gate0/scorers/phantom.py

No-phantom-reps gate (EVAL_HARNESS_STAGE0_SPEC.md §5, §7): clips of type phantom_bench or
phantom_empty carry ground_truth.actual_reps == 0 by construction -- an empty room or a moved
bench, nobody exercising. The detector must report zero reps on every one of them. This is
exactly the bench->6-reps failure mode (EVAL_STRATEGY.md case #1); a single phantom rep on any of
these clips is a hard fail.

bystander is deliberately NOT in this gate (the resolved cross-doc decision,
EVAL_HARNESS_STAGE0_SPEC.md §5/§7, EVAL_STRATEGY.md, EXERCISE_LIBRARY.md §5, ROADMAP.md): the
user really is exercising while a second person stands nearby, so a bystander clip's real
rep count is > 0 by construction, not 0. It's scored by scorers/subject_lock.py (does the
skeleton stay on the user) and folded into ordinary rep-accuracy scoring instead -- treating it
as phantom here would hard-fail every correctly-functioning bystander clip.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, List

import gate_config

PHANTOM_CLIP_TYPES = ("phantom_bench", "phantom_empty")


@dataclass
class PhantomResult:
    checked: int = 0
    failures: List[str] = field(default_factory=list)  # clip_ids that produced a nonzero count

    @property
    def passed(self) -> bool:
        return not self.failures


def score_phantom(clips: Iterable[Any]) -> PhantomResult:
    result = PhantomResult()
    for clip in clips:
        if clip.clip_type not in PHANTOM_CLIP_TYPES:
            continue
        result.checked += 1
        if gate_config.PHANTOM_REPS_MUST_BE_ZERO and clip.detected_reps != 0:
            result.failures.append(clip.clip_id)
    return result
