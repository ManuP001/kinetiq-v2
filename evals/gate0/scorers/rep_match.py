#!/usr/bin/env python3
"""
evals/gate0/scorers/rep_match.py

Monotonic (Needleman-Wunsch-style) alignment between ground-truth reps and detected reps
(EVAL_HARNESS_STAGE0_SPEC.md §6). Reps happen in order, so we align them by position, not by
content -- but counts can differ when the detector phantom-counts or misses a rep, so a plain
zip() isn't enough.

Cost model, taken directly from the spec:
    cost(pair)       = 0   # always free to line up a true rep with a detected rep
    cost(gap in det) = 1   # a true rep with no detected counterpart  -> MISSED
    cost(gap in gt)  = 1   # a detected rep with no true counterpart  -> PHANTOM

Because matching is always free, the optimal alignment always pairs up min(len(gt), len(det))
reps and leaves |len(gt) - len(det)| unmatched -- but the full DP is implemented anyway (rather
than that shortcut) so this stays correct if a future revision makes match cost content-dependent
(e.g. penalising a match between reps whose timestamps are far apart), and so it visibly matches
the spec's Needleman-Wunsch framing.
"""
from __future__ import annotations

from typing import Any, Optional, Sequence

MatchPair = tuple[Optional[Any], Optional[Any]]


def match_reps(gt_reps: Sequence[Any], det_reps: Sequence[Any]) -> list[MatchPair]:
    """Return the min-cost alignment as a list of (gt_rep, det_rep) pairs, in order, where
    either side of a pair may be None (a gap: missed on the gt side, phantom on the det side)."""
    m, n = len(gt_reps), len(det_reps)

    # dp[i][j] = min alignment cost of gt[:i] vs det[:j]
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        dp[i][0] = i  # all i true reps missed
    for j in range(1, n + 1):
        dp[0][j] = j  # all j detected reps phantom

    for i in range(1, m + 1):
        for j in range(1, n + 1):
            match_cost = dp[i - 1][j - 1]      # +0
            missed_cost = dp[i - 1][j] + 1
            phantom_cost = dp[i][j - 1] + 1
            dp[i][j] = min(match_cost, missed_cost, phantom_cost)

    # Backtrack from the end. On a tie, prefer consuming a GAP over a match: since we walk the
    # sequence tail-first, taking the gap first (when it's tied with a match) pushes every
    # unmatched rep towards the tail of the alignment and leaves the head fully matched --
    # e.g. gt=[g1,g2], det=[d1,d2,d3] aligns as (g1,d1),(g2,d2),(None,d3) rather than
    # (None,d1),(g1,d2),(g2,d3). Both are equal-cost under this content-independent cost model,
    # but "extras trail" is the deterministic, human-legible convention.
    pairs: list[MatchPair] = []
    i, j = m, n
    while i > 0 or j > 0:
        if j > 0 and dp[i][j] == dp[i][j - 1] + 1:
            pairs.append((None, det_reps[j - 1]))
            j -= 1
        elif i > 0 and dp[i][j] == dp[i - 1][j] + 1:
            pairs.append((gt_reps[i - 1], None))
            i -= 1
        else:
            pairs.append((gt_reps[i - 1], det_reps[j - 1]))
            i, j = i - 1, j - 1
    pairs.reverse()
    return pairs
