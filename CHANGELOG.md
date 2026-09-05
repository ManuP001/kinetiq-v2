# CHANGELOG — Kinetiq v2

All notable changes to the Kinetiq v2 build are recorded here.
Format is loosely based on [Keep a Changelog](https://keepachangelog.com/).

---

## [0.8.1] — 2026-09-05 — spec-conformance audit: exercise-contract shape reconciled

Part of the "make the codebase provably derive from the markdown spec" pass. The audit itself is
`../kinetiq v3/CODE_SPEC_MAP.md`; this entry covers the one **code/data** change it justified.
No behaviour change: 290 tests pass (unchanged count) and `aggregate.py --golden golden/ --mode full`
still reports `Stage 0 gate: PASS`.

### Fixed — `exercises/{squat,pushup,lunge}.json` conform to EXERCISE_LIBRARY.md §4

All three declared `schema_version: 2` but were missing three fields §4 requires and that all 11
newer contracts already carry (they were left untouched when the 11 were authored in 0.7.0):

- `tier: "A"` — directly from `EXERCISE_LIBRARY.md` §3's table, which places all three in Tier A.
- `movement_type: "rep"` — all three are rep-counted, not timed holds.
- `vision_support: false` — §4's rule is `false` until the exercise passes its own eval bar, and
  §1 states vision-live count is still 0 pending re-proof under the v3 engine. **`false` is both the
  spec-correct value and the gate-respecting one**; setting `true` here would have violated GATE
  G-REAL.

Field order matches the conformant siblings exactly, so all 14 contracts are now one shape.
**Verified inert:** a search across `evals/`, `backend/`, and `kinetiq-demo3` found **no** reader of
`tier`, `movement_type`, or `vision_support` — these are contract metadata today, so adding them
cannot alter detector or prototype behaviour. Checked before editing, precisely because
`vision_support` is the kind of field that *could* have gated the prototype's supported-exercise list.

### Audited, conformant, unchanged

`config.py`'s 8 Stage-0 gate floors (exact spec names); zero restated floor literals anywhere in the
harness (closing `EVAL_HARNESS_STAGE0_SPEC.md` §11's last explicitly-open item); `detector/`'s Stage
1–3 modules against `VISION_ARCHITECTURE.md`; `keypoint_map.py` as §11's "missing" keypoint mapping;
`scorers/`'s five modules and §6's two deliberate edge cases; `prototype_api`'s no-pose-runtime and
in-memory-only properties; and one-detector-two-consumers (`run_detector` defined once, imported by
`prototype_api/main.py`, `golden_loader.py`, `effectiveness_report.py`).

### Surfaced, not resolved

Five code↔doc disagreements are listed as open decisions in `CODE_SPEC_MAP.md` rather than guessed at
— notably **squat has no torso-lean fault** despite three docs saying it should, and **no CI config
exists** to run the regression gate `EVAL_STRATEGY.md` §4 calls "the part v1/v2 never had".

## [0.8.0] — 2026-09-04 — live-prototype run scripts + Render deploy verification

Stands the already-built live prototype up two ways for GATE G-REAL: locally with a real webcam,
and on Render over public HTTPS. **Run-scripts, deploy configs and docs only** -- no detector,
behavior, or test change (290 tests pass, same count as 0.7.0). One-detector-two-consumers intact:
both paths run the same `run_detector`, nothing was reimplemented.

### Added

- `evals/gate0/prototype_api/run_local.ps1` (+ `run_local.sh` twin) -- one command to run the whole
  prototype locally: starts `prototype_api` on `localhost:8000` and serves the sibling
  `kinetiq-demo3` repo on `localhost:8080`, sets `PROTOTYPE_API_CORS_ORIGINS` to the PWA's local
  origin, waits for `/health`, prints the URL, and stops both on Ctrl+C. Allows **both**
  `localhost` and `127.0.0.1` forms of the origin, since those are different origins to the browser
  and picking the "wrong" one is an otherwise-baffling CORS failure. `http://localhost` is a secure
  context, so the camera works and there's no mixed content -- no HTTPS or cloud account needed.
- `evals/gate0/prototype_api/README.md`: a "Running the whole prototype locally (real webcam)"
  section -- click-by-click session steps and the exact `effectiveness_report.py` command to score
  the exported bundle. Its deploy section now leads with **Path R (Render)** as the global path,
  keeping the cloudflared tunnel as the same-network quick option.

### Verified

- **The Dockerfile's COPY set is complete** -- checked by staging its exact `COPY` lines into a
  clean tree (nothing else present) and running the literal container `CMD` against it:
  every module `run_detector` transitively imports resolves; `gate_config.py`'s
  `parents[2]/"backend"` and `config.py`'s `parents[3]/"exercises"` both land correctly at the
  container layout (all 14 exercise contracts load, and `EXERCISE_LIBRARY_DIR` demonstrably pointed
  into the *staged* tree, not the real repo); `check_local.sh` passes against it. Two negative
  controls confirm the test isn't vacuous -- removing `backend/app/core/` breaks the import, and
  removing `exercises/` produces the `/health`-lies behaviour described below.
- `uvicorn`'s console script puts the CWD on `sys.path` (`--app-dir` defaults to `""`, and `run()`
  does `sys.path.insert(0, app_dir)`), so the `CMD`'s bare `prototype_api.main:app` resolves under
  `WORKDIR /app/evals/gate0`. Confirmed against the **installed uvicorn 0.35.0** -- the exact
  version `requirements.txt` pins -- not from memory. This matters because the container uses the
  `uvicorn` console script while local dev uses `python -m prototype_api`; different sys.path paths.
- The local run end-to-end through a real browser (Playwright, fake camera + stubbed MediaPipe):
  PWA served from `localhost:8080` -> **browser-enforced** CORS -> 9/9 successful
  `POST /prototype/assess`, zero page errors. curl cannot prove this; curl isn't subject to CORS.

### NOT verified (stated rather than assumed)

- **An actual `docker build` was never run.** Docker Desktop isn't installed on this dev machine and
  installing it needs admin/UAC + WSL2 + likely a reboot -- not completable unattended. The base
  image and `pip install` layer are therefore unproven; everything the Dockerfile's own
  `COPY`/`WORKDIR`/`CMD` lines control is proven by the staging test above. The exact command to
  prove the rest locally is in `prototype_api/README.md`.

### Surfaced, not fixed (out of scope -- would be a detector-side behavior change)

- **`/health` can report a broken image as healthy.** `load_exercise_library()` globs
  `EXERCISE_LIBRARY_DIR` and returns `{}` for a missing directory instead of failing loudly. So an
  image built without `exercises/` still boots and answers `GET /health` **200 OK**, while every
  `POST /prototype/assess` returns **500** -- and Render's `healthCheckPath: /health` would call
  that service healthy. Mitigated in the docs by making `check_local.sh` (whose second step is a
  real assess round-trip) the mandatory post-deploy check, not a browser hit on `/health`. Worth
  revisiting against `CLAUDE.md`'s "fail loudly" standard when detector-side changes are in scope.

### Not changed

- `Dockerfile`, `.dockerignore`, root `render.yaml` -- reviewed and verified as above; correct
  as-committed, no edit needed.
- `detector/`, `prototype_api/` request handling, `exercises/*.json`, and every test -- untouched.

## [0.7.0] — 2026-09-03 — v3 Stage 5a: 11 new exercise contracts (preponed, still gated)

Kinetiq v3 Stage 5a, run in parallel with GATE G-REAL per the task brief: authors the exercise
CONTRACT JSON for the 11 requested exercises beyond squat/pushup/lunge
(`../kinetiq v3/EXERCISE_LIBRARY.md` §3's 14-exercise table). **Spec/data only** -- no detector
change, no new landmark, nothing goes vision-live. `detector/exercise_signals.scoped_exercises()`
(the Stage-1 detector's real scope) and `prototype_api`'s `SUPPORTED_EXERCISES` both remain exactly
`(squat, pushup, lunge)`, unchanged and unaffected by these 11 files existing -- verified live, not
assumed.

### Added

- `exercises/{pull_up,plank,leg_raise,hanging_leg_raise,overhead_press,arnold_press,bicep_curl,
  triceps_pushdown,hamstring_curl,bench_press,deadlift}.json` -- one contract each, same shape as
  the existing 3 (`schema_version: 2`, `reference_keypoints.correct.key_angles` +
  `common_errors[]`, `thresholds`, `rep_counting`, `coaching_cues`, `contraindications`,
  `model_assist`), extended with the v3-only fields `EXERCISE_LIBRARY.md` §4 calls for:
  `tier` (A/B/C), `movement_type` (`rep` | `hold`), `vision_support: false` on all 11.
  `camera_guidance` (also named in §4) is deliberately NOT added -- not in the build task's
  explicit field list and not present on the existing 3 either.
- All 14 exercises now load via `config.load_exercise_library()`; every fault on every one of the
  11 new files carries a valid severity and normalizes through `exercise_lib.py`'s existing
  `medium` -> `med` alias (not re-decided here, per the build task).
- Every `good_rep` and `flag_cues` entry across all 11 is <= `LIVE_CUE_MAX_WORDS` (8), counted the
  same way `prototype_api/cues.py` and `aggregate.py`'s Stage-0 assertion already do -- caught and
  fixed one over-cap draft (`bench_press.depth`, originally 9 words) before it became a second
  instance of the already-known `squat.shallow_depth`/`pushup.shallow_pushup` mistake (those two
  remain as-is; out of scope for this release).
- **5 faults marked `status: "needs_pt_confirmation"`** (severity `high`, no threshold value
  seeded -- `null` in `thresholds`, not invented) rather than guessing a safety-relevant geometric
  rule, mirroring `lunge.json`'s existing `unresolved_spec_conflict` pattern:
  `deadlift.lumbar_flexion`, `bench_press.excessive_lumbar_arch`,
  `bench_press.excessive_elbow_flare`, `overhead_press.lumbar_hyperextension` (all named
  explicitly in the build task), plus `arnold_press.lumbar_arch` (not named in the task, but the
  identical injury mechanism as `overhead_press` -- extended the same treatment deliberately rather
  than guessing a threshold for one press variant and not its close relative; flagged for review).
- Two landmark-availability gaps, noted rather than papered over with an invented landmark:
  `plank`'s "neck alignment" key fault (`EXERCISE_LIBRARY.md` §3) has no common_error entry --
  there is no head/neck landmark in `detector/keypoint_map.py`'s `POSE_MODEL_LANDMARKS`.
  `arnold_press`'s "rotation path" likewise has none -- the Stage-0 keypoint schema carries
  landmark position (x/y/z/visibility) only, not wrist/forearm orientation.
- One structural note for whoever scopes Stage 5b: `triceps_pushdown`'s primary joint-angle signal
  moves in the OPPOSITE direction from every other exercise here (its rest reference is elbow
  FLEXED, its effort peak is full extension) -- the generic rep-counter FSM
  (`detector/rep_counter.py`) assumes rest=peak-angle/effort=trough-angle, so this one will need an
  inverted signal, not a straight port of the squat/pushup pattern. Documented in the file's own
  `rep_counting._note`, not solved here (Stage 5b is out of scope for this release).

### Not changed

- `exercises/{squat,pushup,lunge}.json` -- untouched.
- `detector/exercise_signals.py`, `prototype_api/`, and every other consumer of the Stage-1
  detector -- untouched; still scoped to squat/pushup/lunge only.
- `backend/app/core/schemas.py`'s `ExerciseId` (currently `Literal["squat", "pushup", "lunge"]`)
  -- deliberately left alone. Expanding it is product-API/backend wiring (whenever `/v2`'s backend
  scaffold actually gets built, `PARALLEL_PLAN.md` T3-a), not contract authoring, and touching it
  would read as a step toward these exercises going live, which this release explicitly is not.

## [0.6.0] — 2026-09-01 — v3 Stage 3: flag-level hysteresis + visibility gating

Kinetiq v3's Stage 3, re-scoped per the task brief: `ROADMAP.md`'s literal Stage-3 entry (rep-
counter smoothing/hysteresis/tempo/graded-depth) was already built in Stage 1
(`evals/gate0/detector/rep_counter.py`, untouched here). This release is the missing RC4 piece --
SPRINT.md G2 "precision-first flagging", the direct fix for the field hip-sag false positive: a
form flag now attaches to a rep only when the fault is SUSTAINED across a large-enough fraction of
the rep's frames, and is never evaluated on frames where its own involved landmarks are too low
visibility.

### Added

- `detector/flag_hysteresis.py`: `evaluate_sustained_flag()` re-evaluates a fault rule across
  every frame in a rep's window and only returns PRESENT once the fault held true for a
  severity-keyed fraction of the frames where it could be judged at all (below
  `FLAG_MIN_EVALUABLE_FRAMES` evaluable frames: `INSUFFICIENT_EVIDENCE`, surfaced, never silently
  dropped). Covers the 5 per-frame, landmark-based flags (`knee_cave_left/right`,
  `shallow_depth`, `elbow_flare`, `hip_sag`); `shallow_pushup`/`shallow_lunge` are rep-aggregate
  (compared against the rep's already-smoothed overall minimum angle) and untouched.
- `detector/faults.py`: every per-flag predicate now takes an optional `min_visibility`
  parameter (default `None` = Stage-1 behaviour, unchanged) so the SAME per-side loop serves both
  a plain rule check and flag_hysteresis.py's visibility-gated evaluation -- avoids a second,
  independently-maintained "which side is visible" check that could disagree with the rule's own.
  The old single-frame aggregate functions (`squat_faults`/`pushup_faults`/`lunge_faults`) are
  removed (nothing but `adapter.py` called them, and it no longer does); replaced by the granular
  predicates plus two focused rep-aggregate predicates (`shallow_pushup_present`,
  `shallow_lunge_present`).
- `detector/adapter.py`: `run_detector` now evaluates the 5 sustained flags across each rep's
  `[start_ms, end_ms]` window instead of a single deepest-point frame, and reports
  `insufficient_evidence` per rep alongside `flags`. A bottom-phase-only fault (squat's
  `shallow_depth`, per its own `phase_detected_in` in `exercises/squat.json`) is narrowed to the
  bottom fraction of *that rep's own excursion range* (`FLAG_BOTTOM_PHASE_FRACTION`) rather than
  the exercise's correct-depth threshold -- a real bug caught while building this: a naive
  whole-rep window flagged `shallow_depth` on every rep, clean ones included, since
  standing/mid-descent legitimately isn't "at depth" yet.
- `backend/app/core/config.py`: `FLAG_MIN_VISIBILITY`, `FLAG_MIN_EVALUABLE_FRAMES`,
  `FLAG_HYSTERESIS_MIN_FRACTION_{HIGH,MED,LOW}_SEV`, `FLAG_BOTTOM_PHASE_FRACTION` -- all
  PLACEHOLDER values pending real golden-set tuning (`GOLDEN_SET_PROTOCOL.md` §8), clearly marked
  as such. Single source of truth, imported via `gate_config.py`.
- Three new synthetic golden clips proving the mechanism end-to-end through the harness (not just
  unit tests over synthetic frame lists): `pushup_noisy_hipsag_side_001` (one noisy frame, must
  NOT flag -- the exact field bug), `pushup_sustained_hipsag_side_001` (genuine sustained sag,
  must flag -- recall holds), `pushup_lowvis_hipsag_side_001` (hip landmark below
  `FLAG_MIN_VISIBILITY` throughout, must read insufficient evidence, never a confident
  accusation).
- `aggregate.py --mode full`: new "Insufficient evidence" report section, surfacing any sustained
  flag the detector couldn't judge either way -- doesn't count as a false accusation or a miss in
  the precision/recall table, but isn't nothing either.

### Decision surfaced (not silently guessed)

- **Hysteresis unit**: fraction of a rep's evaluable frames, not a fixed frame count -- confirmed
  with the user (fps-robust: consistent across devices/frame rates, which matters once real
  multi-device capture is in the mix, vs. a frame count tuned to one capture rate).

### Verified

`squat_badform_001`'s clean reps (1, 3) no longer show a false `shallow_depth` (the bug this
release's bottom-phase fix corrects); the seeded knee-cave reps (2, 4) still flag correctly.
`pushup.hip_sag` on the golden set: precision 100%, recall 100% (tp=1, fp=0, fn=0) -- the noisy
clip contributes a clean true-negative, the sustained clip a true-positive, and the low-visibility
clip contributes neither (insufficient evidence, not scored either way). 208 unit tests pass;
deterministic (verified bit-identical across two full runs); `--data`, `--mode fast/full`, and
`--compare-pose-models` all unaffected.

## [0.5.0] — 2026-08-31 — v3 Stage 2: pose-model bake-off tooling

Kinetiq v3's Stage 2 (`../kinetiq v3/VISION_ARCHITECTURE.md` Stage 2, `ROADMAP.md`): the tooling
that turns "which pose model?" into a measured table (Ch 39: "religion into measurement"), not a
decision made here. **The tooling only** -- the real verdict is deferred to when
`GOLDEN_SET_PROTOCOL.md` §8's bake-off-minimum clips (~23, real recordings) exist; this release
runs end-to-end on one synthetic multi-model clip to prove the mechanism is correct.

### Added

- `backend/app/core/config.py`: `POSE_MODEL_CANDIDATES`, the single-source registry of bake-off
  candidates (name, landmark count, 2D/3D, runtime, weights ref, approx size) -- both the capture
  tool and the harness iterate this; no model name is hardcoded elsewhere.
- `detector/keypoint_map.py`: extended to `rtmpose_halpe26` (RTMPose-m, Halpe-26 -- chosen over
  plain-COCO RTMPose specifically for its extra head/neck/hip/toe/heel points, closer to
  BlazePose's richness) and `blazepose_33`/`rtmpose_halpe26` heel/toe landmarks (for a future
  lunge toe-position rule). Indices verified against published MediaPipe BlazePose and
  AlphaPose/mmpose Halpe-26 orderings, not invented.
- `evals/gate0/golden_loader.py`: `load_golden_poses(golden_dir, pose_model)` -- discovers clips
  by scanning `golden/poses/<model>/` directly (GOLDEN_SET_PROTOCOL.md §2), independent of
  `MANIFEST.json`'s flat-clip list, so it never touches or affects `--mode fast/full`.
  `load_capture_meta()` reads a capture's optional latency/environment stats. Shared
  `validate_frame_schema()` extracted so the loader and the capture tool enforce identical rules.
- `evals/gate0/aggregate.py`: `--compare-pose-models` runs the Stage-1 detector once per
  candidate over `golden/poses/<model>/` and prints one table (clips, rep-accuracy,
  no-phantom-reps, subject-lock, pooled form precision/recall, latency, size). Exits non-zero
  only on a malformed golden set, never because one model scores worse than another; never prints
  a winner.
- `detector/pose_capture/`: the capture tool (GOLDEN_SET_PROTOCOL.md §6). `base.py`'s
  `PoseCaptureAdapter` interface + `capture_clip()` writer isolate real (non-deterministic)
  model inference from everything else, which stays deterministic. Three adapter sketches
  (`blazepose_adapter.py`, `movenet_adapter.py`, `rtmpose_adapter.py`) -- **none of the three
  runtimes (mediapipe/tensorflow/rtmlib) are installed in this repo's dev environment**, so each
  is a best-effort, doc-verified-but-not-live-tested sketch; `dry_run_self_test()` proves the
  schema/writer plumbing without needing the runtime or a video, and never fabricates keypoints
  as real data. `python -m detector.pose_capture --list/--dry-run/--model ...` is the CLI.
- `golden/poses/{blazepose_33,movenet_17,rtmpose_halpe26}/squat_bakeoff_side_001.keypoints.jsonl`:
  one synthetic clip, same physical motion emitted under each model's own landmark indices --
  proves `run_detector` produces identical output regardless of which model captured an
  equivalent skeleton.

### Decisions surfaced (not silently guessed)

- **RTMPose variant**: RTMPose-m on Halpe-26 (26 keypoints), chosen over plain-COCO RTMPose for
  the extra skeletal richness -- confirmed with the user rather than assumed.
- **Latency measurement**: capture-machine wall-clock timed around each frame's inference call,
  explicitly labeled as not representative of on-device mobile performance -- confirmed with the
  user rather than deferred silently or fabricated.

## [0.4.0] — 2026-08-30 — v3 Stage 1: subject-lock + rep-validity gate detector

Kinetiq v3's Stage 1 (`../kinetiq v3/VISION_ARCHITECTURE.md`, `ROADMAP.md`): the offline,
deterministic, keypoints-only reference detector that kills the two worst field failures --
a moving bench counting reps (RC2) and the skeleton jumping to a bystander (RC1). Lives in
`evals/gate0/detector/`; measured by the Stage-0 harness (`evals/gate0/`, added in the v3 work
this entry follows).

### Added

- `detector/subject_lock.py` -- picks one subject at session start (config: largest bbox /
  most-central), tracks that identity by track_id with position-based re-identification when the
  stream's own ids are unstable, and PAUSES (never silently retargets) after
  `SUBJECT_LOST_FRAMES_THRESHOLD` consecutive missed frames.
- `detector/plausibility.py` -- the Stage-3 rep-validity gate's human-plausibility check
  (visible-landmark fraction + shin:thigh limb-ratio band). Independent of subject-lock: a
  false-positive person box (e.g. a bench) can be locked onto, but every frame of it is still
  rejected here.
- `detector/rep_counter.py` -- a median-smoothed, hysteresis-gated valley-detection FSM over the
  exercise's primary joint angle, with a minimum-excursion floor (noise vs. a real rep attempt)
  and a plausible-tempo band (`MIN_REP_DURATION_MS`/`MAX_REP_DURATION_MS` -- a slow 3-0-1-0 rep
  must still register). Depth is graded (partial reps count, at a lower score), not thresholded.
- `detector/faults.py`, `detector/exercise_signals.py`, `detector/keypoint_map.py` -- the
  existing deterministic form-flag rules transliterated from each exercise's own
  `common_errors[].keypoint_signature.rule` string (unchanged semantics -- Stage 1 doesn't tune
  or add fault logic, that's Stage 4/5), plus the COCO-17/BlazePose-33 keypoint-name mapping the
  Stage-0 spec flagged as missing (scoped to the landmarks squat/pushup/lunge actually need).
- `detector/adapter.py` -- `run_detector(keypoints_stream, exercise_id, config) -> DetectedClip`,
  the offline detector adapter deferred by `EVAL_HARNESS_STAGE0_SPEC.md` §12. Deterministic (same
  input -> same output); never sees golden-set ground truth. Subject-lock accuracy against a
  clip's *expected* subject is graded separately, by the harness
  (`score_subject_lock_against_expected`) -- a real detector has no "expected" identity to cheat
  from, only the one it locked onto.
- `backend/app/core/config.py` -- Stage-1 gate floors/tunables (subject-lock selection rule and
  thresholds, plausibility thresholds, tempo band, rep-counter smoothing/hysteresis/excursion,
  graded-depth scoring). Single source of truth, imported via `gate_config.py` like the Stage-0
  floors.

### Changed

- `evals/gate0/golden_loader.py`: `detected.json` is now RECOMPUTED from frozen keypoints via
  `run_detector` for any exercise Stage 1 supports (squat/pushup/lunge) -- reproducible, not
  hand-authored or live-captured. Falls back to reading a pre-existing `<clip_id>.detected.json`
  only for an exercise the detector doesn't support yet (none currently in the golden set; kept
  for a future Tier A/B/C clip added before its own detector logic lands).
- `evals/gate0/golden/`: the synthetic fixture's keypoints were regenerated with real,
  angle-driving motion (the Stage-0 fixture's near-constant dummy values didn't exercise a real
  phase signal) and extended with the clips Stage 1's exit gate needs:
  `pushup_phantom_empty_001` (nobody in frame, distinct from the bench-misdetection story),
  `squat_partial_depth_001` (graded, still-counted shallow reps), `pushup_slow_tempo_001` (a
  deliberately slow rep). `squat_bench_phantom_001` now models the actual failure mode -- a
  low-confidence, implausible "person" detection -- rather than an empty frame.

### Verified (Stage 1 exit gate, `ROADMAP.md`)

On the synthetic golden set via `python aggregate.py --golden golden/ --mode full`: 0 reps on
`phantom_bench`/`phantom_empty`/`bystander` clips; 100% subject-lock on the multi-person clip
(floor 99%); rep-count accuracy 100% on squat and pushup (matching the Stage-0 baseline, which
was hand-authored to already equal ground truth -- Stage 1's 100% is the same number now produced
by an actual algorithm reading keypoints, not restated fiction) and 100% on lunge (no Stage-0
baseline existed for it). `run_detector` is deterministic (unit-tested); 131 unit tests pass
across `evals/gate0/`.

### Fixed — kinetiq-demo2/index.html

- **Flag leakage across aborted rep attempts:** `flag()` used to write directly into the
  permanent per-set `S.flags` tally the moment a bad-form check fired, even during a rep attempt
  that was later discarded for being too short (`dur < minRepDurationMs`, a noise blip rather
  than a real rep). This inflated flag counts / depressed form score for reps that never
  actually counted. `flag()` now only marks the current attempt (`S.flaggedThisRep`); `closeRep()`
  commits those flags into `S.flags` only once the rep has actually counted.
- **Squat knee-cave check replaced:** the previous check used an invented ratio heuristic
  (`kneeSep/ankleSep < 0.7`) that matched neither `exercises/squat.json` nor the Vision_Contract
  sheet, despite a code comment claiming it mirrored both. Replaced with the JSON/xlsx-agreed
  per-side x-deviation rule (`knee_cave_x = 0.05`), split into distinct `knee_cave_left` /
  `knee_cave_right` flags with per-side cues, matching the Exercise Library contract.
- **lunge torso-lean threshold was wrong:** `torsoLeanMaxDeg` was 25 in the demo; both
  `exercises/lunge.json` and the Vision_Contract sheet say 20. Fixed.

### Changed — threshold reconciliation (xlsx is now canonical)

`exercises/*.json` and the `Vision_Contract` sheet of `Kinetiq_Exercise_Library_v2.xlsx`
disagreed on several numeric thresholds. Decision: the xlsx is canonical — it's the newer,
curated dataset that replaced the old placeholder spreadsheet (see the 0.2.0 entry below).
`exercises/{pushup,lunge}.json` and `kinetiq-demo2/index.html`'s `CONFIG` were updated to match
it (`exercises/squat.json` already matched, no change needed there):

- pushup `elbow_flare_deg`: 75 → 60. `shallow_elbow_deg` renamed `depth_elbow_angle_max`: 100 → 95
  (also updated `reference_keypoints.correct.key_angles.elbow_angle_at_bottom.max`: 100 → 95).
  pushup's hip-sag check switched from a y-distance rule (`hip_sag_y`) to the xlsx's angle-based
  rule (`hip_sag_angle_min = 160`), matching what the demo actually computes.
- lunge: added `torso_lean_max_deg = 20` to the `thresholds` block (previously only present as a
  reference value under `key_angles`, missing from the enforced thresholds entirely — this gap
  is why the demo's wrong value of 25 went uncaught). `shallow_lunge`'s rule switched from a
  back-knee-height metric (`lunge_depth_y`) to the xlsx's front-knee-angle metric
  (`front_knee_angle_bottom_max = 100`), matching what the demo actually computes.

### Open item — lunge's second knee-safety check (not implemented)

`exercises/lunge.json` specifies two checks — `front_knee_cave` (x-axis deviation, threshold
0.05) and `front_knee_overextend` (z-axis deviation, threshold 0.08) — both `severity: high`
(knee injury risk). The Vision_Contract sheet specifies one check instead — `knee_past_toe`
(x-axis deviation, threshold 0.06) — matching neither the name nor the value of either JSON
check. This is a three-way conflict on a safety-relevant rule; guessing at the correct physical
semantics isn't safe. **Not implemented** in `kinetiq-demo2` pending resolution. The two JSON
error entries are marked `"status": "unresolved_spec_conflict"` with an explanatory
`status_note`, and their thresholds remain in `exercises/lunge.json`'s `thresholds` block
unchanged (`knee_cave_x`, `knee_overextend_z`) — not deleted, just not wired into the vision
spike. **Needs:** a trainer/PT to confirm which rule (or a corrected third one) is physically
correct before this is built. Lunge currently only flags `shallow_depth` and
`excess_torso_lean`.

### Added

- `kinetiq-demo2/render.yaml`, `kinetiq-demo2/netlify.toml` — no-build static-site deploy
  configs, so the spike can be opened over HTTPS on Android test devices. Neither folder is
  currently a git repo; README.md documents the drag-and-drop fallback (e.g. Netlify Drop) for
  a one-off test round without setting up git first.
- **Lighting-condition capture:** the Gate 0 protocol requires exercise x device x lighting
  matrix coverage, but nothing captured lighting before this — it wasn't in the export schema at
  all. Added a 3-way select (daylight / indoor evening / dim room) to the validate screen;
  exported records now include a `lighting` field.
- `kinetiq-v2/evals/gate0/` — new eval harness: `aggregate.py` ingests the JSON files
  `kinetiq-demo2` exports, computes weighted rep accuracy per exercise (same formula the PWA
  itself uses) against the 90% Gate 0 bar, and prints device x lighting matrix coverage against
  the protocol (>=5 devices x 3 lighting conditions, >=3 sets of 8-12 reps per cell). Exits
  non-zero on fail. `README.md` documents the export → aggregate workflow. `data/` (gitignored)
  holds local device exports.
- `backend/app/core/config.py` — named constants promised by CLAUDE.md §3 and listed as "open"
  in the 0.2.0 entry below: model-tier config keys (`HOT_PATH_MODEL`/`COACHING_MODEL`/
  `PLANNER_MODEL`/`MEMORY_MODEL`), latency budgets, coaching cue caps and confidence threshold,
  streak rules (timezone, reset window, milestones, freeze), PR rule, notification defaults,
  session-duration options, fitness-level default sets/reps, free-tier exercise list, and the
  Gate 0 target accuracy (imported by `evals/gate0/aggregate.py` so both share one source of
  truth). Deliberately does **not** hand-copy per-exercise thresholds — `load_exercise_library()`
  reads `exercises/*.json` at runtime instead, to avoid the exact kind of threshold drift fixed
  above. A few constants (model-assist confidence fallback, per-tier `max_tokens`) aren't
  specified anywhere in the docs; they're placeholders with an explicit "revisit" comment rather
  than a confident-looking number.

---

## [0.2.0] — 2026-07-06 — contradiction fixes, Gate 0, real exercise dataset

### Fixed — documentation contradictions (ADRs 108–110)

- **v1 evidence corrected** (`BRD.md` §2, `CLAUDE.md` §0): v1 was a no-camera PWA UX demo; the claim
  that it "validated on-device camera rep counting" was false. Camera vision is now explicitly
  unproven and gated behind **Gate 0** — the `kinetiq-demo2` camera spike must hit >90% rep accuracy
  on ≥5 real mid-range Android devices before Phase-1 backend build (ADR-110).
- **Streak-at-risk push pulled into Phase 1** (ADR-108): PRD_v2 §7.1 made it the only MVP cue while
  the stack table had FCM in Phase 3. FCM now ships in Phase 1, scoped to that single daily push.
- **Offline-first hot path** (ADR-109): the deterministic layer (rep count, safety flags, base score,
  static cues) is fully on-device; `POST /assess` redefined as a batched, non-blocking upload at set
  boundaries. A session completes with zero network. Latency table and data flow updated.
- **Onboarding canon** (ADR-110): Screen 3 = health context + equipment + preferred time/duration,
  single screen; PRD_v2 §8.2/§8.3 ambiguity ("or as a standalone screen") removed.

### Changed — dataset

- Replaced `Phase1_Fitness_Database_Full_Mapped_Updated.xlsx` (100% placeholder rows: generic
  exercise/food names, 3 distinct programming tuples, constant nutrition targets, and an
  out-of-scope nutrition database) with `Kinetiq_Exercise_Library_v2.xlsx` — real, curated,
  exercise-only data conforming to the Exercise Library contract (CLAUDE.md §6), including video
  metadata, contraindication flags, and vision-support status per exercise.

### Added

- `../kinetiq-demo2/` — Gate 0 camera PWA: real on-device MediaPipe pose, deterministic rep counting
  + form flags for squat/push-up/lunge, config-driven thresholds, positive-first cues, and a
  built-in accuracy-validation mode (human count vs. detected count, exportable results).

---

## [0.1.0] — 2026-06-21 — v2 foundation (docs + schema layer)

The initial v2 scaffold: a docs + schema foundation for the next-version build. No application
code — this is what Claude Code builds *from*. It reads the v1 repo (`../kinetiq`) for context and
treats `PRD_v2.md` as a **baseline to question**, not a frozen spec.

### The mandate

Build **behaviour by phase, but the full schema and contracts now.** v1's expensive mistake was
deferring data collection until a feature shipped — so the data never existed when the feature
arrived. v2 does not repeat that.

### Added — files

- `CLAUDE.md` — v2 build governance and the re-architecture mandate; sets doc precedence
  (CLAUDE.md → ADRs → BRD → PRD_v2) and the rule that every PRD deviation becomes an ADR.
- `BRD.md` — business requirements: goals, stakeholders, scope, 24 testable business requirements,
  success metrics, risks, and open questions.
- `ARCHITECTURE.md` — system design + ADRs (carried v1 ADRs 001–006, added v2 ADRs 100–107),
  latency budget, session data-flow, and the deterministic-vs-model reconciliation rule.
- `API_CONTRACTS.md` — `/v2/` endpoint contracts and generated TypeScript types.
- `PRD_v2.md` — copied in so the folder is self-contained.
- `backend/migrations/001_initial_schema_v2.sql` — full v2 data model (13 tables).
- `backend/migrations/002_seed_exercises_v2.sql` — exercise + badge-catalog seed.
- `backend/app/core/schemas.py` — canonical Pydantic v2 schemas (source of truth for TS types).
- `exercises/{squat,pushup,lunge}.json` — v2 exercise library.
- `.gitignore` — Python / env / editor / build hygiene.

### Changed — architecture (v1 → v2)

- **Vision Agent → two layers.** The deterministic geometry engine stays authoritative for rep
  count and safety flags (on-device, hot path, < 120 ms, no network LLM). A new **advisory**
  model-assisted layer (Phase 2) reasons over keypoint features to refine the form score and catch
  rule-less errors — but **cannot override rep count or safety flags** (ADR-100), is gated by an
  expert-agreement eval (ADR-102), and is default-off.
- **Tiered models** (ADR-104) — deterministic/on-device (hot), cheap model (warm: set summaries),
  strong model (cold: weekly recap, re-engagement, planning, memory synthesis). Model names are
  config keys, never literals.
- **3 agents → 6.** Added Planner, Memory, and Engagement agents — schema-and-contract-ready now,
  behaviour gated by phase.
- **API namespace `/v2/`** (ADR-107) — v1 `/v1/` contracts are untouched; no breakage for v1 clients.

### Changed — data model (4 tables → 13, all with RLS)

- `users` — added `health_context`, `equipment_available`, `preferred_session_time`,
  `preferred_session_duration_minutes`, `health_consent_granted_at`, and lifecycle timestamps
  (PRD_v2 §8). Health context is encrypted, RLS-scoped, and legally gated (ADR-106).
- `exercises` — added `contraindications`, `model_assist`, per-exercise `thresholds`, `is_premium`.
- `sessions` — added `score_source`, targets, `trace_id`, and an index powering the
  Day-1→Day-2 form-score-delta moment.
- New tables: `rep_metrics` (per-rep granularity), `personal_records`, `badge_catalog` +
  `user_badges`, `workout_plans`, `challenges`, `weekly_summaries`, `accountability_pairs`, and
  `form_trends` (pgvector, Memory Agent — ADR-103).

### Changed — schemas.py

- 33-keypoint skeleton (up from 17); new `DerivedFeatures` for the advisory layer.
- Added `score_source`, `PersonalRecord`, `Contraindication`, `UserProfile`, `HomePayload`,
  `WeeklySummary`, and `form_score_delta_vs_last`.
- 22 models total, all validated (build + round-trip).

### Changed — exercise JSON

- Named per-exercise `thresholds` (no more global magic numbers), error `severity`, a
  `contraindications` block (PRD_v2 §8.4), and an inert `model_assist` block (feature window +
  derived features for Phase 2).

### Personalisation & privacy

- Personalisation data is collected at onboarding **and used from MVP** — contraindication callouts,
  softened coaching tone for injury flags, fitness-level default sets/reps, goal-based welcome copy.
- Privacy invariant preserved and hardened: **pixels never leave the device and never reach any
  model**, including the new reasoning layer (ADR-101).

### Verification

- All 3 exercise JSONs valid; 22 Pydantic models build and round-trip; SQL parses (61 statements);
  all 13 tables have RLS; all foreign keys and 5 enum types resolve. (A live Postgres run was not
  possible in the build sandbox — validation was static + sqlglot.)

### Open / not yet built

- `backend/app/core/config.py` — named constants (thresholds, model names, latency/streak windows).
- `prompts/` — versioned v2 agent prompts.
- Open business questions from BRD §11 / PRD_v2 §12 — streak-freeze model, health-data legal
  sign-off, leaderboard anonymisation, D7-gate failure path, MVP personalisation depth.

---

*Add a new dated section at the top for each change set. Record architecture decisions as ADRs in
`ARCHITECTURE.md` and reference them here.*
