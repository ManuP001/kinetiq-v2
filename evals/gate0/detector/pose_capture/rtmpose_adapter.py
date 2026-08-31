#!/usr/bin/env python3
"""
evals/gate0/detector/pose_capture/rtmpose_adapter.py

RTMPose-m, Halpe-26 capture adapter (config.POSE_MODEL_CANDIDATES "rtmpose_halpe26"), via
`rtmlib` (the lightweight ONNX Runtime wrapper the Good-GYM project VISION_ARCHITECTURE.md §2
cites uses). Landmark index -> name mapping lives in detector/keypoint_map.py; this module only
runs the model and emits its raw 26-point output.

NOT RUNNABLE IN THIS REPO'S DEV ENVIRONMENT: `rtmlib` isn't installed here (checked --
ModuleNotFoundError), and there's no recorded video yet either -- though notably `onnxruntime`
IS already installed in this environment (rtmlib's actual inference backend), so this adapter is
closer to runnable here than the other two once `rtmlib` itself and its `cv2` dependency are
added. is_available() correctly reports False; infer_frames()'s body is a best-effort sketch of
rtmlib's `Body(...)` solution class (callable per-frame, returns (keypoints, scores) arrays),
NOT verified against a live installation -- run
`python -m detector.pose_capture --model rtmpose_halpe26 --dry-run` to confirm the schema/writer
plumbing, then validate this sketch against https://github.com/Tau-J/rtmlib on a machine with
rtmlib installed before trusting its output.
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
            "pip install rtmlib opencv-python (onnxruntime is already available in this repo's "
            "environment). rtmlib downloads RTMPose-m/Halpe-26 ONNX weights automatically on "
            "first use of Body(mode='balanced', ...) -- confirm the exact `mode`/backbone "
            "argument that selects Halpe-26 (vs. plain-COCO) against current rtmlib docs, since "
            "that choice isn't pinned by a model-asset path the way the other two adapters are."
        )

    def infer_frames(self, video_path: Path) -> Iterator[Dict[str, Any]]:
        if not self.is_available():
            raise PoseRuntimeUnavailable(f"{self.pose_model_name}: {self.install_hint()}")

        import cv2
        from rtmlib import Body

        body = Body(mode="balanced", to_openpose=False, backend="onnxruntime", device="cpu")

        cap = cv2.VideoCapture(str(video_path))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        try:
            frame_idx = 0
            while True:
                ok, image = cap.read()
                if not ok:
                    break
                t_ms = int(frame_idx * 1000 / fps)

                keypoints, scores = body(image)  # keypoints: [n_people, 26, 2]; scores: [n_people, 26]

                people = []
                for track_id, (person_kp, person_scores) in enumerate(zip(keypoints, scores)):
                    kp = [
                        [float(x), float(y), None, float(score)]
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
