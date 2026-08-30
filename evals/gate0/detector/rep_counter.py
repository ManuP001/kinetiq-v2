#!/usr/bin/env python3
"""
evals/gate0/detector/rep_counter.py

The hybrid rep counter (VISION_ARCHITECTURE.md Stage 4, deterministic-FSM half only -- the
"optional learned boundary model" is Stage 3 of ROADMAP.md, not built here). Generic and
exercise-agnostic: it finds "genuine down-up excursions" in ANY smoothed angle signal, not just
knee/elbow angle, so it has no notion of squat/pushup/lunge at all -- that mapping lives in
exercise_signals.py, one layer up.

Algorithm: median-smooth the signal, then track it as a simple valley-with-minimum-prominence
detector with hysteresis:
  - watch for the running peak ("top reference") while seeking a descent;
  - once the signal has dropped more than REP_COUNTER_HYSTERESIS_DEG below that peak, we're
    descending -- keep tracking the running minimum;
  - once the signal has risen more than the hysteresis margin above that minimum, we're
    ascending -- the tracked minimum is the candidate rep's bottom;
  - the rep candidate CLOSES when the signal returns to >= REP_COUNTER_TOP_ANGLE_DEG.

A closed candidate only COUNTS if both:
  - its excursion (top reference - minimum) is >= REP_MIN_EXCURSION_DEG (below that: fidget/pose
    noise, not a rep attempt -- discarded entirely, not even as "very shallow"); and
  - its duration is within [MIN_REP_DURATION_MS, MAX_REP_DURATION_MS] (the rep-validity gate's
    tempo-plausibility check, VISION_ARCHITECTURE.md Stage 3) -- too fast is jitter, too slow
    isn't one continuous rep.

Depth is deliberately graded, not thresholded here: every counted rep reports its raw minimum
angle; how "good" that depth was (relative to the exercise's own correct-bottom band) is computed
by the caller (detector/adapter.py, via exercise_signals.get_bottom_angle_max) -- this module
doesn't know what a "correct" depth is for any given exercise, only where the genuine excursions
are (EVAL_STRATEGY.md case #5: partial reps count, graded, not dropped).

A None sample (no locked/plausible subject that frame -- a signal gap) is simply skipped: it
doesn't advance the running peak/minimum, but it doesn't reset an excursion in progress either. A
gap long enough to make the eventual duration implausible is caught by the tempo check above, not
by special-cased gap logic.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import gate_config
from detector.geometry import median_filter


@dataclass
class RepEvent:
    idx: int
    start_ms: int
    end_ms: int
    duration_ms: int
    top_ref_deg: float
    min_angle_deg: float
    min_angle_t: int  # timestamp of the rep's deepest point -- where faults.py evaluates form

    @property
    def excursion_deg(self) -> float:
        return self.top_ref_deg - self.min_angle_deg


def _passes_gate(excursion: float, duration_ms: int, config) -> bool:
    if excursion < config.min_excursion_deg:
        return False
    return config.min_rep_duration_ms <= duration_ms <= config.max_rep_duration_ms


@dataclass(frozen=True)
class RepCounterConfig:
    smoothing_window_frames: int = gate_config.REP_COUNTER_SMOOTHING_WINDOW_FRAMES
    hysteresis_deg: float = gate_config.REP_COUNTER_HYSTERESIS_DEG
    top_angle_deg: float = gate_config.REP_COUNTER_TOP_ANGLE_DEG
    min_excursion_deg: float = gate_config.REP_MIN_EXCURSION_DEG
    min_rep_duration_ms: int = gate_config.MIN_REP_DURATION_MS
    max_rep_duration_ms: int = gate_config.MAX_REP_DURATION_MS


def count_reps(
    samples: Sequence[Tuple[int, Optional[float]]], config: Optional[RepCounterConfig] = None
) -> List[RepEvent]:
    """samples: [(t_ms, angle_or_None), ...] in ascending time order, already restricted to the
    locked/plausible subject (see detector/adapter.py). Returns only rep events that PASS the
    min-excursion and tempo gates -- discarded candidates are simply absent."""
    cfg = config or RepCounterConfig()

    times = [t for t, _ in samples]
    raw_angles: List[Optional[float]] = [a for _, a in samples]
    smoothed = median_filter(raw_angles, cfg.smoothing_window_frames)

    events: List[RepEvent] = []
    state = "SEEKING_DESCENT"  # -> "DESCENDING" -> "ASCENDING" -> back to SEEKING_DESCENT
    top_ref: Optional[float] = None
    top_ref_t: Optional[int] = None
    running_min: Optional[float] = None
    running_min_t: Optional[int] = None

    for t, angle in zip(times, smoothed):
        if angle is None:
            continue

        # A single sample can cascade through more than one state transition when samples are
        # sparse (e.g. a clip with only a handful of frames per rep) -- DESCENDING can complete
        # its ascent and close the rep in the very next sample, with no separate sample in
        # between to "notice" ASCENDING first. Re-run the transition checks against this same
        # (t, angle) until a pass makes no further state change, rather than advancing to the
        # next sample after exactly one transition.
        while True:
            prev_state = state

            if state == "SEEKING_DESCENT":
                if top_ref is None or angle >= top_ref:
                    top_ref, top_ref_t = angle, t
                elif angle <= top_ref - cfg.hysteresis_deg:
                    state = "DESCENDING"
                    running_min, running_min_t = angle, t

            elif state == "DESCENDING":
                if angle <= running_min:  # type: ignore[operator]
                    running_min, running_min_t = angle, t
                elif angle >= running_min + cfg.hysteresis_deg:  # type: ignore[operator]
                    state = "ASCENDING"

            elif state == "ASCENDING":
                if angle < running_min:  # type: ignore[operator]
                    # Dipped again before reaching the top -- still the same descent; keep
                    # tracking the (now lower) minimum.
                    running_min, running_min_t = angle, t
                    state = "DESCENDING"
                elif angle >= cfg.top_angle_deg:
                    excursion = top_ref - running_min  # type: ignore[operator]
                    duration_ms = t - top_ref_t  # type: ignore[operator]
                    if _passes_gate(excursion, duration_ms, cfg):
                        events.append(RepEvent(
                            idx=len(events) + 1,
                            start_ms=top_ref_t,  # type: ignore[arg-type]
                            end_ms=t,
                            duration_ms=duration_ms,
                            top_ref_deg=top_ref,  # type: ignore[arg-type]
                            min_angle_deg=running_min,
                            min_angle_t=running_min_t,  # type: ignore[arg-type]
                        ))
                    # Whether counted or discarded, this excursion is resolved -- start looking
                    # for the next one from here.
                    state = "SEEKING_DESCENT"
                    top_ref, top_ref_t = angle, t
                    running_min, running_min_t = None, None

            if state == prev_state:
                break

    return events
