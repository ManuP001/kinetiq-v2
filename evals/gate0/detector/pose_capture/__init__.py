"""evals/gate0/detector/pose_capture -- turns a recorded video into a Stage-0-schema
keypoints.jsonl for one candidate pose model (GOLDEN_SET_PROTOCOL.md §6, VISION_ARCHITECTURE.md
Stage 2).

This is deliberately the ONLY non-deterministic, heavy-dependency part of the whole vision
pipeline: real model inference over real video frames. Everything downstream of the
.keypoints.jsonl file this package writes -- golden_loader.py, detector.adapter.run_detector,
every scorer -- is a pure function of that frozen file and stays fully deterministic. See
base.py's module docstring for the adapter interface, and README.md's bake-off section for the
capture workflow and privacy invariant (video never enters the repo).
"""
