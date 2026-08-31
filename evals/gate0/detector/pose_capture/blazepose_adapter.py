#!/usr/bin/env python3
"""
evals/gate0/detector/pose_capture/blazepose_adapter.py

BlazePose-33 capture adapter (config.POSE_MODEL_CANDIDATES "blazepose_33"), via MediaPipe's
Pose Landmarker task. Landmark index -> name mapping lives in detector/keypoint_map.py, NOT
here -- this module only runs the model and emits its raw 33-point output in MediaPipe's
standard order; keypoint_map.py is what makes that order legible to the rest of the harness.

NOT RUNNABLE IN THIS REPO'S DEV ENVIRONMENT: `mediapipe` isn't installed here (checked via
`import mediapipe` -- ModuleNotFoundError), and there is no recorded video to run it over yet
either (GOLDEN_SET_PROTOCOL.md's real clips don't exist -- that's the point of this stage).
is_available() correctly reports False here; infer_frames()'s body below is a best-effort sketch
of the real MediaPipe Tasks video-mode API (detect_for_video with monotonically increasing
timestamps, world landmarks for pseudo-3D), NOT verified against a live installation -- run
`python -m detector.pose_capture --model blazepose_33 --dry-run` to confirm the schema/writer
plumbing is correct, then validate this sketch's exact API calls against the current MediaPipe
docs (https://ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker/python) on a machine
that has mediapipe installed before trusting its output.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterator

from detector.pose_capture.base import PoseCaptureAdapter, PoseRuntimeUnavailable


class BlazePoseAdapter(PoseCaptureAdapter):
    pose_model_name = "blazepose_33"

    def is_available(self) -> bool:
        try:
            import mediapipe  # noqa: F401
        except ImportError:
            return False
        return True

    def install_hint(self) -> str:
        return (
            "pip install mediapipe opencv-python; download a Pose Landmarker .task model "
            "(https://ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker#models) to "
            "pose_landmarker.task next to the video; then run this adapter for real."
        )

    def infer_frames(self, video_path: Path) -> Iterator[Dict[str, Any]]:
        if not self.is_available():
            raise PoseRuntimeUnavailable(f"{self.pose_model_name}: {self.install_hint()}")

        import cv2
        import mediapipe as mp

        base_options = mp.tasks.BaseOptions(model_asset_path="pose_landmarker.task")
        options = mp.tasks.vision.PoseLandmarkerOptions(
            base_options=base_options,
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
        )
        cap = cv2.VideoCapture(str(video_path))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        try:
            with mp.tasks.vision.PoseLandmarker.create_from_options(options) as landmarker:
                frame_idx = 0
                while True:
                    ok, image = cap.read()
                    if not ok:
                        break
                    t_ms = int(frame_idx * 1000 / fps)
                    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=image)
                    result = landmarker.detect_for_video(mp_image, t_ms)

                    people = []
                    # world landmarks give pseudo-3D (VISION_ARCHITECTURE.md §2: "3D where
                    # available ... reduces the 2D-projection errors behind RC5").
                    for track_id, pose in enumerate(result.pose_world_landmarks or []):
                        kp = [[lm.x, lm.y, lm.z, lm.visibility] for lm in pose]
                        xs = [lm.x for lm in pose]
                        ys = [lm.y for lm in pose]
                        box = [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)]
                        people.append({"track_id": track_id, "kp": kp, "box": box})

                    yield {"t_ms": t_ms, "pose_model": self.pose_model_name, "people": people}
                    frame_idx += 1
        finally:
            cap.release()
