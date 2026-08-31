#!/usr/bin/env python3
"""
evals/gate0/detector/pose_capture/registry.py

Maps each config.POSE_MODEL_CANDIDATES name to its PoseCaptureAdapter implementation -- the one
place that knows "blazepose_33 -> BlazePoseAdapter" etc, so the CLI (and any other caller)
iterates config.py's registry (never a hardcoded model list) and looks up the adapter class here.
"""
from __future__ import annotations

from typing import Dict, Tuple, Type

import gate_config
from detector.pose_capture.base import PoseCaptureAdapter
from detector.pose_capture.blazepose_adapter import BlazePoseAdapter
from detector.pose_capture.movenet_adapter import MoveNetAdapter
from detector.pose_capture.rtmpose_adapter import RTMPoseAdapter

_ADAPTER_CLASSES: Dict[str, Type[PoseCaptureAdapter]] = {
    "blazepose_33": BlazePoseAdapter,
    "movenet_17": MoveNetAdapter,
    "rtmpose_halpe26": RTMPoseAdapter,
}


def available_pose_models() -> Tuple[str, ...]:
    """Every pose model in config.POSE_MODEL_CANDIDATES that also has an adapter implemented
    here -- the intersection, so a registered-but-not-yet-implemented candidate doesn't crash
    callers that enumerate this."""
    return tuple(
        c["name"] for c in gate_config.POSE_MODEL_CANDIDATES if c["name"] in _ADAPTER_CLASSES
    )


def get_adapter(pose_model: str) -> PoseCaptureAdapter:
    """Instantiates the adapter for `pose_model`. Raises KeyError with a clear message if
    `pose_model` isn't in config.POSE_MODEL_CANDIDATES or has no adapter class here -- never
    silently substitutes a different model."""
    known = {c["name"] for c in gate_config.POSE_MODEL_CANDIDATES}
    if pose_model not in known:
        raise KeyError(
            f"{pose_model!r} is not in config.POSE_MODEL_CANDIDATES "
            f"({sorted(known)}) -- add it there first"
        )
    adapter_cls = _ADAPTER_CLASSES.get(pose_model)
    if adapter_cls is None:
        raise KeyError(
            f"{pose_model!r} is registered in config.POSE_MODEL_CANDIDATES but has no "
            f"PoseCaptureAdapter implemented yet -- add one to detector/pose_capture/ and "
            f"register it here"
        )
    return adapter_cls()
