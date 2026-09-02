#!/usr/bin/env python3
"""
evals/gate0/detector/pose_capture/rtmpose_adapter.py

RTMPose-m, Halpe-26 capture adapter (config.POSE_MODEL_CANDIDATES "rtmpose_halpe26"), via
`rtmlib` (the lightweight ONNX Runtime wrapper the Good-GYM project VISION_ARCHITECTURE.md §2
cites uses). Landmark index -> name mapping lives in detector/keypoint_map.py; this module only
runs the model and emits its raw 26-point output.

LIVE-TESTED (pose_capture/README.md): confirmed end-to-end against a real video on
rtmlib 0.0.16 / onnxruntime 1.29.0. Two corrections found by live-testing rather than trusting
the original sketch:
  1. rtmlib's `Body` solution class -- despite this candidate's name -- loads the plain-COCO-17
     `body7` weights (verified via `Body.MODE`'s preset URLs and a live shape check: `Body(...)`
     returns `keypoints.shape == (n, 17, 2)`). The Halpe-26 weights this candidate actually needs
     live behind `BodyWithFeet` instead (its own docstring: "Initialize the Halpe26 pose
     estimation model"; `BodyWithFeet.MODE` preset URLs contain "-halpe26_"), confirmed live to
     return `keypoints.shape == (n, 26, 2)`.
  2. rtmlib returns **pixel coordinates in the source frame's own resolution**, not normalized
     [0, 1] -- confirmed live on an 850x478 frame: x/y values ranged up to ~478/~850, not [0, 1].
     `EVAL_HARNESS_STAGE0_SPEC.md`'s schema and `detector/subject_lock.py`'s `most_central` rule
     (nearest bbox centroid to frame centre `(0.5, 0.5)`) both assume frame-normalized
     coordinates, so this adapter divides x by frame width and y by frame height before emitting.
Both `Body` and `BodyWithFeet` are top-down (YOLOX person detector + per-box pose), so this
adapter is natively multi-person per ADR-300 -- no separate `person_detector` wiring needed here,
rtmlib does it internally.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterator

from detector.pose_capture.base import PoseCaptureAdapter, PoseRuntimeUnavailable


class RTMPoseAdapter(PoseCaptureAdapter):
    pose_model_name = "rtmpose_halpe26"

    def is_available(self) -> bool:
        try:
            import rtmlib  # noqa: F401
        except ImportError:
            return False
        return True

    def install_hint(self) -> str:
        return (
            "pip install rtmlib opencv-python onnxruntime. rtmlib downloads RTMPose-m/Halpe-26 "
            "ONNX weights (body7-halpe26) plus the YOLOX person detector automatically on first "
            "use of BodyWithFeet(mode='balanced', ...) -- NOT `Body`, which loads plain-COCO-17 "
            "weights despite the similar name (live-verified this session, see module docstring)."
        )

    def infer_frames(self, video_path: Path) -> Iterator[Dict[str, Any]]:
        if not self.is_available():
            raise PoseRuntimeUnavailable(f"{self.pose_model_name}: {self.install_hint()}")

        import cv2
        from rtmlib import BodyWithFeet

        body = BodyWithFeet(mode="balanced", to_openpose=False, backend="onnxruntime", device="cpu")

        cap = cv2.VideoCapture(str(video_path))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        try:
            frame_idx = 0
            while True:
                ok, image = cap.read()
                if not ok:
                    break
                t_ms = int(frame_idx * 1000 / fps)
                frame_h, frame_w = image.shape[:2]

                keypoints, scores = body(image)  # keypoints: [n_people, 26, 2] in PIXEL coords

                people = []
                for track_id, (person_kp, person_scores) in enumerate(zip(keypoints, scores)):
                    kp = [
                        [float(x) / frame_w, float(y) / frame_h, None, float(score)]
                        for (x, y), score in zip(person_kp, person_scores)
                    ]
                    xs = [pt[0] for pt in kp]
                    ys = [pt[1] for pt in kp]
                    box = [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)]
                    people.append({"track_id": track_id, "kp": kp, "box": box})

                yield {"t_ms": t_ms, "pose_model": self.pose_model_name, "people": people}
                frame_idx += 1
        finally:
            cap.release()
