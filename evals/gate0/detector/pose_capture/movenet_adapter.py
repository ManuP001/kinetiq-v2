#!/usr/bin/env python3
"""
evals/gate0/detector/pose_capture/movenet_adapter.py

MoveNet Thunder (COCO-17) capture adapter (config.POSE_MODEL_CANDIDATES "movenet_17"), via
TensorFlow Hub's SinglePose Thunder model. Landmark index -> name mapping lives in
detector/keypoint_map.py; this module only runs the model and emits its raw 17-point output.

NOT RUNNABLE IN THIS REPO'S DEV ENVIRONMENT: `tensorflow` isn't installed here (checked --
ModuleNotFoundError), and there's no recorded video yet either. is_available() correctly reports
False; infer_frames()'s body is a best-effort sketch of the TF Hub SinglePose Thunder API
(256x256 int32 RGB input, output_0 shaped [1,1,17,3] as (y, x, score) per keypoint -- note the
y-before-x order, easy to get backwards), NOT verified against a live installation -- run
`python -m detector.pose_capture --model movenet_17 --dry-run` to confirm the schema/writer
plumbing, then validate this sketch against https://www.tensorflow.org/hub/tutorials/movenet on
a machine with tensorflow installed before trusting its output.

KNOWN LIMITATION, noted rather than silently swallowed: SinglePose Thunder detects exactly one
person per frame. For a `bystander` clip (GOLDEN_SET_PROTOCOL.md §4), a real capture would need a
separate person detector (VISION_ARCHITECTURE.md Stage 1's MoveNet MultiPose or YOLO-pose) to
find each individual's box first, then run Thunder per crop and assemble multiple `people`
entries -- that person-detect step is out of scope for this sketch. Capturing a bystander clip
with this adapter as-is would silently produce only one `people` entry; don't do that without
adding the crop step first.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterator

from detector.pose_capture.base import PoseCaptureAdapter, PoseRuntimeUnavailable

_MODEL_URL = "https://tfhub.dev/google/movenet/singlepose/thunder/4"
_INPUT_SIZE = 256


class MoveNetAdapter(PoseCaptureAdapter):
    pose_model_name = "movenet_17"

    def is_available(self) -> bool:
        try:
            import tensorflow  # noqa: F401
            import tensorflow_hub  # noqa: F401
        except ImportError:
            return False
        return True

    def install_hint(self) -> str:
        return (
            "pip install tensorflow tensorflow-hub opencv-python; the Thunder weights "
            f"({_MODEL_URL}) download automatically via tensorflow_hub.load() on first use "
            "(needs network access at capture time, not at scoring time)."
        )

    def infer_frames(self, video_path: Path) -> Iterator[Dict[str, Any]]:
        if not self.is_available():
            raise PoseRuntimeUnavailable(f"{self.pose_model_name}: {self.install_hint()}")

        import cv2
        import numpy as np
        import tensorflow as tf
        import tensorflow_hub as hub

        model = hub.load(_MODEL_URL)
        movenet = model.signatures["serving_default"]

        cap = cv2.VideoCapture(str(video_path))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        try:
            frame_idx = 0
            while True:
                ok, image = cap.read()
                if not ok:
                    break
                t_ms = int(frame_idx * 1000 / fps)

                rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
                input_image = tf.image.resize_with_pad(
                    tf.expand_dims(rgb, axis=0), _INPUT_SIZE, _INPUT_SIZE
                )
                input_image = tf.cast(input_image, dtype=tf.int32)

                outputs = movenet(input_image)
                # output_0: [1, 1, 17, 3], each row (y, x, score) normalized [0, 1] -- y before x.
                keypoints = outputs["output_0"].numpy()[0, 0, :, :]

                kp = [[float(x), float(y), None, float(score)] for y, x, score in keypoints]
                xs = [pt[0] for pt in kp]
                ys = [pt[1] for pt in kp]
                box = [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)]

                yield {
                    "t_ms": t_ms,
                    "pose_model": self.pose_model_name,
                    "people": [{"track_id": 0, "kp": kp, "box": box}],
                }
                frame_idx += 1
        finally:
            cap.release()
