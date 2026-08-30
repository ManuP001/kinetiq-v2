#!/usr/bin/env python3
"""
evals/gate0/golden_loader.py

Loads and validates the frozen golden set (EVAL_HARNESS_STAGE0_SPEC.md §3-5): the MANIFEST.json
index, each clip's <clip_id>.labels.json (frozen ground truth) and <clip_id>.keypoints.jsonl
(frozen input).

detected.json provenance (spec §5, §12; Stage 1 changes this from Stage 0): for any exercise the
Stage-1 reference detector supports (detector.adapter.run_detector), detected output is now
RECOMPUTED from the frozen keypoints on every load -- reproducible, and no longer a hand-authored
or live-captured file on disk. For an exercise the detector doesn't support yet (nothing in the
current golden set, but a future Tier A/B/C clip could exist before its own detector logic
lands), this falls back to reading a pre-existing <clip_id>.detected.json, exactly as Stage 0 did
-- "keep the bootstrap as a fallback". Either way, detected.json is never frozen truth the way
labels.json and keypoints.jsonl are.

Run standalone as a lint check:  python golden_loader.py <golden_dir>
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import exercise_lib
from detector.adapter import run_detector, score_subject_lock_against_expected

VALID_CLIP_TYPES = ("normal", "phantom_bench", "phantom_empty", "bystander")
PHANTOM_LIKE_CLIP_TYPES = ("phantom_bench", "phantom_empty", "bystander")
VALID_VIEWS = ("front", "side", "diagonal")


class GoldenSetError(ValueError):
    """Raised when the golden set fails schema validation (EVAL_HARNESS_STAGE0_SPEC.md §4-5)."""


@dataclass
class GoldenClip:
    clip_id: str
    exercise: str
    clip_type: str
    view: Optional[str]
    lighting: Optional[str]
    fitness_level: Optional[str]
    subject_num_people_in_frame: Optional[int]
    subject_track_id: Optional[int]
    actual_reps: int
    gt_reps: List[Dict[str, Any]]
    detected_reps: int
    det_reps: List[Dict[str, Any]]
    subject_lock: Optional[Dict[str, Any]]
    coaching_cues: List[Dict[str, Any]]
    pose_model: Optional[str]
    keypoints_path: Path
    detector_source: str  # "run_detector" (reproducible) or "bootstrap" (pre-existing file)


def _read_json(path: Path, clip_id: str) -> Any:
    if not path.is_file():
        raise GoldenSetError(f"{clip_id}: missing required file {path.name}")
    with path.open(encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError as exc:
            raise GoldenSetError(f"{clip_id}: {path.name} is not valid JSON: {exc}") from exc


def _load_and_validate_keypoints(clip_id: str, path: Path) -> tuple:
    """Validate the frozen-input schema (spec §5): every frame has t_ms/pose_model/people, kp
    points are variable-length [x, y, z, vis] with z nullable. Returns (pose_model, frames) --
    the pose_model named by the first frame (frame-level pose_model can vary in principle, but a
    single recording isn't expected to switch models mid-clip) and the fully parsed frame list,
    ready to feed to run_detector without re-reading the file."""
    if not path.is_file():
        raise GoldenSetError(f"{clip_id}: missing required file {path.name}")
    pose_model: Optional[str] = None
    frames: List[Dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                frame = json.loads(line)
            except json.JSONDecodeError as exc:
                raise GoldenSetError(
                    f"{clip_id}: {path.name}:{lineno} invalid JSON: {exc}"
                ) from exc
            for required in ("t_ms", "pose_model", "people"):
                if required not in frame:
                    raise GoldenSetError(
                        f"{clip_id}: {path.name}:{lineno} missing required field {required!r}"
                    )
            for person in frame["people"]:
                if "track_id" not in person or "kp" not in person:
                    raise GoldenSetError(
                        f"{clip_id}: {path.name}:{lineno} person entry missing track_id/kp"
                    )
                for point in person["kp"]:
                    if len(point) != 4:
                        raise GoldenSetError(
                            f"{clip_id}: {path.name}:{lineno} keypoint {point!r} must be "
                            f"[x, y, z, vis] (z nullable for 2D-only pose models)"
                        )
            if pose_model is None:
                pose_model = frame["pose_model"]
            frames.append(frame)
    if not frames:
        raise GoldenSetError(f"{clip_id}: {path.name} has no frames")
    return pose_model, frames


def _load_detected(
    clip_id: str, golden_dir: Path, frames: List[Dict[str, Any]], exercise: str, expected_track_id: Optional[int]
) -> tuple:
    """Returns (detected_dict, source) where detected_dict has the same shape as a hand-authored
    detected.json ({detected_reps, reps, subject_lock, coaching_cues}) and source is
    "run_detector" or "bootstrap" (see module docstring)."""
    try:
        detected_clip = run_detector(frames, exercise)
    except KeyError:
        detected = _read_json(golden_dir / f"{clip_id}.detected.json", clip_id)
        return detected, "bootstrap"

    result = detected_clip.to_dict()
    result["subject_lock"] = score_subject_lock_against_expected(detected_clip, expected_track_id)
    return result, "run_detector"


def load_golden(golden_dir: Path) -> List[GoldenClip]:
    golden_dir = Path(golden_dir)
    manifest = _read_json(golden_dir / "MANIFEST.json", clip_id="MANIFEST")

    try:
        severities = exercise_lib.load_fault_severities()
    except exercise_lib.ExerciseLibraryError as exc:
        raise GoldenSetError(f"exercise library failed validation: {exc}") from exc

    clips: List[GoldenClip] = []
    for row in manifest.get("clips", []):
        clip_id = row["clip_id"]
        labels = _read_json(golden_dir / f"{clip_id}.labels.json", clip_id)
        keypoints_path = golden_dir / f"{clip_id}.keypoints.jsonl"
        pose_model, frames = _load_and_validate_keypoints(clip_id, keypoints_path)

        exercise = labels["exercise"]
        clip_type = labels["clip_type"]
        if clip_type not in VALID_CLIP_TYPES:
            raise GoldenSetError(
                f"{clip_id}: unknown clip_type {clip_type!r}, must be one of {VALID_CLIP_TYPES}"
            )
        view = labels.get("view")
        if view is not None and view not in VALID_VIEWS:
            raise GoldenSetError(f"{clip_id}: unknown view {view!r}, must be one of {VALID_VIEWS}")

        if exercise not in severities:
            raise GoldenSetError(
                f"{clip_id}: exercise {exercise!r} is not in the exercise library"
            )
        ex_severities = severities[exercise]

        ground_truth = labels.get("ground_truth", {})
        actual_reps = ground_truth.get("actual_reps", 0)
        gt_reps = ground_truth.get("reps", [])

        for rep in gt_reps:
            for fault in rep.get("faults", []):
                if fault not in ex_severities:
                    raise GoldenSetError(
                        f"{clip_id}: fault {fault!r} on gt rep {rep.get('idx')} is not defined "
                        f"in {exercise!r}'s exercise-library entry"
                    )

        if clip_type in PHANTOM_LIKE_CLIP_TYPES and actual_reps != 0:
            raise GoldenSetError(
                f"{clip_id}: clip_type {clip_type!r} must have ground_truth.actual_reps == 0 "
                f"(EVAL_HARNESS_STAGE0_SPEC.md §5)"
            )

        subject = labels.get("subject", {})
        detected, detector_source = _load_detected(
            clip_id, golden_dir, frames, exercise, subject.get("subject_track_id")
        )

        det_reps = detected.get("reps", [])
        for rep in det_reps:
            for flag in rep.get("flags", []):
                if flag not in ex_severities:
                    raise GoldenSetError(
                        f"{clip_id}: detected flag {flag!r} on rep {rep.get('idx')} is not "
                        f"defined in {exercise!r}'s exercise-library entry"
                    )

        clips.append(
            GoldenClip(
                clip_id=clip_id,
                exercise=exercise,
                clip_type=clip_type,
                view=view,
                lighting=labels.get("lighting"),
                fitness_level=labels.get("fitness_level"),
                subject_num_people_in_frame=subject.get("num_people_in_frame"),
                subject_track_id=subject.get("subject_track_id"),
                actual_reps=actual_reps,
                gt_reps=gt_reps,
                detected_reps=detected.get("detected_reps", 0),
                det_reps=det_reps,
                subject_lock=detected.get("subject_lock"),
                coaching_cues=detected.get("coaching_cues", []),
                pose_model=pose_model,
                keypoints_path=keypoints_path,
                detector_source=detector_source,
            )
        )
    return clips


def _main() -> int:
    if len(sys.argv) != 2:
        print("usage: python golden_loader.py <golden_dir>", file=sys.stderr)
        return 2
    golden_dir = Path(sys.argv[1])
    try:
        clips = load_golden(golden_dir)
    except GoldenSetError as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1
    print(f"OK: {len(clips)} clip(s) validated in {golden_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
