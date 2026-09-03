#!/usr/bin/env python3
"""
evals/gate0/effectiveness_report.py

Step 3 of the live-vision-prototype build: turns one kinetiq-demo3 session export + a trainer's
filled fault labels into a single effectiveness read -- rep-accuracy plus form precision/recall
and insufficient-evidence counts, via the SAME scorers the golden-set gate uses
(scorers/form_pr.py), on the SAME pipeline (labeling/export.py -> labeling/validate.py ->
golden_loader.load_golden_poses). Nothing here is a new scoring rule; this is glue over what
already exists, not a reimplementation of any of it.

Also runs a parity check: the bundle's <clip_id>.detected.json (what the live app displayed,
built from prototype_api's per-call AssessResponse.reps) against a fresh OFFLINE run_detector()
recompute over the bundle's own <clip_id>.keypoints.jsonl -- the exact recompute golden_loader.py
always does for a Stage-1-scoped exercise (squat/pushup/lunge). These SHOULD be byte-identical --
same deterministic algorithm, same input frames -- so a mismatch means a client/API buffer desync
(a dropped or reordered batch), not a scoring disagreement between two valid readings. Flagged,
never hidden; the report's numbers always come from the offline recompute (authoritative)
regardless of whether parity holds.

Trainer sign-off gate: a bundle's clips_template.csv carries pt_verified (GOLDEN_SET_PROTOCOL.md's
existing "Freeze" step -- PT sign-off before a case is trusted). Faults are a HUMAN judgment call
this tool never fabricates: by default it refuses to score a clip whose pt_verified is still
false, since reps_template.csv having blank faults is indistinguishable between "clean set,
trainer confirmed" and "trainer hasn't looked yet" -- only pt_verified tells them apart.
--allow-unverified overrides this (previews, tests) but never silently skips the check.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List

from aggregate import weighted_accuracy
from detector.adapter import run_detector
from exercise_lib import load_fault_severities
from golden_loader import GoldenSetError, load_golden_poses
from labeling.csv_schema import LabelExportError, parse_bool
from labeling.export import export_labels, read_clip_rows
from labeling.validate import validate_golden_set
from scorers.form_pr import aggregate_form_pr, gate_form_pr, insufficient_evidence_counts

CAVEAT = """\
================================================================================
PROTOTYPE EFFECTIVENESS READ -- NOT THE POSE-MODEL BAKE-OFF VERDICT
  - Small n: one session, not a golden set. EXERCISE_LIBRARY.md §5's precision/recall floors
    need real per-flag coverage to mean anything -- a single clip's P/R is a data point, not a
    verdict on the detector.
  - Single-user BlazePose only (numPoses: 1). Bench/bystander subject-lock is NOT exercised here
    at all -- ADR-300's multi-person requirement is scoped to the offline bake-off tooling, not
    this live single-user prototype.
  - Coaching cues are the interim, non-Stage-6 layer (prototype_api/cues.py) -- not evaluated
    here at all.
  - These numbers are only real for a REAL camera session. A stubbed/synthetic (e.g. a Playwright
    test run) exercises the app's plumbing, not real-world detection accuracy -- never read a
    synthetic run's numbers as an effectiveness result.
