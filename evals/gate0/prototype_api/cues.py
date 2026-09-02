#!/usr/bin/env python3
"""
evals/gate0/prototype_api/cues.py

INTERIM cue layer for the live detector API. This is explicitly NOT the Stage-6 calibrated LLM
judge (VISION_ARCHITECTURE.md Stage 6, EVAL_HARNESS_STAGE0_SPEC.md §10/§12) -- it is a plain
lookup into the exercise library's own coaching_cues text, never cue copy invented here.

Positive-first (CLAUDE.md §2's "positive-before-correction" invariant): a clean rep (no committed
flags) maps to the exercise's `coaching_cues.good_rep`; a flagged rep maps to the FIRST committed
flag's `coaching_cues.flag_cues[...]` text, in the exact order run_detector's own `flags` list
already produced -- never re-ordered or re-decided here (that ordering is
EXERCISE_SUSTAINED_FLAG_IDS-then-rep-aggregate, detector/adapter.py's job, not this module's).

Word cap: LIVE_CUE_MAX_WORDS (config.py), counted with the SAME len(text.split()) aggregate.py's
existing Stage-0 coaching-cue assertion already uses -- one definition of "word count", not two.
An over-cap cue is FLAGGED (CueResult.over_word_cap), never silently truncated -- squat.json's
shallow_depth cue ("Sit a little deeper — hip crease to knee level") is over the 8-word cap; that
is a copy bug for someone to fix in the exercise library, not something to hide by cutting words.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import gate_config


@dataclass
class CueResult:
    text: Optional[str]  # None only if the exercise library has no cue for this situation at all
    over_word_cap: bool
    word_count: int


def _word_count(text: str) -> int:
    return len(text.split())


def cue_for_rep(exercise_json: Dict[str, Any], flags: List[str]) -> CueResult:
    """flags: the committed flags of the rep to comment on (usually the latest completed rep;
    main.py decides which rep, this function only maps flags -> cue text)."""
    cues = exercise_json.get("coaching_cues", {})
    if not flags:
        text = cues.get("good_rep")
    else:
        text = cues.get("flag_cues", {}).get(flags[0])

    if text is None:
        return CueResult(text=None, over_word_cap=False, word_count=0)

    count = _word_count(text)
    return CueResult(
        text=text, over_word_cap=count > gate_config.LIVE_CUE_MAX_WORDS, word_count=count
    )
