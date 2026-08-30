"""evals/gate0/detector -- the Stage-1 offline, deterministic, keypoints-only reference
detector (VISION_ARCHITECTURE.md Stages 1/3/4/5b).

This is the harness-side reference implementation the eval gate measures Stage 1 against: it is
NOT the live PWA/JS detector. Porting this algorithm to the live JS path is a documented
follow-on (see the gate0 README), not part of this package. Every module here is pure/stdlib and
operates on already-parsed keypoints (never touches pixels), so it can be unit-tested in
isolation and eventually transliterated 1:1 into the live path.
"""
