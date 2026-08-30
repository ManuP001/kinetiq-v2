#!/usr/bin/env python3
"""
evals/gate0/detector/plausibility.py

Human-pose plausibility check (VISION_ARCHITECTURE.md Stage 3: "A bench has no plausible
33-point skeleton -- it fails here"). Independent of subject-lock: a person detector can hand
subject-lock a bounding box that LOOKS like a person (so subject-lock happily tracks it), while
this check still rejects every frame of it because the "skeleton" inside that box isn't a
plausible human. Two gates, deliberately separate (Ch 30: each specialist does one job):

  1. Enough of the scoped landmarks (keypoint_map.SCOPED_LANDMARK_NAMES) must be visible.
  2. The visible limb proportions (shin:thigh ratio) must fall in a human-plausible band.

Both thresholds default from config.py (imported via gate_config) -- never restated as literals
-- but are overridable via PlausibilityConfig, same pattern as detector/rep_counter.py, so a
caller (run_detector's `config` parameter) can tune them without touching global config.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import gate_config
from detector.geometry import distance
from detector.keypoint_map import SCOPED_LANDMARK_NAMES, get_point


@dataclass(frozen=True)
class PlausibilityConfig:
    min_keypoint_visibility: float = gate_config.MIN_KEYPOINT_VISIBILITY
    min_visible_keypoint_fraction: float = gate_config.MIN_VISIBLE_KEYPOINT_FRACTION
    human_limb_ratio_min: float = gate_config.HUMAN_LIMB_RATIO_MIN
    human_limb_ratio_max: float = gate_config.HUMAN_LIMB_RATIO_MAX


def visible_fraction(
    person: Dict[str, Any], pose_model: str, config: Optional[PlausibilityConfig] = None
) -> float:
    """Fraction of the scoped landmark set visible above min_keypoint_visibility."""
    cfg = config or PlausibilityConfig()
    total = len(SCOPED_LANDMARK_NAMES)
    if total == 0:
        return 0.0
    visible = 0
    for name in SCOPED_LANDMARK_NAMES:
        point = get_point(person, pose_model, name)
        if point is not None and point[3] >= cfg.min_keypoint_visibility:
            visible += 1
    return visible / total


def _limb_ratio(
    person: Dict[str, Any], pose_model: str, side: str, cfg: PlausibilityConfig
) -> Optional[float]:
    """shin length (knee->ankle) / thigh length (hip->knee) for one side, or None if the
    triple isn't sufficiently visible."""
    hip = get_point(person, pose_model, f"{side}_hip")
    knee = get_point(person, pose_model, f"{side}_knee")
    ankle = get_point(person, pose_model, f"{side}_ankle")
    if hip is None or knee is None or ankle is None:
        return None
    min_vis = cfg.min_keypoint_visibility
    if hip[3] < min_vis or knee[3] < min_vis or ankle[3] < min_vis:
        return None
    thigh = distance((hip[0], hip[1]), (knee[0], knee[1]))
    shin = distance((knee[0], knee[1]), (ankle[0], ankle[1]))
    if thigh == 0:
        return None
    return shin / thigh


def has_plausible_limb_ratio(
    person: Dict[str, Any], pose_model: str, config: Optional[PlausibilityConfig] = None
) -> bool:
    """True if EITHER leg's shin:thigh ratio is in the plausible human band, or if neither leg
    has enough visible landmarks to judge at all (in which case the visibility gate above is the
    one doing the rejecting -- this check only actively fails a frame it can actually measure)."""
    cfg = config or PlausibilityConfig()
    ratios = [
        r for r in (
            _limb_ratio(person, pose_model, "left", cfg),
            _limb_ratio(person, pose_model, "right", cfg),
        )
        if r is not None
    ]
    if not ratios:
        return True
    return any(cfg.human_limb_ratio_min <= r <= cfg.human_limb_ratio_max for r in ratios)


def is_plausible_human(
    person: Dict[str, Any], pose_model: str, config: Optional[PlausibilityConfig] = None
) -> bool:
    """The Stage-3 rep-validity gate's human-plausibility check. A frame that fails this can
    never contribute to a rep, regardless of subject-lock status."""
    cfg = config or PlausibilityConfig()
    if visible_fraction(person, pose_model, cfg) < cfg.min_visible_keypoint_fraction:
        return False
    return has_plausible_limb_ratio(person, pose_model, cfg)
