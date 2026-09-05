#!/usr/bin/env python3
"""
evals/gate0/detector/geometry.py

Pure 2D geometry helpers shared by the plausibility check and the exercise-signal extraction.
2D-only (x, y) deliberately: MoveNet has no z at all (EVAL_HARNESS_STAGE0_SPEC.md §5: "z is null
for 2D-only pose models"), and keeping angle math 2D-only means it behaves identically regardless
of which pose model produced the frame -- exactly the "model-agnostic feature vector"
VISION_ARCHITECTURE.md §2 calls for. Revisit if a later stage's pose-model bake-off (Stage 2)
shows 3D world landmarks meaningfully improve angle accuracy.
"""
from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

XY = Tuple[float, float]


def angle_deg(a: XY, b: XY, c: XY) -> float:
    """The angle ABC at vertex b, in degrees, given three (x, y) points. 180 = fully extended
    (straight line through b), smaller = more flexed."""
    v1 = (a[0] - b[0], a[1] - b[1])
    v2 = (c[0] - b[0], c[1] - b[1])
    len1 = math.hypot(*v1)
    len2 = math.hypot(*v2)
    if len1 == 0 or len2 == 0:
        return 0.0
    cos_theta = (v1[0] * v2[0] + v1[1] * v2[1]) / (len1 * len2)
    cos_theta = max(-1.0, min(1.0, cos_theta))  # guard fp drift outside [-1, 1]
    return math.degrees(math.acos(cos_theta))


def distance(a: XY, b: XY) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def midpoint(a: XY, b: XY) -> XY:
    return ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)


def torso_lean_deg(shoulder_mid: XY, hip_mid: XY) -> float:
    """Absolute deviation of the torso (hip -> shoulder) from vertical, in degrees. 0 = upright.

    Transliterated from kinetiq-demo2's shipped `torsoLeanDeg()` so the offline detector measures
    the same quantity the product already does, rather than inventing a second definition of
    "torso lean" that would disagree with it:

        Math.abs(Math.atan2(sh.x - hp.x, hp.y - sh.y) * 180/Math.PI)

    Note the argument order: atan2(horizontal offset, vertical offset), which yields the angle
    FROM VERTICAL -- not the usual atan2(y, x) angle from horizontal. `hp.y - sh.y` is positive
    when the shoulders sit above the hips, because image y grows downward. Absolute value, so a
    forward and a backward lean of the same magnitude read the same; the exercises that use this
    (squat, lunge) both cap total deviation rather than direction.
    """
    return abs(math.degrees(math.atan2(shoulder_mid[0] - hip_mid[0], hip_mid[1] - shoulder_mid[1])))


def median(values: Sequence[float]) -> float:
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2 == 1:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2.0


def median_filter(series: Sequence[Optional[float]], window: int) -> List[Optional[float]]:
    """Median filter over a (possibly gappy, None-valued) series. The window is centred on each
    index and uses only the non-None samples inside it; an index with zero valid samples in its
    window stays None (a genuine data gap isn't smoothed into a fabricated value)."""
    if window < 1:
        raise ValueError("window must be >= 1")
    half = window // 2
    n = len(series)
    out: List[Optional[float]] = []
    for i in range(n):
        lo = max(0, i - half)
        hi = min(n, i + half + 1)
        valid = [v for v in series[lo:hi] if v is not None]
        out.append(median(valid) if valid else None)
    return out


def bbox_centroid(box: Sequence[float]) -> XY:
    """box = [x, y, w, h] -> its centre point."""
    x, y, w, h = box
    return (x + w / 2.0, y + h / 2.0)


def bbox_area(box: Sequence[float]) -> float:
    _, _, w, h = box
    return max(0.0, w) * max(0.0, h)


def bbox_iou(a: Sequence[float], b: Sequence[float]) -> float:
    """Intersection-over-union of two [x, y, w, h] boxes."""
    ax0, ay0, aw, ah = a
    bx0, by0, bw, bh = b
    ax1, ay1 = ax0 + aw, ay0 + ah
    bx1, by1 = bx0 + bw, by0 + bh

    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    iw, ih = max(0.0, ix1 - ix0), max(0.0, iy1 - iy0)
    intersection = iw * ih
    union = bbox_area(a) + bbox_area(b) - intersection
    return intersection / union if union > 0 else 0.0
