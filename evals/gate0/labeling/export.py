#!/usr/bin/env python3
"""
evals/gate0/labeling/export.py

Converts a PT's filled CSV templates (labeling/templates.py) into per-clip
`<clip_id>.labels.json` (EVAL_HARNESS_STAGE0_SPEC.md §5) and merges each clip's row into
`golden/MANIFEST.json` (§4). Deliberately mechanical: this module only reshapes CSV rows into the
schema's JSON shape and enforces CSV-structural integrity (a required column, a well-formed
integer, no duplicate clip_id/rep_idx) -- it does NOT check domain rules like "does this fault id
exist" or "does a phantom clip really have zero reps". That's labeling/validate.py's job
(run it right after export, or via CI) -- keeping the two separate means a CSV that's merely
malformed and a clip that's well-formed-but-wrong fail with different, clearer messages.

Privacy invariant (GOLDEN_SET_PROTOCOL.md §1): writes only labels.json + MANIFEST.json under
golden_dir -- never touches or references a video file.
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from labeling.csv_schema import (
    CLIP_COLUMNS,
    LabelExportError,
    REP_COLUMNS,
    clip_row_get,
    parse_bool,
    parse_faults,
    parse_int,
    require_columns,
)

MANIFEST_FILENAME = "MANIFEST.json"
SCHEMA_VERSION = 1


def _read_csv_dicts(path: Path) -> List[Dict[str, Any]]:
    with Path(path).open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader), reader.fieldnames


def read_clip_rows(path: Path) -> List[Dict[str, Any]]:
    rows, fieldnames = _read_csv_dicts(path)
    require_columns(fieldnames, CLIP_COLUMNS, context=str(path))
    seen_ids: set[str] = set()
    for row in rows:
        clip_id = clip_row_get(row, "clip_id", clip_id="?")
        if not clip_id:
            raise LabelExportError(f"{path}: a row is missing clip_id")
        if clip_id in seen_ids:
            raise LabelExportError(f"{path}: duplicate clip_id {clip_id!r}")
        seen_ids.add(clip_id)
    return rows


def read_rep_rows(path: Path) -> List[Dict[str, Any]]:
    rows, fieldnames = _read_csv_dicts(path)
    require_columns(fieldnames, REP_COLUMNS, context=str(path))
    return rows


def _build_reps(clip_id: str, rep_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    reps: List[Dict[str, Any]] = []
    seen_idx: set[int] = set()
    for row in rep_rows:
        rep_idx = parse_int(row.get("rep_idx", ""), context=f"{clip_id} rep row")
        if rep_idx in seen_idx:
            raise LabelExportError(f"{clip_id}: duplicate rep_idx {rep_idx}")
        seen_idx.add(rep_idx)
        faults = parse_faults(row.get("faults", ""))
        reps.append({"idx": rep_idx, "faults": faults})
    reps.sort(key=lambda r: r["idx"])
    return reps


def build_clip_labels(clip_row: Dict[str, Any], rep_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Builds one clip's labels.json dict (EVAL_HARNESS_STAGE0_SPEC.md §5 shape) from its
    clip-level row plus every rep-level row that names the same clip_id."""
    clip_id = clip_row_get(clip_row, "clip_id", clip_id="?")
    if not clip_id:
        raise LabelExportError("clip row is missing clip_id")

    exercise = clip_row_get(clip_row, "exercise", clip_id=clip_id)
    clip_type = clip_row_get(clip_row, "clip_type", clip_id=clip_id)
    if not exercise:
        raise LabelExportError(f"{clip_id}: missing required column exercise")
    if not clip_type:
        raise LabelExportError(f"{clip_id}: missing required column clip_type")

    view = clip_row_get(clip_row, "view", clip_id=clip_id)
    lighting = clip_row_get(clip_row, "lighting", clip_id=clip_id)
    fitness_level = clip_row_get(clip_row, "fitness_level", clip_id=clip_id)

    actual_reps = parse_int(clip_row.get("actual_reps", ""), context=f"{clip_id} actual_reps")
    num_people_in_frame = parse_int(
        clip_row.get("num_people_in_frame", ""), context=f"{clip_id} num_people_in_frame"
    )
    subject_track_id = parse_int(
        clip_row.get("subject_track_id", ""),
        context=f"{clip_id} subject_track_id",
        required=False,
    )

    labeler = clip_row_get(clip_row, "labeler", clip_id=clip_id)
    pt_verified = parse_bool(clip_row.get("pt_verified", ""), context=f"{clip_id} pt_verified")

    reps = _build_reps(clip_id, rep_rows)

    return {
        "schema_version": SCHEMA_VERSION,
        "clip_id": clip_id,
        "exercise": exercise,
        "clip_type": clip_type,
        "view": view,
        "lighting": lighting,
        "fitness_level": fitness_level,
        "subject": {
            "expected": "user",
            "num_people_in_frame": num_people_in_frame,
            "subject_track_id": subject_track_id,
        },
        "ground_truth": {
            "actual_reps": actual_reps,
            "reps": reps,
        },
        "labeler": labeler,
        "pt_verified": pt_verified,
    }


