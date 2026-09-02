#!/usr/bin/env python3
"""
evals/gate0/labeling/cli.py

Command-line entry point for the record -> label -> export -> validate -> score workflow
(GOLDEN_SET_PROTOCOL.md §7):

    python -m labeling templates --out-dir label_work/
        # writes label_work/clips_template.csv + reps_template.csv (header only).

    python -m labeling templates --list-faults squat
        # prints squat's valid error_ids, straight from exercises/squat.json -- what a PT is
        # allowed to type into the reps template's `faults` column.

    python -m labeling export --clips label_work/clips_template.csv \
        --reps label_work/reps_template.csv --golden golden/
        # writes golden/<clip_id>.labels.json per clip row + merges golden/MANIFEST.json.

    python -m labeling validate --golden golden/
        # the same checks CI runs; exits non-zero and prints every issue if any clip is wrong.

Run from evals/gate0/ (so `exercise_lib`, `gate_config`, `golden_loader`, `aggregate` resolve).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from labeling.export import export_labels
from labeling.templates import fault_ids_by_exercise, format_fault_ids, write_templates
from labeling.validate import validate_golden_set


def _cmd_templates(out_dir: Optional[Path], list_faults: Optional[str]) -> int:
    if list_faults:
        print(format_fault_ids(list_faults))
        return 0
    if out_dir is None:
        print("error: --out-dir is required (or use --list-faults)", file=sys.stderr)
        return 2
    clips_path, reps_path = write_templates(out_dir)
    print(f"wrote {clips_path}")
    print(f"wrote {reps_path}")
    known = sorted(fault_ids_by_exercise())
    print(f"Fill both, then run `python -m labeling export`. Exercises: {known} "
          f"(see --list-faults <exercise> for valid fault ids).")
    return 0


def _cmd_export(clips: Path, reps: Path, golden: Path) -> int:
    from labeling.csv_schema import LabelExportError

    try:
        written = export_labels(clips, reps, golden)
    except LabelExportError as exc:
        print(f"export error: {exc}", file=sys.stderr)
        return 2
    for path in written:
        print(f"wrote {path}")
    print(f"updated {Path(golden) / 'MANIFEST.json'}")
    print("Run `python -m labeling validate --golden "
          f"{golden}` next.")
    return 0


def _cmd_validate(golden: Path) -> int:
    report = validate_golden_set(golden)
    print(report.format())
    return 0 if report.ok else 1


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command")

    p_templates = sub.add_parser("templates", help="Write blank CSV templates / list fault ids.")
    p_templates.add_argument("--out-dir", type=Path, help="Directory to write the templates into.")
    p_templates.add_argument("--list-faults", help="Print valid error_ids for this exercise.")

    p_export = sub.add_parser("export", help="CSV templates -> labels.json + MANIFEST.json.")
    p_export.add_argument("--clips", type=Path, required=True, help="Filled clips_template.csv.")
    p_export.add_argument("--reps", type=Path, required=True, help="Filled reps_template.csv.")
    p_export.add_argument("--golden", type=Path, default=Path("golden"), help="golden/ to write into.")

    p_validate = sub.add_parser("validate", help="Validate a golden/ directory; CI-reusable.")
    p_validate.add_argument("--golden", type=Path, default=Path("golden"), help="golden/ to validate.")

    args = parser.parse_args(argv)

    if args.command == "templates":
        return _cmd_templates(args.out_dir, args.list_faults)
    if args.command == "export":
        return _cmd_export(args.clips, args.reps, args.golden)
    if args.command == "validate":
        return _cmd_validate(args.golden)

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