================================================================================
"""


def _clip_row(bundle_dir: Path) -> Dict[str, Any]:
    rows = read_clip_rows(bundle_dir / "clips_template.csv")
    if len(rows) != 1:
        raise SystemExit(
            f"error: {bundle_dir / 'clips_template.csv'} must have exactly 1 clip row, "
            f"found {len(rows)} -- a bundle is one session, one clip"
        )
    return rows[0]


def _keypoints_path(bundle_dir: Path, clip_id: str) -> Path:
    path = bundle_dir / f"{clip_id}.keypoints.jsonl"
    if not path.is_file():
        raise SystemExit(f"error: {path} not found in bundle directory")
    return path


def _pose_model_of(keypoints_path: Path) -> str:
    with keypoints_path.open(encoding="utf-8") as f:
        first_line = f.readline()
    return json.loads(first_line)["pose_model"]


def _load_bundle_detected(bundle_dir: Path, clip_id: str) -> Dict[str, Any]:
    path = bundle_dir / f"{clip_id}.detected.json"
    if not path.is_file():
        raise SystemExit(f"error: {path} not found in bundle directory")
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def check_parity(bundle_dir: Path, clip_id: str, exercise: str) -> List[str]:
    """Returns a list of human-readable mismatch descriptions; empty means parity holds. Compares
    only idx/flags/insufficient_evidence -- the bundle's detected.json never carried form_score
    (prototype_api's AssessResponse doesn't compute it; see kinetiq-demo3/README.md), so that
    field is intentionally not part of this comparison."""
    keypoints_path = _keypoints_path(bundle_dir, clip_id)
    with keypoints_path.open(encoding="utf-8") as f:
        frames = [json.loads(line) for line in f if line.strip()]

    fresh = run_detector(frames, exercise)
    fresh_reps = {
        r.idx: {"flags": r.flags, "insufficient_evidence": r.insufficient_evidence}
        for r in fresh.reps
    }

    bundle = _load_bundle_detected(bundle_dir, clip_id)
    bundle_reps = {
        r["idx"]: {"flags": r["flags"], "insufficient_evidence": r["insufficient_evidence"]}
        for r in bundle.get("reps", [])
    }

    mismatches: List[str] = []
    if bundle.get("detected_reps") != fresh.detected_reps:
        mismatches.append(
            f"detected_reps: bundle(live)={bundle.get('detected_reps')!r} "
            f"offline-recompute={fresh.detected_reps!r}"
        )
    for idx in sorted(set(bundle_reps) | set(fresh_reps)):
        b, o = bundle_reps.get(idx), fresh_reps.get(idx)
        if b != o:
            mismatches.append(f"rep {idx}: bundle(live)={b!r} offline-recompute={o!r}")
    return mismatches


def build_golden_set(bundle_dir: Path, golden_dir: Path, clip_id: str, pose_model: str) -> None:
    """The PROVEN path (labeling/export.py -> labeling/validate.py), called as a library, not
    reimplemented. Places the bundle's keypoints.jsonl at
    golden_dir/poses/<pose_model>/<clip_id>.keypoints.jsonl, which load_golden_poses() requires;
    merges into any existing MANIFEST.json rather than clobbering other clips already there."""
    try:
        export_labels(
            bundle_dir / "clips_template.csv", bundle_dir / "reps_template.csv", golden_dir
        )
    except LabelExportError as exc:
        raise SystemExit(f"error: labeling export failed: {exc}")

    poses_dir = golden_dir / "poses" / pose_model
    poses_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(
        _keypoints_path(bundle_dir, clip_id), poses_dir / f"{clip_id}.keypoints.jsonl"
    )

    report = validate_golden_set(golden_dir)
    print(report.format())
    if not report.ok:
        raise SystemExit(
            "error: labeling validate found issues (above) -- fix clips_template.csv / "
            "reps_template.csv and re-run. (Did the trainer actually fill in "
            "reps_template.csv's faults column with real error_ids?)"
        )


def print_report(bundle_dir: Path, golden_dir: Path, allow_unverified: bool) -> int:
    clip_row = _clip_row(bundle_dir)
    clip_id, exercise = clip_row["clip_id"], clip_row["exercise"]
    keypoints_path = _keypoints_path(bundle_dir, clip_id)
    pose_model = _pose_model_of(keypoints_path)

    print(CAVEAT)
    print(f"clip_id: {clip_id}    exercise: {exercise}    pose_model: {pose_model}\n")

    print("-- Parity check: live app's detected.json vs. offline run_detector() recompute --")
    mismatches = check_parity(bundle_dir, clip_id, exercise)
    if mismatches:
        print("  FAIL -- the live session and the offline recompute disagree. This means a "
              "client/API buffer mismatch (e.g. a dropped or reordered batch), not a scoring "
              "disagreement. The numbers below use the offline recompute (authoritative), not "
              "the live snapshot:")
        for m in mismatches:
            print(f"    {m}")
    else:
        print("  PASS -- live session and offline recompute agree exactly.")

    pt_verified = parse_bool(clip_row.get("pt_verified", "false"), context=f"{clip_id} pt_verified")
    if not pt_verified and not allow_unverified:
        print(
            f"\nerror: clips_template.csv says pt_verified=false for {clip_id!r}. Faults are a "
            f"human judgment call this tool never fabricates -- blank faults in "
            f"reps_template.csv could mean 'clean set, trainer confirmed' or 'trainer hasn't "
            f"reviewed it yet', and only pt_verified tells those apart.\n"
            f"  -> Have the trainer review reps_template.csv's faults column (semicolon-"
            f"separated error_ids from exercises/{exercise}.json, blank = clean rep), set "
            f"pt_verified=true in clips_template.csv once they have, then re-run.\n"
            f"  -> Or pass --allow-unverified for a preview read (never treat its P/R numbers "
            f"as a real result).",
            file=sys.stderr,
        )
        return 2

    print()
    build_golden_set(bundle_dir, golden_dir, clip_id, pose_model)

    try:
        clips = [c for c in load_golden_poses(golden_dir, pose_model) if c.clip_id == clip_id]
    except GoldenSetError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not clips:
        print(
            f"error: {clip_id} did not load from {golden_dir} after export -- unexpected given "
            f"validate passed above", file=sys.stderr,
        )
        return 2
    clip = clips[0]

    acc = weighted_accuracy([{"actual": clip.actual_reps, "detected": clip.detected_reps}])
    print("\n-- Rep-accuracy --")
    print(f"  detected={clip.detected_reps}  actual={clip.actual_reps}  accuracy={acc:.1%}")

    severities = load_fault_severities()
    gated = gate_form_pr(aggregate_form_pr(clips), severities)
    print("\n-- Form precision/recall (per flag, severity-gated) --")
    if not gated.get(exercise):
        print("  (no faults labeled or detected on this clip)")
    else:
        for flag in sorted(gated[exercise]):
            g = gated[exercise][flag]
            p_str = f"{g.precision:.0%}" if g.precision is not None else "n/a"
            r_str = f"{g.recall:.0%}" if g.recall is not None else "n/a"
            pf_str = f"{g.precision_floor:.0%}" if g.precision_floor is not None else "-"
            rf_str = f"{g.recall_floor:.0%}" if g.recall_floor is not None else "-"
            status = (
                "advisory" if g.severity == "low" else ("meets floor" if g.passed else "below floor")
            )
            print(
                f"  {flag:<22} sev={g.severity:<5} tp={g.tp} fp={g.fp} fn={g.fn}  "
                f"precision={p_str:>5} (floor {pf_str})  recall={r_str:>5} (floor {rf_str})  "
                f"[{status}]"
            )

    insufficient = insufficient_evidence_counts(clips)
    if insufficient:
        print("\n-- Insufficient evidence (sustained flag, too few visible frames to judge) --")
        for flag in sorted(insufficient):
            print(f"    {flag:<22} {insufficient[flag]} rep(s)")

    print(
        f"\nWrote/updated {golden_dir} (MANIFEST.json, {clip_id}.labels.json, "
        f"poses/{pose_model}/{clip_id}.keypoints.jsonl) -- re-run "
        f"`aggregate.py --golden {golden_dir} --mode full` directly on this directory too, "
        f"and it'll pick up this clip alongside anything else already there."
    )

    return 0 if not mismatches else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--bundle-dir", type=Path, required=True,
        help="Extracted kinetiq-demo3 export .zip: <clip_id>.keypoints.jsonl, "
             "<clip_id>.detected.json, clips_template.csv, reps_template.csv "
             "(both trainer-reviewed -- pt_verified=true in clips_template.csv).",
    )
    parser.add_argument(
        "--golden", type=Path, required=True,
        help="golden/ working directory to write labels.json/MANIFEST.json/poses/<model>/"
             "keypoints.jsonl into (created if missing; merges with clips already there rather "
             "than clobbering them).",
    )
    parser.add_argument(
        "--allow-unverified", action="store_true",
        help="Score even if clips_template.csv's pt_verified is false. For a preview only -- "
             "never treat the resulting P/R numbers as a real effectiveness result.",
    )
    args = parser.parse_args()

    if not args.bundle_dir.is_dir():
        print(f"error: {args.bundle_dir} is not a directory", file=sys.stderr)
        return 2

    return print_report(args.bundle_dir, args.golden, args.allow_unverified)


if __name__ == "__main__":
    raise SystemExit(main())
