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
# Only phantom_bench/phantom_empty are zero-rep (EVAL_HARNESS_STAGE0_SPEC.md §5/§7,
# EVAL_STRATEGY.md, EXERCISE_LIBRARY.md §5, ROADMAP.md -- the resolved cross-doc decision).
# bystander is a REAL-REP clip: the user exercises normally while a second person is in frame;
# it's scored under subject-lock (scorers/subject_lock.py) and rep-accuracy, never treated as a
# zero-rep phantom gate (scorers/phantom.py's PHANTOM_CLIP_TYPES mirrors this).
PHANTOM_LIKE_CLIP_TYPES = ("phantom_bench", "phantom_empty")
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


def validate_frame_schema(frame: Dict[str, Any], context: str) -> None:
    """The frozen-input frame schema (EVAL_HARNESS_STAGE0_SPEC.md §5): t_ms/pose_model/people
    required, kp points are variable-length [x, y, z, vis] with z nullable. Shared by this
    loader (parsing committed keypoints.jsonl lines) and detector/pose_capture/ (validating a
    freshly-inferred frame before it's ever written to disk) -- one set of rules, not two
    independently-maintained copies. Raises ValueError, not GoldenSetError: pose_capture output
    isn't part of a golden set yet when this runs on it."""
    for required in ("t_ms", "pose_model", "people"):
        if required not in frame:
            raise ValueError(f"{context}: missing required field {required!r}")
    for person in frame["people"]:
        if "track_id" not in person or "kp" not in person:
            raise ValueError(f"{context}: person entry missing track_id/kp")
        for point in person["kp"]:
            if len(point) != 4:
                raise ValueError(
                    f"{context}: keypoint {point!r} must be [x, y, z, vis] "
                    f"(z nullable for 2D-only pose models)"
                )


def _load_and_validate_keypoints(clip_id: str, path: Path) -> tuple:
    """Validate the frozen-input schema (spec §5) for every line of a committed keypoints.jsonl.
    Returns (pose_model, frames) -- the pose_model named by the first frame (frame-level
    pose_model can vary in principle, but a single recording isn't expected to switch models
    mid-clip) and the fully parsed frame list, ready to feed to run_detector without re-reading
    the file."""
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
            try:
                validate_frame_schema(frame, context=f"{path.name}:{lineno}")
            except ValueError as exc:
                raise GoldenSetError(f"{clip_id}: {exc}") from exc
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


def _load_severities() -> Dict[str, Dict[str, str]]:
    try:
        return exercise_lib.load_fault_severities()
    except exercise_lib.ExerciseLibraryError as exc:
        raise GoldenSetError(f"exercise library failed validation: {exc}") from exc


def _load_clip(
    clip_id: str,
    golden_dir: Path,
    keypoints_path: Path,
    severities: Dict[str, Dict[str, str]],
) -> GoldenClip:
    """The full per-clip load+validate pipeline, shared by load_golden (flat keypoints.jsonl,
    MANIFEST-driven) and load_golden_poses (Stage 2: golden/poses/<model>/, discovered by
    directory scan) -- see each function's docstring for what differs between them."""
    labels = _read_json(golden_dir / f"{clip_id}.labels.json", clip_id)
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
        raise GoldenSetError(f"{clip_id}: exercise {exercise!r} is not in the exercise library")
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
        # Stage 3 (SPRINT.md G2): a sustained flag the detector couldn't judge either way this
        # rep -- same validation as a committed flag, since it still names a real fault id.
        for flag in rep.get("insufficient_evidence", []):
            if flag not in ex_severities:
                raise GoldenSetError(
                    f"{clip_id}: insufficient_evidence flag {flag!r} on rep {rep.get('idx')} is "
                    f"not defined in {exercise!r}'s exercise-library entry"
                )

    return GoldenClip(
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


def load_golden(golden_dir: Path) -> List[GoldenClip]:
    """The Stage-0/1 path: MANIFEST-driven, one flat <clip_id>.keypoints.jsonl per clip
    (--data/--mode fast|full). Unchanged by Stage 2 -- see load_golden_poses for the bake-off."""
    golden_dir = Path(golden_dir)
    manifest = _read_json(golden_dir / "MANIFEST.json", clip_id="MANIFEST")
    severities = _load_severities()

    clips: List[GoldenClip] = []
    for row in manifest.get("clips", []):
        clip_id = row["clip_id"]
        keypoints_path = golden_dir / f"{clip_id}.keypoints.jsonl"
        clips.append(_load_clip(clip_id, golden_dir, keypoints_path, severities))
    return clips


def load_golden_poses(golden_dir: Path, pose_model: str) -> List[GoldenClip]:
    """Stage 2 (--compare-pose-models): load every clip that has frozen keypoints for
    `pose_model` under golden/poses/<pose_model>/ (GOLDEN_SET_PROTOCOL.md §2), cross-referencing
    the SAME model-independent <clip_id>.labels.json every pose model shares (ground truth
    doesn't change with the model under test). Discovered by scanning the poses/ directory
    directly, independent of MANIFEST.json's main clip list -- a bake-off-only clip doesn't need
    a flat top-level keypoints.jsonl, which load_golden (and --mode fast/full) still requires and
    this function never touches. Returns [] if no clips exist for this pose model yet."""
    golden_dir = Path(golden_dir)
    poses_dir = golden_dir / "poses" / pose_model
    if not poses_dir.is_dir():
        return []
    severities = _load_severities()

    suffix = ".keypoints.jsonl"
    clips: List[GoldenClip] = []
    for keypoints_path in sorted(poses_dir.glob(f"*{suffix}")):
        clip_id = keypoints_path.name[: -len(suffix)]
        clip = _load_clip(clip_id, golden_dir, keypoints_path, severities)
        if clip.pose_model != pose_model:
            raise GoldenSetError(
                f"{clip_id}: keypoints under poses/{pose_model}/ declare pose_model "
                f"{clip.pose_model!r} -- directory/frame mismatch"
            )
        clips.append(clip)
    return clips


def load_capture_meta(golden_dir: Path, pose_model: str, clip_id: str) -> Optional[Dict[str, Any]]:
    """Optional per-(model, clip) capture stats -- avg_latency_ms_per_frame, capture_env,
    frames_captured -- written by detector/pose_capture/ next to the keypoints it produced
    (golden/poses/<model>/<clip_id>.capture_meta.json). Not part of the frozen schema
    (EVAL_HARNESS_STAGE0_SPEC.md §5 doesn't define it) and never required: a hand-authored or
    synthetic clip simply has none, and callers (aggregate.py's --compare-pose-models table)
    must treat that as "n/a", not an error. Latency here is capture-machine wall-clock, NOT
    on-device -- see its capture_env field for what actually produced it."""
    path = golden_dir / "poses" / pose_model / f"{clip_id}.capture_meta.json"
    if not path.is_file():
        return None
    with path.open(encoding="utf-8") as f:
        return json.load(f)


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
