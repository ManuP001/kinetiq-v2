"""evals/gate0/prototype_api -- a thin FastAPI wrapper around the eval-validated run_detector
(evals/gate0/detector/adapter.py). Step 1 of the live-vision-prototype build
(VISION_ARCHITECTURE.md).

ONE detector, two consumers: this service imports and calls run_detector; it must never
reimplement or fork a detection rule. See main.py's module docstring and test_parity.py, which
proves the API's result for a given frame sequence is identical to calling run_detector directly.

NOT the full /v2 product API (no auth, no DB, no persistence beyond an in-memory per-process
session buffer) and NOT Stage-6 coaching (cues.py is explicitly interim). See README.md for the
request/response contract and how to run this locally.
"""
