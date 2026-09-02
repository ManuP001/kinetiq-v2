#!/usr/bin/env python3
"""
evals/gate0/aggregate.py

Two independent gates live in this script:

1. The original Gate 0 (ADR-110): aggregates JSON exported from kinetiq-demo2's "Export JSON"
   button (results screen) and prints a pass/fail verdict against >90% rep accuracy per exercise,
   plus device x lighting matrix coverage.
       python aggregate.py --data data/

2. The Stage-0 golden-set gate (EVAL_HARNESS_STAGE0_SPEC.md): scores the frozen, committed
   golden/ set for rep-count accuracy, no-phantom-reps, subject-lock, per-flag form
   precision/recall (severity-aware), and view robustness.
       python aggregate.py --golden golden/ --mode fast   # assertions + rep-acc (CI push)
       python aggregate.py --golden golden/ --mode full   # + form P/R + subject-lock + view

See README.md in this directory for both workflows; kinetiq-demo2/README.md is the canonical
source for how --data exports are collected.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from exercise_lib import load_fault_severities
from gate_config import (
    GATE0_TARGET_ACCURACY,
    LIVE_CUE_MAX_WORDS,
    POSE_MODEL_CANDIDATES,
    SUBJECT_LOCK_FLOOR,
    VIEW_ACC_MAX_GAP,
)
from golden_loader import (
    GoldenClip,
    GoldenSetError,
    load_capture_meta,
    load_golden,
    load_golden_poses,
)
from scorers.form_pr import PR, aggregate_form_pr, gate_form_pr
from scorers.phantom import PHANTOM_CLIP_TYPES, score_phantom
from scorers.subject_lock import score_subject_lock
from scorers.view import score_view_robustness

# Gate 0 protocol constants (kinetiq-demo2/README.md "Gate 0 protocol"). These describe the
# *evaluation* protocol for this script, not the app itself, so they live here rather than in
# backend/app/core/config.py.
MIN_SETS_PER_CELL = 3
MIN_REPS_PER_SET = 8
MAX_REPS_PER_SET = 12
MIN_DEVICES = 5
LIGHTING_CONDITIONS = ("daylight", "indoor_evening", "dim_room")

DEVICE_UA_RE = re.compile(r"Android\s+[\d.]+;\s*([^)]+)\)")

# Stage-0 coaching-cue judge stub (EVAL_HARNESS_STAGE0_SPEC.md §10): the calibrated LLM judge for
# semantic cue quality lands in Stage 6 (EVAL_STRATEGY.md §2). Until then, cheap deterministic
# assertions only -- length (LIVE_CUE_MAX_WORDS, imported from config.py) and a minimal banned
# medical-term list. This list is a Stage-0 stopgap, not a clinical term registry.
_BANNED_MEDICAL_TERMS = (
    "injury", "injured", "tear", "torn", "fracture", "rupture", "herniated",
    "impingement", "sprain", "strain", "dislocation", "surgery",
)


def parse_device_label(user_agent: str) -> str:
    """Coarse device label from a raw navigator.userAgent string. Not a precise device DB —
    just enough to group sets by physical device for coverage tracking."""
    m = DEVICE_UA_RE.search(user_agent or "")
    if m:
        return m.group(1).strip()
    return (user_agent or "unknown")[:40]


def load_sessions(data_dir: Path) -> list[dict[str, Any]]:
    sessions: list[dict[str, Any]] = []
    for path in sorted(data_dir.glob("*.json")):
        with path.open(encoding="utf-8") as f:
            payload = json.load(f)
        for rec in payload.get("sessions", []):
            rec = dict(rec)
            rec["_device_label"] = parse_device_label(rec.get("device", ""))
            rec["_lighting"] = rec.get("lighting") or "unspecified"
            rec["_source_file"] = path.name
            sessions.append(rec)
    return sessions


def weighted_accuracy(records: list[dict[str, Any]]) -> float:
    """Same formula the PWA itself uses (index.html renderResults()): a weighted accuracy over
    the whole set of records, not a mean of per-set accuracies."""
    sum_actual = sum(r["actual"] for r in records)
    sum_err = sum(abs(r["detected"] - r["actual"]) for r in records)
    if sum_actual == 0:
        return 1.0
    return max(0.0, 1 - sum_err / sum_actual)


def print_accuracy_verdict(sessions: list[dict[str, Any]]) -> bool:
    by_exercise: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in sessions:
        by_exercise[r["exercise"]].append(r)

    print("=" * 60)
    print("GATE 0 - REP ACCURACY (target: {:.0%})".format(GATE0_TARGET_ACCURACY))
    print("=" * 60)
    all_pass = True
    for exercise in sorted(by_exercise):
        recs = by_exercise[exercise]
        acc = weighted_accuracy(recs)
        passed = acc >= GATE0_TARGET_ACCURACY
        all_pass = all_pass and passed
        status = "PASS" if passed else "FAIL"
        print(f"  {exercise:<10} {acc:>7.1%}  ({len(recs)} sets)  [{status}]")

    overall_acc = weighted_accuracy(sessions) if sessions else 0.0
    overall_pass = overall_acc >= GATE0_TARGET_ACCURACY and bool(sessions)
    all_pass = all_pass and overall_pass
    print("-" * 60)
    print(f"  {'OVERALL':<10} {overall_acc:>7.1%}  ({len(sessions)} sets)  "
          f"[{'PASS' if overall_pass else 'FAIL'}]")
    print()
    return all_pass


def print_matrix_coverage(sessions: list[dict[str, Any]]) -> None:
    by_exercise: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in sessions:
        by_exercise[r["exercise"]].append(r)

    print("=" * 60)
    print("DEVICE x LIGHTING MATRIX COVERAGE")
    print(f"(protocol: >={MIN_DEVICES} devices x {len(LIGHTING_CONDITIONS)} lighting "
          f"conditions, >={MIN_SETS_PER_CELL} sets of {MIN_REPS_PER_SET}-{MAX_REPS_PER_SET} "
          f"reps per cell)")
    print("=" * 60)
    for exercise in sorted(by_exercise):
        recs = by_exercise[exercise]
        devices = sorted({r["_device_label"] for r in recs})
        print(f"\n  {exercise} - {len(devices)} device(s) seen "
              f"({'OK' if len(devices) >= MIN_DEVICES else 'NEEDS MORE'})")
        cells: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for r in recs:
            cells[(r["_device_label"], r["_lighting"])].append(r)
        for device in devices:
            for lighting in LIGHTING_CONDITIONS:
                cell = cells.get((device, lighting), [])
                in_range = [
                    r for r in cell if MIN_REPS_PER_SET <= r["actual"] <= MAX_REPS_PER_SET
                ]
                ok = len(in_range) >= MIN_SETS_PER_CELL
                marker = "OK" if ok else f"needs {MIN_SETS_PER_CELL - len(in_range)} more"
                print(f"    {device:<20} {lighting:<15} {len(in_range)} valid set(s)  [{marker}]")
        stray_lighting = {l for (_, l) in cells if l not in LIGHTING_CONDITIONS}
        if stray_lighting:
            print(f"    (unrecognised/unspecified lighting values seen: "
                  f"{', '.join(sorted(stray_lighting))} - re-export from an updated demo2 build)")
    print()


class CueAssertionResult:
    """Stage-0 stub result for the coaching-cue judge (see _BANNED_MEDICAL_TERMS above)."""

    def __init__(self) -> None:
        self.checked = 0
        self.failures: list[str] = []

    @property
    def passed(self) -> bool:
        return not self.failures


def check_coaching_cue_assertions(clips: list[GoldenClip]) -> CueAssertionResult:
    """Cheap, deterministic assertions standing in for the Stage-6 calibrated LLM judge
    (EVAL_HARNESS_STAGE0_SPEC.md §10): cue length and a banned-term list. Not semantic quality --
    that needs a judge calibrated against hand-graded cues (EVAL_STRATEGY.md §2), which is out of
    scope for Stage 0."""
    result = CueAssertionResult()
    for clip in clips:
        for cue in clip.coaching_cues:
            result.checked += 1
            text = cue.get("text", "")
            word_count = len(text.split())
            if word_count > LIVE_CUE_MAX_WORDS:
                result.failures.append(
                    f"{clip.clip_id} rep {cue.get('rep_idx')}: {word_count} words "
                    f"(max {LIVE_CUE_MAX_WORDS}): {text!r}"
                )
            lowered = text.lower()
            hit = next((term for term in _BANNED_MEDICAL_TERMS if term in lowered), None)
            if hit:
                result.failures.append(
                    f"{clip.clip_id} rep {cue.get('rep_idx')}: contains medical term "
                    f"{hit!r}: {text!r}"
                )
    return result


def print_stage0_report(clips: list[GoldenClip], mode: str) -> bool:
    """Legible pass/fail table over the golden set (EVAL_HARNESS_STAGE0_SPEC.md §7): accuracy by
    exercise, per-flag precision/recall, phantom/subject-lock pass-fail. Returns whether every
    checked dimension is above its floor."""
    all_pass = True

    print("=" * 70)
    print(f"STAGE 0 GOLDEN SET REPORT  (mode: {mode})")
    print("=" * 70)

    # --- rep-count accuracy (every clip with a real rep count -- phantom_bench/phantom_empty
    # are 0 reps by construction and are graded by the no-phantom-reps gate below instead;
    # bystander is NOT phantom-like (EVAL_HARNESS_STAGE0_SPEC.md §5/§7) and belongs here, same
    # as a 'normal' clip) ---
    rep_counted_clips = [c for c in clips if c.clip_type not in PHANTOM_CLIP_TYPES]
    by_exercise: dict[str, list[GoldenClip]] = defaultdict(list)
    for c in rep_counted_clips:
        by_exercise[c.exercise].append(c)

    print(f"\n-- Rep-count accuracy (target {GATE0_TARGET_ACCURACY:.0%}) --")
    if not rep_counted_clips:
        print("  (no rep-counted clips in golden set)")
    for exercise in sorted(by_exercise):
        recs = [{"actual": c.actual_reps, "detected": c.detected_reps} for c in by_exercise[exercise]]
        acc = weighted_accuracy(recs)
        passed = acc >= GATE0_TARGET_ACCURACY
        all_pass = all_pass and passed
        print(f"  {exercise:<18} {acc:>7.1%}  ({len(recs)} clip(s))  [{'PASS' if passed else 'FAIL'}]")

    # --- no-phantom-reps ---
    phantom_result = score_phantom(clips)
    print(f"\n-- No-phantom-reps (clip types: {', '.join(PHANTOM_CLIP_TYPES)}) --")
    print(f"  checked {phantom_result.checked} clip(s)  "
          f"[{'PASS' if phantom_result.passed else 'FAIL'}]")
    for clip_id in phantom_result.failures:
        print(f"    FAIL: {clip_id} produced a nonzero rep count")
    all_pass = all_pass and phantom_result.passed

    # --- coaching-cue assertions (Stage-0 judge stub) ---
    cue_result = check_coaching_cue_assertions(clips)
    print("\n-- Coaching-cue assertions (Stage-0 stub; calibrated judge lands in Stage 6) --")
    print(f"  checked {cue_result.checked} cue(s)  [{'PASS' if cue_result.passed else 'FAIL'}]")
    for reason in cue_result.failures:
        print(f"    FAIL: {reason}")
    all_pass = all_pass and cue_result.passed

    if mode == "full":
        # --- form precision/recall, per flag, severity-gated ---
        severities = load_fault_severities()
        gated = gate_form_pr(aggregate_form_pr(clips), severities)
        print("\n-- Form precision/recall (per flag, severity-gated) --")
        if not gated or not any(gated.values()):
            print("  (no flags observed on any 'normal' clip)")
        for exercise in sorted(gated):
            if not gated[exercise]:
                continue
            print(f"  {exercise}:")
            for flag in sorted(gated[exercise]):
                g = gated[exercise][flag]
                p_str = f"{g.precision:.0%}" if g.precision is not None else "n/a"
                r_str = f"{g.recall:.0%}" if g.recall is not None else "n/a"
                pf_str = f"{g.precision_floor:.0%}" if g.precision_floor is not None else "-"
                rf_str = f"{g.recall_floor:.0%}" if g.recall_floor is not None else "-"
                if g.severity == "low":
                    status = "advisory"
                else:
                    status = "PASS" if g.passed else "FAIL"
                    all_pass = all_pass and g.passed
                print(f"    {flag:<22} sev={g.severity:<5} tp={g.tp} fp={g.fp} fn={g.fn}  "
                      f"precision={p_str:>5} (floor {pf_str})  "
                      f"recall={r_str:>5} (floor {rf_str})  [{status}]")

        # --- insufficient evidence (Stage 3, SPRINT.md G2): surfaced, never silently dropped.
        # A sustained flag with too few visibility-passing frames to judge either way -- doesn't
        # count as a false accusation OR a miss in the P/R table above, but isn't nothing either.
        insufficient_counts: dict[str, int] = defaultdict(int)
        for clip in clips:
            for rep in clip.det_reps:
                for flag in rep.get("insufficient_evidence", []):
                    insufficient_counts[flag] += 1
        if insufficient_counts:
            print("\n-- Insufficient evidence (sustained flag, too few visible frames to judge) --")
            for flag in sorted(insufficient_counts):
                print(f"    {flag:<22} {insufficient_counts[flag]} rep(s)")

        # --- subject-lock ---
        lock_result = score_subject_lock(clips)
        print(f"\n-- Subject-lock (floor {SUBJECT_LOCK_FLOOR:.0%}) --")
        if not lock_result.per_clip:
            print("  (no multi-person clips in golden set)")
        else:
            for clip_id in sorted(lock_result.per_clip):
                print(f"    {clip_id:<28} {lock_result.per_clip[clip_id]:.1%}")
            lock_pass = lock_result.passed(SUBJECT_LOCK_FLOOR)
            print(f"  mean {lock_result.mean:.1%}  [{'PASS' if lock_pass else 'FAIL'}]")
            all_pass = all_pass and lock_pass

        # --- view robustness ---
        view_results = score_view_robustness(clips)
        print(f"\n-- View robustness (max gap {VIEW_ACC_MAX_GAP:.0%}) --")
        if not view_results:
            print("  (no clips with a labeled view in golden set)")
        for exercise in sorted(view_results):
            vr = view_results[exercise]
            views_str = ", ".join(f"{v}={a:.1%}" for v, a in sorted(vr.accuracy_by_view.items()))
            gap = vr.gap
            gap_str = f"{gap:.1%}" if gap is not None else "n/a"
            passed = vr.passed(VIEW_ACC_MAX_GAP)
            all_pass = all_pass and passed
            print(f"  {exercise:<18} {views_str}  gap={gap_str}  [{'PASS' if passed else 'FAIL'}]")

    print()
    print(f"Stage 0 gate: {'PASS' if all_pass else 'FAIL'}")
    return all_pass


def _pool_form_pr(per_exercise: dict[str, dict[str, PR]]) -> PR:
    """Micro-averaged precision/recall across every flag and exercise -- one pooled number per
    pose model for the bake-off table's single row, rather than --mode full's per-flag
    breakdown. Ch 39 still applies at the per-dimension level (this is one dimension of several
    columns, not the only number that matters)."""
    total = PR()
    for flags in per_exercise.values():
        for pr in flags.values():
            total.tp += pr.tp
            total.fp += pr.fp
            total.fn += pr.fn
    return total


def _fmt_pct(value: float | None) -> str:
    return f"{value:.1%}" if value is not None else "n/a"


def print_pose_model_comparison(golden_dir: Path) -> bool:
    """Stage 2 (VISION_ARCHITECTURE.md Stage 2, ROADMAP.md Stage 2): runs the Stage-1 detector
    once per candidate pose model (gate_config.POSE_MODEL_CANDIDATES) over golden/poses/<model>/,
    and prints ONE multi-dimensional comparison table. Ch 39: "a single climbing number can hide
    a collapsing one" -- every dimension is printed, none dropped, and no winner is picked here;
    that's a human reading real numbers once GOLDEN_SET_PROTOCOL.md §8's clips exist. Returns
    False only on a hard failure (a malformed golden set) -- a candidate with zero clips, or one
    model scoring worse than another, is not a failure of this tool."""
    print("=" * 100)
    print("STAGE 2 POSE-MODEL BAKE-OFF")
    print("=" * 100)

    rows: list[dict] = []
    any_clips = False
    for candidate in POSE_MODEL_CANDIDATES:
        pose_model = candidate["name"]
        try:
            clips = load_golden_poses(golden_dir, pose_model)
        except GoldenSetError as exc:
            print(f"error: {pose_model}: {exc}", file=sys.stderr)
            return False

        if not clips:
            rows.append({"pose_model": pose_model, "clips": 0})
            continue
        any_clips = True

        rep_counted = [c for c in clips if c.clip_type not in PHANTOM_CLIP_TYPES]
        rep_acc = (
            weighted_accuracy(
                [{"actual": c.actual_reps, "detected": c.detected_reps} for c in rep_counted]
            )
            if rep_counted else None
        )
        phantom_result = score_phantom(clips)
        lock_result = score_subject_lock(clips)
        pooled = _pool_form_pr(aggregate_form_pr(clips))

        latencies = [
            meta["avg_latency_ms_per_frame"]
            for clip in clips
            if (meta := load_capture_meta(golden_dir, pose_model, clip.clip_id))
            and meta.get("avg_latency_ms_per_frame") is not None
        ]

        rows.append({
            "pose_model": pose_model,
            "clips": len(clips),
            "rep_acc": rep_acc,
            "phantom_checked": phantom_result.checked,
            "phantom_pass": phantom_result.passed,
            "subject_lock": lock_result.mean,
            "precision": pooled.precision,
            "recall": pooled.recall,
            "latency_ms": sum(latencies) / len(latencies) if latencies else None,
            "size_mb": candidate.get("approx_size_mb"),
        })

    cols = ("model", "clips", "rep-acc", "phantom", "sub-lock", "precision", "recall", "latency", "size")
    widths = (18, 6, 9, 9, 9, 10, 8, 16, 8)
    header = "".join(c.ljust(w) for c, w in zip(cols, widths))
    print(header)
    print("-" * len(header))
    for row in rows:
        if row["clips"] == 0:
            print(
                f"{row['pose_model']:<18}{'0':<6}"
                f"(no golden/poses/{row['pose_model']}/ clips yet -- GOLDEN_SET_PROTOCOL.md §8)"
            )
            continue
        phantom_s = "n/a" if row["phantom_checked"] == 0 else ("PASS" if row["phantom_pass"] else "FAIL")
        latency_s = f"{row['latency_ms']:.1f}ms" if row["latency_ms"] is not None else "n/a (synthetic)"
        size_s = f"{row['size_mb']:.1f}MB" if row["size_mb"] is not None else "n/a"
        values = (
            row["pose_model"], str(row["clips"]), _fmt_pct(row["rep_acc"]), phantom_s,
            _fmt_pct(row["subject_lock"]), _fmt_pct(row["precision"]), _fmt_pct(row["recall"]),
            latency_s, size_s,
        )
        print("".join(v.ljust(w) for v, w in zip(values, widths)))

    print()
    if not any_clips:
        print("No golden/poses/<model>/ clips exist for any candidate yet -- expected until")
        print("GOLDEN_SET_PROTOCOL.md §8's bake-off-minimum clips are recorded. This table is the")
        print("tooling; the real verdict is deferred to when that data exists.")
    else:
        print("Read the table; this tool does not pick a winner (Ch 39: model selection is")
        print("measurement, not a debate -- see gate0/README.md's bake-off section).")
    return True


def run_data(data_dir: Path) -> int:
    """The original --data path (ADR-110), unchanged in behaviour."""
    if not data_dir.is_dir():
        print(f"error: {data_dir} is not a directory", file=sys.stderr)
        return 2

    sessions = load_sessions(data_dir)
    if not sessions:
        print(f"No session records found in {data_dir}. Export JSON from kinetiq-demo2's "
              f"results screen and drop the files here.")
        return 1

    accuracy_pass = print_accuracy_verdict(sessions)
    print_matrix_coverage(sessions)

    if not accuracy_pass:
        print("Gate 0: NOT PASSING - rep accuracy below the 90% bar on at least one exercise.")
    else:
        print("Gate 0 rep-accuracy bar met. Confirm matrix coverage above before declaring the "
              "gate passed - accuracy alone isn't sufficient without device/lighting breadth.")

    return 0 if accuracy_pass else 1


def run_golden(golden_dir: Path, mode: str) -> int:
    """The Stage-0 golden-set path (EVAL_HARNESS_STAGE0_SPEC.md)."""
    if not golden_dir.is_dir():
        print(f"error: {golden_dir} is not a directory", file=sys.stderr)
        return 2

    try:
        clips = load_golden(golden_dir)
    except GoldenSetError as exc:
        print(f"error: golden set failed validation: {exc}", file=sys.stderr)
        return 2

    if not clips:
        print(f"No clips found in {golden_dir} (check MANIFEST.json).", file=sys.stderr)
        return 1

    return 0 if print_stage0_report(clips, mode) else 1


def run_compare_pose_models(golden_dir: Path) -> int:
    """Stage 2's --compare-pose-models path (VISION_ARCHITECTURE.md Stage 2)."""
    if not golden_dir.is_dir():
        print(f"error: {golden_dir} is not a directory", file=sys.stderr)
        return 2

    return 0 if print_pose_model_comparison(golden_dir) else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data", type=Path, default=None,
        help="Directory of exported Gate 0 JSON files (default: ./data). Ignored if --golden "
             "is given.",
    )
    parser.add_argument(
        "--golden", type=Path, default=None,
        help="Directory of the frozen Stage-0 golden set (MANIFEST.json + per-clip "
             "labels/keypoints/detected). See EVAL_HARNESS_STAGE0_SPEC.md.",
    )
    parser.add_argument(
        "--mode", choices=["fast", "full"], default="fast",
        help="Golden-set gate depth: fast = assertions + rep-acc (CI push); full = + form P/R "
             "+ subject-lock + view (CI merge/nightly). Only applies with --golden.",
    )
    parser.add_argument(
        "--compare-pose-models", action="store_true",
        help="Stage 2: run the detector once per candidate pose model over "
             "golden/poses/<model>/ and print a comparison table (rep-acc, no-phantom-reps, "
             "subject-lock, form precision/recall, latency, size). Requires --golden; ignores "
             "--mode. Prints, never picks a winner.",
    )
    args = parser.parse_args()

    if args.compare_pose_models:
        if args.golden is None:
            print("error: --compare-pose-models requires --golden", file=sys.stderr)
            return 2
        return run_compare_pose_models(args.golden)
    if args.golden is not None:
        return run_golden(args.golden, args.mode)
    return run_data(args.data or Path(__file__).parent / "data")


if __name__ == "__main__":
    raise SystemExit(main())
