#!/usr/bin/env python3
"""
evals/gate0/detector/pose_capture/movenet_adapter.py

MoveNet MultiPose Lightning (COCO-17) capture adapter (config.POSE_MODEL_CANDIDATES
"movenet_17"), via TensorFlow Hub's MultiPose Lightning model. Landmark index -> name mapping
lives in detector/keypoint_map.py; this module only runs the model and emits its raw 17-point
output per detected person.

LIVE-TESTED (pose_capture/README.md): confirmed end-to-end against a real video on
tensorflow 2.21.0 / tensorflow-hub 0.16.1. ADR-300 replaced the original SinglePose Thunder
sketch -- SinglePose returns exactly one pose and can't feed subject-lock (RC1) at all. Live-
verified this session:
  - `https://tfhub.dev/google/movenet/multipose/lightning/1` loads via hub.load() (Lightning is
    TF Hub's only MultiPose variant -- there is no MultiPose Thunder, confirmed by checking the
    hub listing rather than assuming).
  - Input must be resized (with letterbox padding) to dimensions that are multiples of 32, cast
    to int32 RGB -- not the fixed 256x256 square SinglePose used.
  - output_0 is shaped [1, 6, 56]: up to 6 person instances, each a 56-vector of 17 keypoints x
    (y, x, score) [note y-before-x, same as SinglePose] followed by a 5-value bounding box
    [ymin, xmin, ymax, xmax, instance_score]. Confirmed live against a single-person frame: 1 of
    6 instance slots scored above the config's instance_score_threshold, the rest near zero.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterator

from detector.pose_capture.base import PoseCaptureAdapter, PoseRuntimeUnavailable

_MODEL_URL = "https://tfhub.dev/google/movenet/multipose/lightning/1"


def _multi_person_config() -> Dict[str, Any]:
    """Reads movenet_17's multi_person_config from config.POSE_MODEL_CANDIDATES (ADR-300) --
    never re-derive/guess the instance-score threshold or instance count here."""
    import gate_config

    for candidate in gate_config.POSE_MODEL_CANDIDATES:
        if candidate["name"] == "movenet_17":
            return candidate["multi_person_config"]
    raise KeyError("movenet_17 missing from config.POSE_MODEL_CANDIDATES")


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
            "pip install tensorflow tensorflow-hub opencv-python; the MultiPose Lightning "
            f"weights ({_MODEL_URL}) download automatically via tensorflow_hub.load() on first "
            "use (needs network access at capture time, not at scoring time). If import fails "
            "with ModuleNotFoundError: pkg_resources, pin setuptools<81 (tensorflow-hub still "
            "depends on it; newer setuptools removed it)."
        )

    def infer_frames(self, video_path: Path) -> Iterator[Dict[str, Any]]:
        if not self.is_available():
            raise PoseRuntimeUnavailable(f"{self.pose_model_name}: {self.install_hint()}")

        import cv2
        import tensorflow as tf
        import tensorflow_hub as hub

        cfg = _multi_person_config()
        instance_score_threshold = cfg["instance_score_threshold"]

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
                h, w = rgb.shape[:2]
                # MultiPose Lightning requires input dims that are multiples of 32; pad rather
                # than distort the aspect ratio (tf.image.resize_with_pad letterboxes).
                target_h = max(32, (h // 32) * 32 or 32)
                target_w = max(32, (w // 32) * 32 or 32)
                input_image = tf.image.resize_with_pad(
                    tf.expand_dims(rgb, axis=0), target_h, target_w
                )
                input_image = tf.cast(input_image, dtype=tf.int32)

                outputs = movenet(input_image)
                # output_0: [1, 6, 56] -- up to 6 person instances, each 17 keypoints x (y, x,
                # score) [y before x] followed by [ymin, xmin, ymax, xmax, instance_score].
                instances = outputs["output_0"].numpy()[0]  # [6, 56]

                people = []
                for track_id, row in enumerate(instances):
                    instance_score = float(row[55])
                    if instance_score < instance_score_threshold:
                        continue
                    keypoints = row[:51].reshape(17, 3)  # (y, x, score) per keypoint
                    kp = [
                        [float(x), float(y), None, float(score)]
                        for y, x, score in keypoints
                    ]
                    ymin, xmin, ymax, xmax = (float(v) for v in row[51:55])
                    box = [xmin, ymin, xmax - xmin, ymax - ymin]
                    people.append({"track_id": track_id, "kp": kp, "box": box})

                yield {"t_ms": t_ms, "pose_model": self.pose_model_name, "people": people}
                frame_idx += 1
        finally:
            cap.release()
