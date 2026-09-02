#!/usr/bin/env python3
"""
evals/gate0/labeling/validate.py

The validator CI (and a PT/dev running it by hand) runs over golden/ after export.py writes
labels.json + MANIFEST.json: does every fault id actually exist in that exercise's library with a
real severity, do phantom_bench/phantom_empty clips carry actual_reps == 0, does a bystander clip
carry a real rep count with a marked subject, are keypoints.jsonl frames schema-valid, do
MANIFEST.json and the labels.json files agree. Unlike golden_loader.py (which raises and stops at
the first problem -- correct for its own job of building clip objects to score), this collects
EVERY issue across the whole set into one ValidationReport, because a PT fixing a spreadsheet
needs the full list, not one error at a time.

Severity taxonomy note (EXERCISE_LIBRARY.md §4): the exercise library still writes "medium", not
"med" -- exercise_lib.py already resolved this by aliasing at read time (see its module
docstring); this validator reuses that loader rather than re-deciding it.

Bystander actual_reps -- RESOLVED (was previously a genuine cross-doc conflict, flagged rather
than silently picked in an earlier revision of this file): the canonical answer, now consistent
across EVAL_HARNESS_STAGE0_SPEC.md §5/§7, EVAL_STRATEGY.md, EXERCISE_LIBRARY.md §5, and
ROADMAP.md, is that only phantom_bench/phantom_empty are zero-rep. A bystander clip is a REAL-REP
clip: the user exercises normally (actual_reps = the user's real count, > 0, reps[] labeled with
faults exactly like a normal clip) while a second person stands nearby, and is scored under
subject-lock (scorers/subject_lock.py) plus ordinary rep-accuracy -- never the phantom gate
(scorers/phantom.py). This validator's PHANTOM_LIKE_CLIP_TYPES import (golden_loader.py) reflects
that: it no longer includes "bystander".
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import exercise_lib
from aggregate import LIGHTING_CONDITIONS
from gate_config import FITNESS_LEVEL_DEFAULT_SETS_REPS
from golden_loader import (
    PHANTOM_LIKE_CLIP_TYPES,
    VALID_CLIP_TYPES,
    VALID_VIEWS,
    validate_frame_schema,
)

MANIFEST_FILENAME = "MANIFEST.json"
VALID_FITNESS_LEVELS = tuple(FITNESS_LEVEL_DEFAULT_SETS_REPS.keys())

# Fields present on both a MANIFEST row and its labels.json -- checked for agreement.
_SHARED_FIELDS = (
    "exercise",
    "clip_type",
    "view",
    "lighting",
    "fitness_level",
    "labeler",
    "pt_verified",
)


@dataclass
class ValidationIssue:
    clip_id: str
    level: str  # "error" | "warning"
    message: str
    rep_idx: Optional[int] = None

    def format(self) -> str:
        where = self.clip_id if self.rep_idx is None else f"{self.clip_id} rep {self.rep_idx}"
        return f"[{self.level.upper()}] {where}: {self.message}"


@dataclass
class ValidationReport:
    issues: List[ValidationIssue] = field(default_factory=list)

    def error(self, clip_id: str, message: str, rep_idx: Optional[int] = None) -> None:
        self.issues.append(ValidationIssue(clip_id, "error", message, rep_idx))

    def warning(self, clip_id: str, message: str, rep_idx: Optional[int] = None) -> None:
        self.issues.append(ValidationIssue(clip_id, "warning", message, rep_idx))

    @property
    def errors(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.level == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def format(self) -> str:
        if not self.issues:
            return "OK: no issues found."
        lines = [i.format() for i in sorted(self.issues, key=lambda i: (i.clip_id, i.rep_idx or 0))]
        lines.append(f"-- {len(self.errors)} error(s), {len(self.warnings)} warning(s)")
        return "\n".join(lines)


def _read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _check_keypoints(golden_dir: Path, clip_id: str, report: ValidationReport) -> None:
    candidates = list(golden_dir.glob(f"poses/*/{clip_id}.keypoints.jsonl"))
    flat = golden_dir / f"{clip_id}.keypoints.jsonl"
    if flat.is_file():
        candidates.append(flat)

    if not candidates:
        report.warning(clip_id, "no keypoints.jsonl captured yet (under poses/<model>/ or flat)")
        return

    for path in candidates:
        pose_model = path.parent.name if path.parent != golden_dir else "(flat)"
        with path.open(encoding="utf-8") as f:
            for lineno, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    frame = json.loads(line)
                except json.JSONDecodeError as exc:
                    report.error(clip_id, f"{pose_model} line {lineno}: invalid JSON: {exc}")
                    continue
                try:
                    validate_frame_schema(frame, context=f"{pose_model} line {lineno}")
                except ValueError as exc:
                    report.error(clip_id, str(exc))


def _check_labels(
    clip_id: str,
    labels: Dict[str, Any],
    severities: Optional[Dict[str, Dict[str, str]]],
    report: ValidationReport,
) -> None:
    exercise = labels.get("exercise")
    clip_type = labels.get("clip_type")
    view = labels.get("view")
    lighting = labels.get("lighting")
    fitness_level = labels.get("fitness_level")

    if clip_type not in VALID_CLIP_TYPES:
        report.error(clip_id, f"unknown clip_type {clip_type!r}, must be one of {VALID_CLIP_TYPES}")
    if view is not None and view not in VALID_VIEWS:
        report.error(clip_id, f"unknown view {view!r}, must be one of {VALID_VIEWS}")
    if lighting is not None and lighting not in LIGHTING_CONDITIONS:
        report.error(clip_id, f"unknown lighting {lighting!r}, must be one of {LIGHTING_CONDITIONS}")
    if fitness_level is not None and fitness_level not in VALID_FITNESS_LEVELS:
        report.error(
            clip_id,
            f"unknown fitness_level {fitness_level!r}, must be one of {VALID_FITNESS_LEVELS}",
        )

    ex_severities = None
    if severities is not None:
        if exercise not in severities:
            report.error(clip_id, f"exercise {exercise!r} is not in the exercise library")
        else:
            ex_severities = severities[exercise]

    subject = labels.get("subject", {})
    num_people = subject.get("num_people_in_frame")
    subject_track_id = subject.get("subject_track_id")
    ground_truth = labels.get("ground_truth", {})
    actual_reps = ground_truth.get("actual_reps")
    reps = ground_truth.get("reps", [])

    if clip_type in PHANTOM_LIKE_CLIP_TYPES:
        if actual_reps != 0 or reps:
            report.error(
                clip_id,
                f"clip_type {clip_type!r} must have actual_reps == 0 and reps == [] "
                f"(got actual_reps={actual_reps!r}, {len(reps)} rep row(s))",
            )
    else:
        # normal and bystander both carry a real rep count -- bystander is NOT phantom-like
        # (EVAL_HARNESS_STAGE0_SPEC.md §5/§7, EXERCISE_LIBRARY.md §5, ROADMAP.md): the user
        # really exercises while a second person is in frame, so its ground truth is labeled
        # exactly like a normal clip's, plus a marked subject for subject-lock scoring.
        if clip_type == "bystander":
            if not isinstance(actual_reps, int) or actual_reps <= 0:
                report.error(
                    clip_id,
                    f"bystander clip must have actual_reps > 0 (the user's real rep count while "
                    f"a second person is in frame), got {actual_reps!r}",
                )
            if subject_track_id is None:
                report.error(clip_id, "bystander clip must mark subject.subject_track_id")
        elif not isinstance(actual_reps, int) or actual_reps < 0:
            report.error(clip_id, f"actual_reps must be a non-negative integer, got {actual_reps!r}")

        if isinstance(actual_reps, int) and actual_reps >= 0 and len(reps) != actual_reps:
            report.error(
                clip_id,
                f"actual_reps={actual_reps} but {len(reps)} rep row(s) were labeled -- every rep "
                f"1..actual_reps needs a row (faults: [] for a clean rep)",
            )
        expected_idx = set(range(1, (actual_reps or 0) + 1)) if isinstance(actual_reps, int) else set()
        seen_idx = {r.get("idx") for r in reps}
        if expected_idx and seen_idx != expected_idx:
            report.error(
                clip_id,
                f"rep idx values {sorted(seen_idx)} don't cover 1..{actual_reps} exactly",
            )
        if num_people is not None and num_people > 1 and subject_track_id is None:
            report.error(clip_id, f"num_people_in_frame={num_people} but no subject_track_id marked")

    if ex_severities is not None:
        for rep in reps:
            rep_idx = rep.get("idx")
            for fault_id in rep.get("faults", []):
                if fault_id not in ex_severities:
                    report.error(
                        clip_id,
                        f"fault {fault_id!r} is not defined in {exercise!r}'s exercise-library entry",
                        rep_idx=rep_idx,
                    )


def _check_manifest_agreement(
    clip_id: str, manifest_row: Dict[str, Any], labels: Dict[str, Any], report: ValidationReport
) -> None:
    labels_view = dict(labels)
    labels_view["num_people_in_frame"] = labels.get("subject", {}).get("num_people_in_frame")
    for field_name in _SHARED_FIELDS:
        manifest_value = manifest_row.get(field_name)
        labels_value = labels_view.get(field_name)
        if manifest_value != labels_value:
            report.error(
                clip_id,
                f"MANIFEST.json {field_name}={manifest_value!r} disagrees with "
                f"labels.json {field_name}={labels_value!r}",
            )
    if manifest_row.get("num_people_in_frame") != labels_view.get("num_people_in_frame"):
        report.error(
            clip_id,
            f"MANIFEST.json num_people_in_frame={manifest_row.get('num_people_in_frame')!r} "
            f"disagrees with labels.json subject.num_people_in_frame="
            f"{labels_view.get('num_people_in_frame')!r}",
        )


def validate_golden_set(golden_dir: Path, exercise_lib_dir: Optional[Path] = None) -> ValidationReport:
    """Validates every clip in golden_dir: MANIFEST/labels.json agreement, fault-id/severity
    correctness, per-clip-type rep-count shape (phantom_bench/phantom_empty zero-rep,
    bystander/normal real-rep), and keypoints.jsonl schema validity. Never raises for a
    domain violation -- everything becomes an issue in the returned report; only a genuinely
    unreadable MANIFEST.json/labels.json (bad JSON) is fatal (still reported, not raised)."""
    golden_dir = Path(golden_dir)
    report = ValidationReport()

    manifest_path = golden_dir / MANIFEST_FILENAME
    manifest_by_id: Dict[str, Dict[str, Any]] = {}
    if not manifest_path.is_file():
        report.error("MANIFEST", f"missing {manifest_path}")
    else:
        try:
            manifest = _read_json(manifest_path)
        except json.JSONDecodeError as exc:
            report.error("MANIFEST", f"{manifest_path} is not valid JSON: {exc}")
            manifest = {"clips": []}
        for row in manifest.get("clips", []):
            clip_id = row.get("clip_id")
            if not clip_id:
                report.error("MANIFEST", "a clips[] row is missing clip_id")
                continue
            manifest_by_id[clip_id] = row

    try:
        severities = exercise_lib.load_fault_severities(exercise_lib_dir)
    except exercise_lib.ExerciseLibraryError as exc:
        report.error("EXERCISE_LIBRARY", str(exc))
        severities = None

    labels_files = {p.name[: -len(".labels.json")]: p for p in golden_dir.glob("*.labels.json")}

    for clip_id in sorted(set(manifest_by_id) | set(labels_files)):
        if clip_id not in labels_files:
            report.error(clip_id, "listed in MANIFEST.json but has no <clip_id>.labels.json")
            continue
        if clip_id not in manifest_by_id:
            report.error(clip_id, "has a labels.json but is not listed in MANIFEST.json")
            continue

        try:
            labels = _read_json(labels_files[clip_id])
        except json.JSONDecodeError as exc:
            report.error(clip_id, f"labels.json is not valid JSON: {exc}")
            continue

        _check_labels(clip_id, labels, severities, report)
        _check_manifest_agreement(clip_id, manifest_by_id[clip_id], labels, report)
        _check_keypoints(golden_dir, clip_id, report)

    return report
