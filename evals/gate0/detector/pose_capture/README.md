# detector/pose_capture/ — live-testing notes

Status as of 2026-09-02: all three adapters are **live-tested**, not sketches (CHANGELOG 0.5.0
shipped them as doc-verified sketches only; none had actually run). This file records exactly how
they were verified, the pinned versions, and the platform caveats — read this before trusting a
capture on a new machine.

Verification method (`PARALLEL_PLAN.md` T1-a): each adapter was run through the real
`base.capture_clip()` / `cli.py` path — not a bypassed one-off script — against a throwaway
self-recorded video (never committed; deleted from the capture machine after this smoke test per
`GOLDEN_SET_PROTOCOL.md` §1). Every emitted frame passed `golden_loader.validate_frame_schema()`
inline (the writer raises on the first bad frame, so "N frames written" already means "N
schema-valid frames"). This is a plumbing smoke test, not a bake-off verdict — no golden-set
labels were involved and none of PARALLEL_PLAN.md's blocked threshold/value tuning happened here.

## Environment

Installed in an isolated venv **outside the repo**, at `C:\kv3_posecap` (Windows long-path limits
broke `pip install` for `onnxruntime` at a deeply nested path — recreating the venv at a short
path fixed it; enabling OS-level long-path support was not attempted). Python 3.13.5, Windows 11.

```
mediapipe==1.0.1
tensorflow==2.21.0
tensorflow-hub==0.16.1
rtmlib==0.0.16
onnxruntime==1.29.0
opencv-python==5.0.0.93
opencv-contrib-python==5.0.0.93
numpy==2.5.2
setuptools==80.10.2   # pinned <81 -- see caveat below
```

Full `pip freeze` output kept alongside the venv, not in this repo (throwaway capture-machine
detail, not project state).

### Platform caveats

- **Windows long paths**: if `pip install rtmlib` (or anything pulling `onnxruntime`) fails with
  `OSError: [Errno 2] No such file or directory` deep inside site-packages, the venv's path is too
  long for the Windows default 260-char limit. Recreate the venv at a short path (e.g.
  `C:\kv3_posecap`) rather than nesting it under a long project/temp directory.
- **`setuptools` >= 81 removed `pkg_resources`**, which `tensorflow-hub` still imports at module
  load time (`ModuleNotFoundError: No module named 'pkg_resources'`). Fix: `pip install
  "setuptools<81"`. Produces a `pkg_resources is deprecated` `UserWarning`, not a hard error —
  expected and harmless for this smoke test.
- MediaPipe's `.task` model file is **not committed** and not looked up relative to the repo by
  default — set `KINETIQ_POSE_LANDMARKER_PATH` to its location (see `blazepose_adapter.py`).

## Per-adapter findings

### `blazepose_33` (MediaPipe Tasks PoseLandmarker)

Model: `pose_landmarker_full` (float16), downloaded from
`storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/latest/pose_landmarker_full.task`
(9,398,198 bytes, live-measured — `approx_size_mb: 9.0` in `config.py`).

Two real bugs in the original sketch, found by comparing its code against a live API session
(`help()`/`dir()` introspection, then an actual `detect_for_video()` call) rather than trusting
the sketch's own comments:

1. **BGR fed into an image declared `SRGB`.** `cv2.VideoCapture` reads frames as BGR; the sketch
   passed that directly into `mp.Image(image_format=mp.ImageFormat.SRGB, data=image)` with no
   conversion, silently swapping the red/blue channels the model saw on every frame. Fixed with an
   explicit `cv2.cvtColor(image, cv2.COLOR_BGR2RGB)`.
2. **Wrong landmark set for the schema.** The sketch used `result.pose_world_landmarks` (real-
   world metric coordinates, hip-centred, unbounded/negative) for `kp`/`box`. But
   `EVAL_HARNESS_STAGE0_SPEC.md`'s schema and `detector/subject_lock.py`'s `most_central` rule
   (nearest bbox centroid to frame centre `(0.5, 0.5)`) both assume **frame-normalized [0, 1]**
   coordinates. `result.pose_landmarks` (not `_world_`) is MediaPipe's normalized-image-space
   output and is what the schema actually needs; z is still populated on it (relative, not
   metric). Verified live: `pose_landmarks[0].x/y` ranged inside `[0.25, 0.76]` / `[0.39, 0.75]`
   for a frame with the subject roughly centred — consistent with frame-normalized coordinates,
   `pose_world_landmarks` would not have been.

ADR-300: `num_poses=2` set on `PoseLandmarkerOptions` (default is 1, single-person). Verified live
that this runs without error; the test video has one visible person so only one pose came back,
but the code path structurally supports more.

**Result on the smoke-test video**: 481/481 frames captured, 33 landmarks/person, z populated,
avg **22.6 ms/frame** (capture-machine wall-clock, not on-device).

### `movenet_17` (TensorFlow Hub MoveNet)

ADR-300 replaced the pre-ADR SinglePose Thunder candidate — SinglePose returns exactly one pose,
so it can't feed `subject_lock` (RC1) at all. **MultiPose Lightning** is TF Hub's only MultiPose
variant (no MultiPose Thunder exists — confirmed by checking the TF Hub listing live, not assumed
from memory, after the RTMPose lesson below).

`https://tfhub.dev/google/movenet/multipose/lightning/1` loads via `tensorflow_hub.load()` (a
plain HTTP HEAD/GET against the URL 404s — `hub.load()` uses its own resolution against the
Kaggle-backed model mirror tfhub.dev now proxies to, confirmed by loading it for real). Input must
be letterbox-padded to dimensions that are multiples of 32 (not a fixed 256x256 square). Output
`output_0` is `[1, 6, 56]`: up to 6 person instances, each 17 keypoints × `(y, x, score)` followed
by `[ymin, xmin, ymax, xmax, instance_score]` — verified live against the test video, which has
one visible person: exactly 1 of 6 instance slots scored above `instance_score_threshold` (0.1,
`config.py`'s `movenet_17.multi_person_config` — a structural "is this slot a real detection"
gate, not a Stage-3 form-flagging cutoff, and not tuned against any golden-set data).

**Result on the smoke-test video**: 481/481 frames captured, 17 landmarks/person, z null (correct
for a 2D-only model), exactly 1 of 6 instance slots detected per frame (matching the one visible
person). `capture_meta.json`'s own `avg_latency_ms_per_frame` for this run (70,629ms) is **not a
real number** — it ran concurrently with the `rtmpose_halpe26` capture below on the same machine,
and two heavy CPU-bound ML workloads at once caused severe contention/thrashing. An isolated
8-frame benchmark (no concurrent job) gives the trustworthy figure: avg **1,212 ms/frame** (CPU,
first-call warmup excluded).

### `rtmpose_halpe26` (rtmlib)

The most significant finding of this whole exercise, and exactly the kind of bug this live-testing
task exists to catch. The original sketch used `rtmlib.Body(mode="balanced", ...)` — its own
`install_hint()` already flagged uncertainty here ("confirm the exact mode/backbone argument that
selects Halpe-26"). Live-tested: `Body(...)` returns `keypoints.shape == (n, 17, 2)` — **plain
COCO-17**, not Halpe-26, despite `Body` being the class this candidate's name implies. Inspected
`Body.MODE`'s preset URLs directly (`inspect.getsource`) — all three presets point to `body7`
(COCO) weights. `rtmlib` has a separate class, `BodyWithFeet`, whose own docstring says
"Initialize the Halpe26 pose estimation model" and whose `MODE` URLs contain `-halpe26_`; switched
to it and verified `keypoints.shape == (n, 26, 2)`, with indices 5/6/11/12/15/16 (shoulders/hips/
ankles) landing at near-identical pixel coordinates to `Body`'s COCO-17 output on the same frame —
confirms `keypoint_map.py`'s "indices 0-16 = COCO-17 order" documentation is correct once the
right class is used.

Both `Body` and `BodyWithFeet` are top-down (bundled YOLOX person detector + per-box pose), so
this candidate is natively multi-person per ADR-300 — no separate `person_detector` wiring was
needed in the adapter itself, though `config.py` records `person_detector: "yolox (rtmlib-bundled,
runs internally)"` so the bake-off's latency/size comparisons can account for it (ADR-300's
"latency comparisons must include the detector's cost for top-down stacks").

A second bug, same root cause (trusting the sketch instead of checking live): rtmlib returns
**pixel coordinates in the source frame's own resolution**, not normalized `[0, 1]` — confirmed
live on an 850×478 frame: raw x/y values ranged up to ~478/~850. Like `blazepose_33`'s bug above,
this breaks `subject_lock.py`'s frame-normalized assumption; fixed by dividing x by frame width
and y by frame height before emitting. Verified live post-fix: x/y both land inside `[0, 1]`
(e.g. `x ∈ [0.20, 0.79]`, `y ∈ [0.37, 0.87]` for a centred subject).

**Latency**: substantially slower than the other two — an isolated 8-frame benchmark (no
concurrent job) gives ~500–1,100ms/frame (CPU, `onnxruntime`), so a 481-frame clip takes roughly
5-6 minutes to capture, not a few seconds. This is not a bug, just the cost of a top-down
detector+pose stack on CPU; batch capture scripts/CI should budget for it.

**Result on the smoke-test video**: 481/481 frames captured, 26 landmarks/person, coordinates
normalized to `[0, 1]` post-fix. `capture_meta.json`'s own `avg_latency_ms_per_frame` for this run
(51,015ms) is **not a real number**, for the same reason as `movenet_17` above — this capture ran
concurrently with it on the same machine. Trust the isolated benchmark figure instead.

## Known caveat not fixed here (out of scope for this smoke test)

`movenet_17`'s `kp`/`box` coordinates are normalized to the **letterbox-padded input**
(`tf.image.resize_with_pad`'s output), not corrected back to the original frame's own aspect
ratio. For a non-square source video (the smoke-test clip is portrait, 478x850) this introduces a
small systematic offset between MoveNet's normalized coordinates and the frame-normalized space
`blazepose_33` and `subject_lock.py`'s `(0.5, 0.5)` centre assumption use. This didn't break
schema validity or this smoke test's goal, and correcting it is a numeric-precision fix, not a
plumbing one — left as a follow-up rather than folded into this pass (`PARALLEL_PLAN.md` blocks
threshold/value tuning until real golden-set data exists; this is adjacent to that same
discipline: don't hand-tune geometry without a labeled clip to check it against).
