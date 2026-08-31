#!/usr/bin/env python3
"""
evals/gate0/detector/pose_capture/cli.py

Command-line entry point for capturing keypoints from a candidate pose model
(GOLDEN_SET_PROTOCOL.md §6):

    python -m detector.pose_capture --list
        # every candidate model + whether its runtime is available here.

    python -m detector.pose_capture --model blazepose_33 --dry-run
        # no video or runtime needed -- proves the schema/writer plumbing works and prints
        # install instructions for capturing for real.

    python -m detector.pose_capture --model blazepose_33 --video path/to/clip.mp4 \
        --clip-id squat_clean_side_001 --golden golden/
        # the real capture -- requires the model's runtime installed (see --list / install_hint).

Run from evals/gate0/ (so the `detector` package resolves via -m's cwd-relative lookup).

Privacy (GOLDEN_SET_PROTOCOL.md §1): only ever writes keypoints.jsonl + capture_meta.json under
--golden; never copies the video itself anywhere. Delete/offline the source video yourself once
capture is done.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from detector.pose_capture.base import PoseRuntimeUnavailable, capture_clip, dry_run_self_test
from detector.pose_capture.registry import available_pose_models, get_adapter


def _cmd_list() -> int:
    print(f"{'model':<20}{'available here':<18}install hint")
    for pose_model in available_pose_models():
        adapter = get_adapter(pose_model)
        available = "yes" if adapter.is_available() else "no"
        print(f"{pose_model:<20}{available:<18}{adapter.install_hint()}")
    return 0


def _cmd_dry_run(pose_model: str) -> int:
    adapter = get_adapter(pose_model)
    print(dry_run_self_test(adapter))
    return 0


def _cmd_capture(pose_model: str, video: Path, clip_id: str, golden_dir: Path) -> int:
    adapter = get_adapter(pose_model)
    try:
        result = capture_clip(adapter, video, golden_dir, clip_id)
    except PoseRuntimeUnavailable as exc:
        print(f"error: {exc}", file=sys.stderr)
        print("Run with --dry-run to verify the tool itself works without this runtime.",
              file=sys.stderr)
        return 2

    if result.avg_latency_ms_per_frame is not None:
        print(
            f"wrote {result.keypoints_path} ({result.frames_written} frames, "
            f"avg {result.avg_latency_ms_per_frame:.1f}ms/frame; {result.capture_env})"
        )
    else:
        print(f"wrote {result.keypoints_path} (0 frames -- check the video path/codec)")
    print(f"wrote {result.meta_path}")
    print("Remember: delete/offline the source video now -- only keypoints are committed "
          "(GOLDEN_SET_PROTOCOL.md §1).")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--model", choices=available_pose_models(),
        help="Candidate pose model to run (see --list).",
    )
    parser.add_argument("--video", type=Path, help="Path to the source video (never committed).")
    parser.add_argument("--clip-id", help="Clip id, e.g. squat_clean_side_001.")
    parser.add_argument(
        "--golden", type=Path, default=Path("golden"),
        help="golden/ directory to write poses/<model>/<clip_id>.keypoints.jsonl into "
             "(default: ./golden).",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Self-test the schema/writer without a video or the model's runtime installed.",
    )
    parser.add_argument(
        "--list", action="store_true", help="List candidate models and runtime availability.",
    )
    args = parser.parse_args(argv)

    if args.list:
        return _cmd_list()
    if not args.model:
        parser.error("--model is required (or use --list)")
    if args.dry_run:
        return _cmd_dry_run(args.model)
    if not args.video or not args.clip_id:
        parser.error("--video and --clip-id are required for a real capture (or use --dry-run)")
    return _cmd_capture(args.model, args.video, args.clip_id, args.golden)


if __name__ == "__main__":
    raise SystemExit(main())