def _manifest_row(labels: Dict[str, Any]) -> Dict[str, Any]:
    """The MANIFEST.json index row for one clip (spec §4's example shape) -- a subset of
    labels.json's own fields, kept separate so a stale MANIFEST row is a detectable disagreement
    (labeling/validate.py) rather than a second silently-independent source of truth."""
    return {
        "clip_id": labels["clip_id"],
        "exercise": labels["exercise"],
        "clip_type": labels["clip_type"],
        "view": labels["view"],
        "lighting": labels["lighting"],
        "fitness_level": labels["fitness_level"],
        "num_people_in_frame": labels["subject"]["num_people_in_frame"],
        "labeler": labels["labeler"],
        "pt_verified": labels["pt_verified"],
    }


def _load_or_init_manifest(manifest_path: Path) -> Dict[str, Any]:
    if manifest_path.is_file():
        with manifest_path.open(encoding="utf-8") as f:
            return json.load(f)
    return {"schema_version": SCHEMA_VERSION, "golden_version": "v3.0", "clips": []}


def _merge_manifest(manifest: Dict[str, Any], rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_id = {row["clip_id"]: row for row in manifest.get("clips", [])}
    for row in rows:
        by_id[row["clip_id"]] = row
    manifest["clips"] = [by_id[clip_id] for clip_id in sorted(by_id)]
    return manifest


def export_labels(
    clips_csv: Path, reps_csv: Path, golden_dir: Path, manifest_path: Optional[Path] = None
) -> List[Path]:
    """Reads clips_csv + reps_csv, writes one <clip_id>.labels.json per clip row into golden_dir,
    and merges each clip's MANIFEST row into golden_dir/MANIFEST.json (or manifest_path if given).
    Existing MANIFEST entries for OTHER clips are preserved untouched; an existing entry for the
    SAME clip_id is replaced (re-exporting a corrected CSV is expected, not an error). Returns the
    list of labels.json paths written, sorted by clip_id.
    """
    golden_dir = Path(golden_dir)
    golden_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = Path(manifest_path) if manifest_path else golden_dir / MANIFEST_FILENAME

    clip_rows = read_clip_rows(clips_csv)
    rep_rows = read_rep_rows(reps_csv)

    rep_rows_by_clip: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    known_clip_ids = {clip_row_get(r, "clip_id", clip_id="?") for r in clip_rows}
    for row in rep_rows:
        clip_id = clip_row_get(row, "clip_id", clip_id="?")
        if not clip_id:
            raise LabelExportError(f"{reps_csv}: a rep row is missing clip_id")
        if clip_id not in known_clip_ids:
            raise LabelExportError(
                f"{reps_csv}: rep row references clip_id {clip_id!r} not present in {clips_csv}"
            )
        rep_rows_by_clip[clip_id].append(row)

    written: List[Path] = []
    manifest_rows: List[Dict[str, Any]] = []
    for clip_row in clip_rows:
        clip_id = clip_row_get(clip_row, "clip_id", clip_id="?")
        labels = build_clip_labels(clip_row, rep_rows_by_clip.get(clip_id, []))
        labels_path = golden_dir / f"{clip_id}.labels.json"
        labels_path.write_text(json.dumps(labels, indent=2) + "\n", encoding="utf-8")
        written.append(labels_path)
        manifest_rows.append(_manifest_row(labels))

    manifest = _load_or_init_manifest(manifest_path)
    manifest = _merge_manifest(manifest, manifest_rows)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    return sorted(written)
