#!/usr/bin/env python3
"""
evals/gate0/detector/flag_hysteresis.py

Flag-level temporal hysteresis + visibility gating (SPRINT.md G2 "precision-first flagging" --
the direct fix for the field hip-sag false positive: a rep with a genuinely straight body flagged
because ONE noisy frame's angle dipped below the threshold).

detector/faults.py evaluates each fault rule per FRAME (unchanged -- Stage 1 kept the rules
"as-is" and this stays true: no new fault semantics, no threshold tuning). Stage 1's adapter.py
called that rule exactly once, at the rep's single deepest-point frame -- fine for "what did the
worst point look like", useless for telling a one-frame jitter apart from a real, sustained
fault. This module re-evaluates the rule across EVERY frame in the rep's [start_ms, end_ms]
window (the RepEvent from rep_counter.py -- untouched; see that module's own docstring, and
ROADMAP.md's Stage 3 entry, which is ALREADY built there: smoothing/hysteresis/tempo/graded-depth
on the rep COUNTER, not the flags) and only commits a flag to the rep once the fault held true
for a large enough FRACTION of the frames where it could be evaluated at all.

Scope: only the 5 per-frame, landmark-based flags have a predicate in faults.py and go through
this module -- knee_cave_left, knee_cave_right, shallow_depth, elbow_flare, hip_sag
(SUSTAINED_FLAG_IDS). shallow_pushup and shallow_lunge are REP-AGGREGATE rules (compared against
the rep's overall smoothed minimum angle from rep_counter.py, not any single frame's landmarks);
they already inherit that module's temporal smoothing and have no per-frame landmark evidence to
gate on, so they are evaluated exactly as before (detector/faults.py's aggregate functions,
called once per rep) and never reach this module.

Three possible outcomes per flag, per rep -- FlagOutcome:
  - PRESENT / ABSENT: the fault held true in >= its required fraction of evaluable frames.
  - INSUFFICIENT_EVIDENCE: too few frames had visible-enough landmarks to judge at all
    (< FLAG_MIN_EVALUABLE_FRAMES). This is NOT "absent" -- it is surfaced to the caller
    (detector/adapter.py) as its own outcome, never silently folded into "no flag" the way a
    missing landmark silently was before Stage 3.

A frame's evidence for a flag doesn't count at all (neither towards "present" nor "absent") if
that flag's OWN involved landmarks are below FLAG_MIN_VISIBILITY on that frame -- this reuses
each predicate's own per-side "which landmarks does this rule actually read" logic (via the
`min_visibility` parameter every faults.py predicate takes) rather than a second, independently
maintained landmark list that could silently disagree about which side's data a dual-side rule
(elbow_flare, hip_sag) is trusting.

Severity-aware, precision-first (SPRINT.md G2): the required sustained fraction is keyed off the
SAME severity taxonomy as everything else (EXERCISE_LIBRARY.md §4) -- high-severity requires the
LARGEST fraction, trading missed faults for never falsely accusing a good rep on a safety-relevant
flag. All three fraction floors (and FLAG_MIN_VISIBILITY, FLAG_MIN_EVALUABLE_FRAMES) are
PLACEHOLDER values in config.py pending real golden-set tuning (GOLDEN_SET_PROTOCOL.md §8) --
this module is the mechanism, not the calibration.

Safety-veto invariant (VISION_ARCHITECTURE.md Stage 5b): this module only governs WHEN a flag
FIRST commits to a rep. Nothing here, and nothing downstream of it, can un-commit or clear a flag
that already committed -- there is no "clear" operation in this module at all, only "decide once".
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, Optional, Sequence, Tuple

import gate_config
from detector import faults

# Fault ids whose rule reads a single frame's landmarks (faults.py has a *_present predicate for
# each) -- the only flags this module ever evaluates. Rep-aggregate flags (shallow_pushup,
# shallow_lunge) are deliberately absent; see module docstring.
_PREDICATES: Dict[str, Callable[..., Optional[bool]]] = {
    "knee_cave_left": faults.knee_cave_left_present,
    "knee_cave_right": faults.knee_cave_right_present,
    "shallow_depth": lambda person, pose_model, thresholds, min_visibility=None: (
        faults.shallow_depth_present(person, pose_model, min_visibility)
    ),
    "elbow_flare": faults.elbow_flare_present,
    "hip_sag": faults.hip_sag_present,
}

SUSTAINED_FLAG_IDS: Tuple[str, ...] = tuple(_PREDICATES.keys())

# Which of SUSTAINED_FLAG_IDS applies to each exercise -- mirrors which flags each exercise's
# faults.py predicates can ever produce (ROADMAP.md Stage 1 scope: squat/pushup/lunge). lunge has
# none: shallow_lunge is its only implemented fault, and it's rep-aggregate (see module
# docstring), so lunge never goes through this module at all today.
EXERCISE_SUSTAINED_FLAG_IDS: Dict[str, Tuple[str, ...]] = {
    "squat": ("knee_cave_left", "knee_cave_right", "shallow_depth"),
    "pushup": ("elbow_flare", "hip_sag"),
    "lunge": (),
}


class FlagOutcome(Enum):
    PRESENT = "present"
    ABSENT = "absent"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


@dataclass(frozen=True)
class FlagHysteresisConfig:
    min_visibility: float = gate_config.FLAG_MIN_VISIBILITY
    min_evaluable_frames: int = gate_config.FLAG_MIN_EVALUABLE_FRAMES
    min_fraction_high_sev: float = gate_config.FLAG_HYSTERESIS_MIN_FRACTION_HIGH_SEV
    min_fraction_med_sev: float = gate_config.FLAG_HYSTERESIS_MIN_FRACTION_MED_SEV
    min_fraction_low_sev: float = gate_config.FLAG_HYSTERESIS_MIN_FRACTION_LOW_SEV
    # Used by detector/adapter.py (not by evaluate_sustained_flag itself, which is agnostic of
    # phase) to narrow a bottom-phase-only fault's window to the bottom fraction of the rep's OWN
    # excursion range -- see config.py's FLAG_BOTTOM_PHASE_FRACTION docstring for why it's
    # self-relative rather than gated on the exercise's correct-depth threshold.
    bottom_phase_fraction: float = gate_config.FLAG_BOTTOM_PHASE_FRACTION

    def min_fraction_for_severity(self, severity: str) -> float:
        try:
            return {
                "high": self.min_fraction_high_sev,
                "med": self.min_fraction_med_sev,
                "low": self.min_fraction_low_sev,
            }[severity]
        except KeyError:
            raise ValueError(
                f"severity must be one of high/med/low (EXERCISE_LIBRARY.md §4), got {severity!r}"
            ) from None


def evaluate_sustained_flag(
    fault_id: str,
    frame_records: Sequence[Tuple[Dict[str, Any], str]],
    thresholds: Dict[str, Any],
    severity: str,
    config: Optional[FlagHysteresisConfig] = None,
) -> FlagOutcome:
    """frame_records: [(person, pose_model), ...] for every frame in the rep's window (order
    doesn't matter -- this counts occurrences, it doesn't track a sequence). fault_id must be one
    of SUSTAINED_FLAG_IDS."""
    predicate = _PREDICATES.get(fault_id)
    if predicate is None:
        raise KeyError(
            f"{fault_id!r} has no per-frame predicate -- flag_hysteresis only covers "
            f"{SUSTAINED_FLAG_IDS} (rep-aggregate flags like shallow_pushup/shallow_lunge are "
            f"evaluated by detector/faults.py directly, never through this module)"
        )
    cfg = config or FlagHysteresisConfig()
    # Validate severity up front -- not lazily inside the fraction check below, which an
    # INSUFFICIENT_EVIDENCE short-circuit would otherwise skip entirely, silently accepting a
    # bad severity whenever there happened to be too little evidence to reach that check.
    cfg.min_fraction_for_severity(severity)

    evaluable = 0
    present = 0
    for person, pose_model in frame_records:
        result = predicate(person, pose_model, thresholds, min_visibility=cfg.min_visibility)
        if result is None:
            continue  # landmark(s) missing or below FLAG_MIN_VISIBILITY -- not evidence either way
        evaluable += 1
        if result:
            present += 1

    if evaluable < cfg.min_evaluable_frames:
        return FlagOutcome.INSUFFICIENT_EVIDENCE

    fraction = present / evaluable
    required = cfg.min_fraction_for_severity(severity)
    return FlagOutcome.PRESENT if fraction >= required else FlagOutcome.ABSENT
