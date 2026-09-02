#!/usr/bin/env python3
"""
evals/gate0/scorers/form_pr.py

Per-flag precision/recall over the golden set (EVAL_HARNESS_STAGE0_SPEC.md §6), gated against
config.py's severity-split floors -- the pair v1/v2 never measured.

Two edge-case choices, made deliberately here per the spec (not incidental, and not to be
"fixed" later without re-reading §6):
  - A flag carried by a PHANTOM detected rep (no matching ground-truth rep) counts as a false
    positive for that flag. The rep itself never happened, so any fault called on it is also
    fabricated.
  - A fault on a MISSED ground-truth rep (no matching detected rep) counts as a false negative
    for that flag. The detector never got the chance to catch it, but the fault was real.

Severity floors are looked up per-flag and applied per-flag (never one flat bar): high-severity
carries the strictest precision floor but the most lenient recall floor -- precision-first, per
EXERCISE_LIBRARY.md §4.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional

import gate_config
from scorers.phantom import PHANTOM_CLIP_TYPES
from scorers.rep_match import match_reps

_PRECISION_FLOORS = {
    "high": gate_config.FORM_PRECISION_FLOOR_HIGH_SEV,
    "med": gate_config.FORM_PRECISION_FLOOR_MED_SEV,
    # low-severity is advisory / logged only -- no enforced floor (EXERCISE_LIBRARY.md §4).
}
_RECALL_FLOORS = {
    "high": gate_config.FORM_RECALL_FLOOR_HIGH_SEV,
    "med": gate_config.FORM_RECALL_FLOOR_MED_SEV,
}


@dataclass
class PR:
    tp: int = 0
    fp: int = 0
    fn: int = 0

    @property
    def precision(self) -> Optional[float]:
        denom = self.tp + self.fp
        return self.tp / denom if denom else None

    @property
    def recall(self) -> Optional[float]:
        denom = self.tp + self.fn
        return self.tp / denom if denom else None


@dataclass
class FlagGateResult:
    severity: str
    tp: int
    fp: int
    fn: int
    precision: Optional[float]
    recall: Optional[float]
    precision_floor: Optional[float]
    recall_floor: Optional[float]
    precision_pass: bool
    recall_pass: bool

    @property
    def passed(self) -> bool:
        return self.precision_pass and self.recall_pass


def score_clip_form_pr(gt_reps: list[dict[str, Any]], det_reps: list[dict[str, Any]]) -> dict[str, PR]:
    """Per-flag TP/FP/FN for a single clip, over its matched (gt, det) rep pairs."""
    per_flag: dict[str, PR] = {}

    def bucket(flag: str) -> PR:
        return per_flag.setdefault(flag, PR())

    for gt, det in match_reps(gt_reps, det_reps):
        if gt is not None and det is not None:
            gt_faults = set(gt.get("faults", []))
            det_flags = set(det.get("flags", []))
            for flag in gt_faults | det_flags:
                pr = bucket(flag)
                in_gt = flag in gt_faults
                in_det = flag in det_flags
                if in_gt and in_det:
                    pr.tp += 1
                elif in_det:  # in_det and not in_gt
                    pr.fp += 1
                else:  # in_gt and not in_det
                    pr.fn += 1
        elif gt is None:  # phantom detected rep -- every flag it carries is a false accusation
            for flag in det.get("flags", []):
                bucket(flag).fp += 1
        else:  # det is None -- missed ground-truth rep; its real faults were never caught
            for flag in gt.get("faults", []):
                bucket(flag).fn += 1
    return per_flag


def aggregate_form_pr(clips: Iterable[Any]) -> dict[str, dict[str, PR]]:
    """exercise -> flag -> PR, summed across every clip with real per-rep faults. Only
    phantom_bench/phantom_empty carry no faults by construction (EVAL_HARNESS_STAGE0_SPEC.md
    §5) and are excluded here -- graded separately by scorers/phantom.py instead. bystander is
    NOT phantom-like (the resolved cross-doc decision -- see scorers/phantom.py's module
    docstring): the user's real reps are labeled normally, faults included, so a bystander clip
    contributes form P/R evidence exactly like a 'normal' one, in addition to being scored by
    scorers/subject_lock.py."""
    result: dict[str, dict[str, PR]] = {}
    for clip in clips:
        if clip.clip_type in PHANTOM_CLIP_TYPES:
            continue
        per_flag = score_clip_form_pr(clip.gt_reps, clip.det_reps)
        ex_bucket = result.setdefault(clip.exercise, {})
        for flag, pr in per_flag.items():
            total = ex_bucket.setdefault(flag, PR())
            total.tp += pr.tp
            total.fp += pr.fp
            total.fn += pr.fn
    return result


def gate_flag(pr: PR, severity: str) -> FlagGateResult:
    precision_floor = _PRECISION_FLOORS.get(severity)
    recall_floor = _RECALL_FLOORS.get(severity)
    precision = pr.precision
    recall = pr.recall
    # No floor defined (low severity) or no observations yet (denominator 0) -> nothing to
    # fail on. A flag that's never been raised or never applicable can't have violated a floor.
    precision_pass = precision_floor is None or precision is None or precision >= precision_floor
    recall_pass = recall_floor is None or recall is None or recall >= recall_floor
    return FlagGateResult(
        severity=severity,
        tp=pr.tp,
        fp=pr.fp,
        fn=pr.fn,
        precision=precision,
        recall=recall,
        precision_floor=precision_floor,
        recall_floor=recall_floor,
        precision_pass=precision_pass,
        recall_pass=recall_pass,
    )


def gate_form_pr(
    per_exercise: dict[str, dict[str, PR]], severities: dict[str, dict[str, str]]
) -> dict[str, dict[str, FlagGateResult]]:
    """Apply each flag's severity-matching floor (EVAL_HARNESS_STAGE0_SPEC.md §6). Raises
    ValueError if a flag observed in the golden set has no severity entry in the exercise
    library -- that's a golden-set/library mismatch, not a thing to silently skip."""
    out: dict[str, dict[str, FlagGateResult]] = {}
    for exercise, flags in per_exercise.items():
        ex_severities = severities.get(exercise, {})
        bucket = out.setdefault(exercise, {})
        for flag, pr in flags.items():
            severity = ex_severities.get(flag)
            if severity is None:
                raise ValueError(
                    f"flag {flag!r} observed on exercise {exercise!r} has no severity in the "
                    f"exercise library -- every fault referenced by the golden set must exist "
                    f"there (EVAL_HARNESS_STAGE0_SPEC.md §5)"
                )
            bucket[flag] = gate_flag(pr, severity)
    return out
