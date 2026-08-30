#!/usr/bin/env python3
"""
evals/gate0/scorers/view.py

View robustness (EVAL_HARNESS_STAGE0_SPEC.md §7, EVAL_STRATEGY.md §7): the spread of rep-count
accuracy across front/side/diagonal camera views of the same exercise, gated against
VIEW_ACC_MAX_GAP -- a detector that's great from the side and useless from the front isn't
"90% accurate", it's untested from two of the three angles testers actually use.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Optional

import gate_config

VIEWS = ("front", "side", "diagonal")


def _clip_accuracy(clip: Any) -> float:
    actual = clip.actual_reps
    detected = clip.detected_reps
    if actual == 0:
        return 1.0 if detected == 0 else 0.0
    return max(0.0, 1 - abs(detected - actual) / actual)


@dataclass
class ViewResult:
    accuracy_by_view: Dict[str, float] = field(default_factory=dict)

    @property
    def gap(self) -> Optional[float]:
        if len(self.accuracy_by_view) < 2:
            return None
        vals = self.accuracy_by_view.values()
        return max(vals) - min(vals)

    def passed(self, max_gap: Optional[float] = None) -> bool:
        if max_gap is None:
            max_gap = gate_config.VIEW_ACC_MAX_GAP
        gap = self.gap
        return gap is None or gap <= max_gap


def score_view_robustness(clips: Iterable[Any]) -> Dict[str, ViewResult]:
    """exercise -> ViewResult, averaging rep-count accuracy per view over 'normal' clips that
    carry a labeled view in {front, side, diagonal}."""
    by_exercise_view: Dict[str, Dict[str, list[float]]] = {}
    for clip in clips:
        if clip.clip_type != "normal" or clip.view not in VIEWS:
            continue
        acc = _clip_accuracy(clip)
        by_exercise_view.setdefault(clip.exercise, {}).setdefault(clip.view, []).append(acc)

    out: Dict[str, ViewResult] = {}
    for exercise, view_map in by_exercise_view.items():
        result = ViewResult()
        for view, accs in view_map.items():
            result.accuracy_by_view[view] = sum(accs) / len(accs)
        out[exercise] = result
    return out
