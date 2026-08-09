#!/usr/bin/env python3
"""
evals/gate0/aggregate.py

Aggregates the JSON files exported from kinetiq-demo2's "Export JSON" button (results screen)
and prints a Gate 0 pass/fail verdict (ADR-110): >90% rep accuracy per exercise, plus device x
lighting matrix coverage against the protocol (>=5 real mid-range Android devices x 3 lighting
conditions, >=3 sets of 8-12 reps per cell).

See README.md in this directory for the full protocol; kinetiq-demo2/README.md is the canonical
source for how the data is collected.

Usage:
    python aggregate.py --data data/
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

# Import the shared target-accuracy constant from the backend config so this script and the
# backend never disagree on the Gate 0 bar. No pyproject.toml/packaging exists yet in this repo,
# so a small sys.path insert is the pragmatic option here over duplicating the literal — revisit
# once the backend has real package structure.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from app.core.config import GATE0_TARGET_ACCURACY  # noqa: E402

# Gate 0 protocol constants (kinetiq-demo2/README.md "Gate 0 protocol"). These describe the
# *evaluation* protocol for this script, not the app itself, so they live here rather than in
# backend/app/core/config.py.
MIN_SETS_PER_CELL = 3
MIN_REPS_PER_SET = 8
MAX_REPS_PER_SET = 12
MIN_DEVICES = 5
LIGHTING_CONDITIONS = ("daylight", "indoor_evening", "dim_room")

DEVICE_UA_RE = re.compile(r"Android\s+[\d.]+;\s*([^)]+)\)")


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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data", type=Path, default=Path(__file__).parent / "data",
        help="Directory of exported Gate 0 JSON files (default: ./data)",
    )
    args = parser.parse_args()

    if not args.data.is_dir():
        print(f"error: {args.data} is not a directory", file=sys.stderr)
        return 2

    sessions = load_sessions(args.data)
    if not sessions:
        print(f"No session records found in {args.data}. Export JSON from kinetiq-demo2's "
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


if __name__ == "__main__":
    raise SystemExit(main())
