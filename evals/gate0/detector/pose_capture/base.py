#!/usr/bin/env python3
"""
evals/gate0/detector/pose_capture/base.py

The adapter interface every candidate pose model implements, and the (deterministic-except-for-
the-adapter-call) writer that turns an adapter's output into a committed
golden/poses/<model>/<clip_id>.keypoints.jsonl plus a companion .capture_meta.json
(golden_loader.load_capture_meta).

Design rule: an adapter's actual model-runtime import happens LAZILY, inside infer_frames(), not
at module import time. That's what lets this package (and its CLI) be imported and enumerate
"which candidates are available here" on a machine with none of mediapipe/tensorflow/rtmlib
installed -- is_available() must be safe to call unconditionally.
"""
from __future__ import annotations

import abc
import json
import platform
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from golden_loader import validate_frame_schema


class PoseRuntimeUnavailable(RuntimeError):
    """Raised by capture_clip() (or an adapter's infer_frames()) when the runtime/weights this
    adapter needs aren't importable/available in the current environment. Expected and normal --
    not every machine running this harness has every ML runtime installed; see the adapter's
    install_hint()."""


@dataclass
class CaptureResult:
    clip_id: str
    pose_model: str
    frames_written: int
    avg_latency_ms_per_frame: Optional[float]
    capture_env: str
    keypoints_path: Path
    meta_path: Path


class PoseCaptureAdapter(abc.ABC):
    """One implementation per config.POSE_MODEL_CANDIDATES entry. pose_model_name MUST match
    that entry's "name" field exactly -- it's written into every frame's pose_model field, and
    it's the golden/poses/<name>/ directory this adapter's output lands in."""

    pose_model_name: str

    @abc.abstractmethod
    def is_available(self) -> bool:
        """Whether this adapter's runtime is importable (and, where practical, weights are
        resolvable) in the current environment. Must never raise -- a missing dependency is
        this method's normal, expected answer (False), not an exception."""

    @abc.abstractmethod
    def install_hint(self) -> str:
        """Human-readable instructions for installing this adapter's runtime + weights on a
        machine that can run it for real."""

    @abc.abstractmethod
    def infer_frames(self, video_path: Path) -> Iterator[Dict[str, Any]]:
        """Yields one Stage-0-schema frame dict per video frame
        (EVAL_HARNESS_STAGE0_SPEC.md §5): {"t_ms": int, "pose_model": str,
        "people": [{"track_id": int, "kp": [[x, y, z, vis], ...], "box": [x, y, w, h]}]}.
        Include every detected person (subject-lock needs the full set for bystander clips).
        Only ever called by capture_clip() after is_available() is True; may raise
        PoseRuntimeUnavailable itself as a defence-in-depth check."""


def capture_clip(
    adapter: PoseCaptureAdapter, video_path: Path, golden_dir: Path, clip_id: str
) -> CaptureResult:
    """Runs `adapter` over `video_path` and writes
    golden/poses/<adapter.pose_model_name>/<clip_id>.keypoints.jsonl (schema-validated frame by
    frame, so a malformed frame is caught before anything is committed) plus a companion
    .capture_meta.json (latency, capture environment -- see golden_loader.load_capture_meta's
    docstring on why this is capture-machine wall-clock, not on-device).

    Requires adapter.is_available(); raises PoseRuntimeUnavailable otherwise. A caller that
    can't guarantee the runtime is installed should check is_available() itself, or use
    dry_run_self_test() instead of calling this at all -- this function never fabricates
    keypoints when the runtime is missing.

    Privacy invariant (GOLDEN_SET_PROTOCOL.md §1): only writes keypoints.jsonl + capture_meta.json
    -- never copies, moves, or references the video file itself into golden_dir.
    """
    if not adapter.is_available():
        raise PoseRuntimeUnavailable(
            f"{adapter.pose_model_name}: runtime not available in this environment. "
            f"{adapter.install_hint()}"
        )

    out_dir = Path(golden_dir) / "poses" / adapter.pose_model_name
    out_dir.mkdir(parents=True, exist_ok=True)
    keypoints_path = out_dir / f"{clip_id}.keypoints.jsonl"
    meta_path = out_dir / f"{clip_id}.capture_meta.json"

    frames_iter = adapter.infer_frames(Path(video_path))
    latencies_ms: List[float] = []
    frame_count = 0
    with keypoints_path.open("w", encoding="utf-8") as f:
        while True:
            start = time.perf_counter()
            try:
                frame = next(frames_iter)
            except StopIteration:
                break
            # Timed around next() only -- the adapter's actual inference work happens inside its
            # generator body, not in our own json.dumps/write below.
            latencies_ms.append((time.perf_counter() - start) * 1000)
            validate_frame_schema(frame, context=f"{clip_id} frame {frame_count}")
            if frame.get("pose_model") != adapter.pose_model_name:
                raise ValueError(
                    f"{clip_id} frame {frame_count}: adapter {adapter.pose_model_name!r} "
                    f"produced pose_model {frame.get('pose_model')!r}"
                )
            f.write(json.dumps(frame) + "\n")
            frame_count += 1

    avg_latency = sum(latencies_ms) / len(latencies_ms) if latencies_ms else None
    capture_env = f"{platform.platform()} / python {platform.python_version()} (capture-machine, not on-device)"
    meta = {
        "pose_model": adapter.pose_model_name,
        "clip_id": clip_id,
        "frames_captured": frame_count,
        "avg_latency_ms_per_frame": avg_latency,
        "capture_env": capture_env,
    }
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    return CaptureResult(
        clip_id=clip_id,
        pose_model=adapter.pose_model_name,
        frames_written=frame_count,
        avg_latency_ms_per_frame=avg_latency,
        capture_env=capture_env,
        keypoints_path=keypoints_path,
        meta_path=meta_path,
    )


def dry_run_self_test(adapter: PoseCaptureAdapter) -> str:
    """Proves the writer + schema validator work correctly for this adapter WITHOUT needing its
    runtime installed and WITHOUT ever touching golden_dir -- a synthetic frame is written to a
    throwaway temp file, validated, and discarded. This is explicitly not "fake keypoints as if
    real": nothing here is written anywhere a caller could mistake for captured data, and the
    return value says so. Use this when is_available() is False to confirm the tool itself is
    correct, then follow install_hint() to actually capture on a capable machine."""
    import tempfile

    synthetic_frame = {
        "t_ms": 0,
        "pose_model": adapter.pose_model_name,
        "people": [{"track_id": 0, "kp": [[0.5, 0.5, None, 0.9]], "box": [0.4, 0.4, 0.2, 0.2]}],
    }
    validate_frame_schema(synthetic_frame, context="dry-run self-test")

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".keypoints.jsonl", delete=False, encoding="utf-8"
    ) as f:
        f.write(json.dumps(synthetic_frame) + "\n")
        temp_path = f.name
    Path(temp_path).unlink(missing_ok=True)

    availability = "available" if adapter.is_available() else "NOT available"
    return (
        f"DRY RUN: {adapter.pose_model_name} runtime is {availability} in this environment.\n"
        f"  Schema self-test: PASSED (wrote+validated 1 synthetic frame to a throwaway temp "
        f"file, never committed).\n"
        f"  To capture for real: {adapter.install_hint()}"
    )
