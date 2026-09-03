# Gate 0 eval harness

Two independent gates live in this directory. See `EVAL_HARNESS_STAGE0_SPEC.md` (kinetiq v3) and
`EVAL_STRATEGY.md` for the full rationale; this doc is the day-to-day workflow.

| | `--data` (original Gate 0) | `--golden` (Stage-0/1 golden set) | `--golden --compare-pose-models` (Stage 2) |
|---|---|---|---|
| Input | raw device exports, gitignored | frozen, committed keypoints + PT labels | frozen keypoints per pose model, `golden/poses/<model>/` |
| Scores | rep-count accuracy, device x lighting coverage | + no-phantom-reps, subject-lock, form precision/recall, view robustness | the same dimensions, one row per candidate pose model |
| Bar | ADR-110: >90% rep accuracy on >=5 devices x 3 lighting conditions | `EXERCISE_LIBRARY.md` §5's per-exercise vision-live gates | none -- prints a table, a human picks the winner |

## 1. Original Gate 0: `--data` (device exports)

Aggregates the JSON `kinetiq-demo2`'s results screen exports and prints a pass/fail verdict:
**>90% rep accuracy on >=5 real mid-range Android devices across 3 lighting conditions**, per
exercise. The full collection protocol (devices, lighting, session structure, rollback rule)
lives in `kinetiq-demo2/README.md` under "Gate 0 protocol" — this doc doesn't repeat it, only the
aggregation workflow.

1. Run `kinetiq-demo2` on each test device, per the protocol in its README: >=3 sets of 8-12
   reps, per exercise, per lighting condition, with a human counting reps out loud.
2. On each device, after collecting your sets, open the "View validation log" screen and tap
   **Export JSON**. This downloads one file per device/session (e.g.
   `kinetiq_gate0_<timestamp>.json`).
3. Copy all exported files into `data/` in this directory.
4. Run:
   ```
   python aggregate.py --data data/
   ```
5. Read the two sections it prints:
   - **Rep accuracy** — weighted accuracy per exercise (`1 - sum(|detected-actual|) / sum(actual)`,
     the same formula the PWA itself uses) against the 90% bar, plus overall.
   - **Device x lighting matrix coverage** — which (device, lighting) cells have the required
     >=3 valid sets (8-12 reps) per exercise, and which still need more data.

The script exits non-zero if the accuracy bar isn't met on any exercise.

### Data hygiene

`data/*.json` contains raw `navigator.userAgent` strings from test devices — local test output,
not source data. It's gitignored (`kinetiq-v2/.gitignore`); don't commit real exports.

### Rollback rule

Per CLAUDE.md §9 / kinetiq-demo2/README.md: if accuracy is still below the bar after 2 tuning
rounds of the `CONFIG` thresholds in `index.html`, stop and diagnose the vision approach — don't
paper over poor detection by adjusting thresholds until the number looks right.

## 2. Stage-0 golden set: `--golden` (record → label → freeze → score)

The golden set (`golden/`) is the frozen, PT-verified yardstick that scores the dimensions
`--data` never measures: **no-phantom-reps, subject-lock, per-flag form precision/recall
(severity-aware), and view robustness** (`EVAL_HARNESS_STAGE0_SPEC.md`). Unlike `data/`, it is
**committed** — it stores keypoints and labels only, never video or pixels (`CLAUDE.md` §2).

### Workflow

1. **Record.** Film a clip for the case you need (a clean set, a deliberately faulted set, a
   moved bench with nobody in frame, a bystander in the background, the same set from
   front/side/diagonal, ...). `EVAL_STRATEGY.md` §1's seed cases are the starting list.
2. **Capture keypoints.** Run each candidate pose model over the recording
   (`detector/pose_capture/`, below) to produce `golden/poses/<model>/<clip_id>.keypoints.jsonl`
   — the *only* thing derived from pixels that gets committed. Can happen before or after
   labeling; the two are independent.
3. **Label.** A PT/trainer reviews the recording and fills two CSVs (`labeling/`, below): one row
   per clip (exercise, clip_type, view, lighting, fitness level, subject info) and one row per rep
   (which `error_id`s from the relevant `exercises/*.json` are present, or none for a clean rep).
   `python -m labeling export` turns the filled CSVs into `<clip_id>.labels.json` (schema:
   `EVAL_HARNESS_STAGE0_SPEC.md` §5) and merges the clip into `MANIFEST.json` — a PT never
   hand-writes JSON. `python -m labeling validate --golden golden/` then runs the same checks CI
   does (fault ids exist and have a severity, phantom_bench/phantom_empty zero-rep shape,
   bystander's real-rep-count + marked-subject shape, keypoints schema, MANIFEST/labels.json
   agreement) and prints every offending clip/rep in one report, not just the first.
4. **Detector output.** For squat/pushup/lunge (the exercises `detector/adapter.py` supports as
   of Stage 1), you don't need to do anything here — `python aggregate.py --golden` recomputes
   `detected.json` from `keypoints.jsonl` via `run_detector` every time it runs, reproducibly.
   For an exercise the detector doesn't support yet (a future Tier A/B/C clip added before its
   own detector logic lands), hand-author or live-capture `<clip_id>.detected.json` instead
   (schema in spec §5) — the loader falls back to it automatically. Either way, it's **not**
   frozen the way labels/keypoints are.
5. **Freeze.** Get PT sign-off (`pt_verified: true` in the clip-level CSV, carried into both
   `labels.json` and `MANIFEST.json` by the exporter), and commit `labels.json` +
   `keypoints.jsonl` + the `MANIFEST.json` update together (plus `detected.json` only if step 4
   needed the bootstrap fallback). Per `EVAL_STRATEGY.md` §3: never edit an existing golden case
   in the same commit as a model or threshold change — the yardstick has to hold still to know
   whether a score moved because the system improved or the goalposts did.
6. **Score.**
   ```
   python aggregate.py --golden golden/ --mode fast    # assertions + rep-acc (CI push, seconds)
   python aggregate.py --golden golden/ --mode full    # + form P/R + subject-lock + view (CI merge/nightly)
   ```
   Exits non-zero if any dimension is below its floor. The floors themselves
   (`GATE0_TARGET_ACCURACY`, `SUBJECT_LOCK_FLOOR`, `FORM_PRECISION_FLOOR_*`,
   `FORM_RECALL_FLOOR_*`, `VIEW_ACC_MAX_GAP`) live in `backend/app/core/config.py` — this harness
   imports them (via `gate_config.py`), never restates them.

### Layout

```
golden/
  MANIFEST.json                 # index of every --mode fast/full clip
  <clip_id>.labels.json         # frozen ground truth (committed) -- shared across pose models
  <clip_id>.keypoints.jsonl     # frozen input, one pose frame per line (committed)
  <clip_id>.detected.json       # ONLY needed for an exercise detector/adapter.py doesn't support
                                 # yet -- see "Detector output" above. None of the current clips
                                 # need one; squat/pushup/lunge are all recomputed live.
  poses/<pose_model>/<clip_id>.keypoints.jsonl        # Stage 2 only -- see below
  poses/<pose_model>/<clip_id>.capture_meta.json      # optional; latency/env from a real capture
```

`poses/<model>/` clips are independent of `--mode fast/full`'s `MANIFEST.json`-driven flat
clips -- `--compare-pose-models` discovers them by scanning the directory, so a bake-off-only
clip needs a `<clip_id>.labels.json` (shared, model-independent ground truth per
`GOLDEN_SET_PROTOCOL.md` §2) but not a flat top-level `keypoints.jsonl`.

Run `python golden_loader.py golden/` on its own as a quick schema lint (fault ids exist in the
exercise library, every fault has a severity, clip types and views are valid, keypoints are
well-formed) without running the full scorer suite.

### The Stage-1 reference detector (`detector/`)

`detector/adapter.py`'s `run_detector(keypoints_stream, exercise_id, config) -> DetectedClip` is
the offline, deterministic, keypoints-only implementation of
`VISION_ARCHITECTURE.md` Stages 1/3/4/5b — subject-lock, the rep-validity gate, the smoothed rep
counter, and the deterministic form-flag rules (as of Stage 3: sustained across the rep, not
single-frame -- see the next section). It's what turns `--mode full` from "scores whatever
detected.json says" into "measures an actual algorithm against frozen input." See its module
docstrings (`detector/subject_lock.py`, `plausibility.py`, `rep_counter.py`, `faults.py`,
`flag_hysteresis.py`, `exercise_signals.py`, `keypoint_map.py`) for how each stage works and why.
It's scoped to squat/pushup/lunge for now (`ROADMAP.md` Stage 1); a new exercise needs its own
entry in `exercise_signals.PRIMARY_JOINTS` and a fault evaluator in `faults.py` before the
detector can score it (`golden_loader.py` falls back to a bootstrap `detected.json` until then).

This is the harness-side reference implementation the eval gate measures against -- **not** the
live PWA/JS detector. Porting the algorithm to the live JS path is a deliberate follow-on, not
done here; every module is written as pure functions over plain dicts specifically so that port
is a transliteration, not a redesign.

### Stage-3 flag-level hysteresis + visibility gating (`detector/flag_hysteresis.py`)

The direct fix for the field hip-sag false positive (SPRINT.md G2, `../kinetiq-v2/VISION_ERROR_ANALYSIS.md`
RC4): Stage 1 evaluated each fault rule (`detector/faults.py`) once per rep, at that rep's single
deepest-point frame -- a single noisy frame could trip a flag on an otherwise-clean rep. Stage 3
re-evaluates the rule across every frame in the rep's window and only commits the flag once the
fault held true for a large enough **fraction** of the frames where it could be judged at all
(fps-robust by design, not a fixed frame count -- confirmed with the user rather than assumed; see
`flag_hysteresis.py`'s module docstring). Two refinements on top of that:

- **Per-flag visibility gate**: a frame doesn't count as evidence for a flag at all if that
  flag's own involved landmarks are below `FLAG_MIN_VISIBILITY` on that frame (distinct from the
  coarser whole-body plausibility check). Too little evidence overall (`< FLAG_MIN_EVALUABLE_FRAMES`)
  and the flag reports **insufficient evidence** -- not asserted, not denied, and surfaced in the
  printed report's own section, never silently folded into "no fault".
- **Severity-aware strictness**: the required sustained fraction is keyed off the same
  high/med/low taxonomy everything else uses -- high-severity flags need the *most* sustained
  evidence before committing (precision-first: better to miss a real fault than falsely accuse a
  good rep on a safety-relevant flag).
- **Bottom-phase-only faults** (e.g. squat's `shallow_depth`, whose rule the exercise library
  declares relevant only at the bottom, not the whole descent/ascent) are evaluated over just the
  bottom fraction of *that rep's own excursion range* -- not the exercise's correct-depth
  threshold, so a partial-depth rep still has a genuine bottom to judge against (see
  `adapter.py`'s `_evaluate_rep_flags` docstring; this was a real bug caught while building this,
  not a hypothetical -- a naive whole-rep window flagged `shallow_depth` on every rep, clean ones
  included, since standing/mid-descent legitimately isn't "at depth" yet).

Only the 5 per-frame, landmark-based flags go through this (`knee_cave_left/right`,
`shallow_depth`, `elbow_flare`, `hip_sag`) -- `shallow_pushup`/`shallow_lunge` are rep-aggregate
(compared against the rep's overall smoothed minimum angle, already temporally smoothed by
`rep_counter.py`) and unaffected. **This governs WHEN a flag first commits, never un-commits
one** -- the deterministic safety veto (`VISION_ARCHITECTURE.md` Stage 5b) is untouched.

All the thresholds here (`FLAG_MIN_VISIBILITY`, `FLAG_MIN_EVALUABLE_FRAMES`,
`FLAG_HYSTERESIS_MIN_FRACTION_{HIGH,MED,LOW}_SEV`, `FLAG_BOTTOM_PHASE_FRACTION`) are **placeholder
values pending real golden-set tuning** (`GOLDEN_SET_PROTOCOL.md` §8) -- this is the mechanism,
not the calibration; don't read the numbers in `config.py` as validated.

### Synthetic fixture data

**The `golden/` directory currently ships only synthetic, parametrically-generated fixture data**
(see `golden/MANIFEST.json`'s `_synthetic_fixture` flag) — eleven small clips covering the cases
Stage 0/1/3's exit gates need: clean reps, a seeded knee-cave fault, a bench misdetection, an
empty frame, a bystander, partial depth, a slow-tempo rep, and (Stage 3) a one-noisy-frame clip
that must NOT flag, a sustained-fault clip that must, and a low-visibility clip that must read
"insufficient evidence" -- see the Stage-3 section above. These exist purely so `scorers/*.py`,
`golden_loader.py`, `detector/*.py`, and `aggregate.py --golden golden/ --mode full` run and pass
end-to-end without needing real recordings. **They are not PT-verified and are not the frozen
v3.0 golden set `EVAL_STRATEGY.md` §3 calls for.** Before this becomes the authoritative gate for
any exercise going vision-live (`EXERCISE_LIBRARY.md` §5), replace/augment it with real recorded,
PT-labeled clips per the workflow above — start from `EVAL_STRATEGY.md` §1's seed-case table.

### The severity alias (flagged, not silently fixed)

The Stage-0 severity taxonomy is `{high, med, low}` (`EXERCISE_LIBRARY.md` §4), but
`kinetiq-v2/exercises/*.json` currently write `"medium"` and `"high"`. `exercise_lib.py` aliases
`medium -> med` at load time (see its module docstring) rather than bulk-rewriting the exercise
JSON, which is out of scope here. **The underlying JSON data still says `"medium"`** — a
follow-up should normalise `exercises/*.json` directly and delete the alias.

### Known simplifications

- A fault that never appears (as a ground-truth fault or a detected flag) anywhere in the golden
  set is simply absent from the form-P/R report — it is not auto-failed, but it's also not
  actually being tested. A real frozen golden set needs enough cases per fault for its floor to
  mean something.
- The coaching-cue judge is a cheap stub (length + banned-term list), not the calibrated
  LLM-as-judge `EVAL_STRATEGY.md` §2 describes. That lands in Stage 6 — `run_detector` doesn't
  emit coaching cues at all (deliberately; that's Stage 6's job, not Stage 1's).
- `detector/adapter.py` evaluates the 5 per-frame form-flag rules across each rep's whole window
  (Stage 3), sustained-fraction-gated -- but still doesn't distinguish *which* sub-phase within
  that window a frame belongs to beyond the bottom-only narrowing described above; a rule
  declared relevant to "descending, bottom, ascending" is evaluated identically across all three,
  not weighted toward the phase where it matters most. Full per-frame temporal fault tracking
  with real phase awareness is Stage 4/5's learned form model, not this deterministic baseline.
- `insufficient_evidence` is a new field on each detected rep (not part of `flags`) -- a scorer
  or report that only reads `flags` will correctly treat it as "no accusation" (never a false
  positive), but won't see that the flag was actually unjudgeable; `aggregate.py --mode full`
  surfaces it in its own report section specifically so it isn't silently invisible elsewhere.
- The Stage-1 detector is scoped to squat/pushup/lunge (`ROADMAP.md`); the 11 requested
  exercises are Stage 5, gated in one at a time, and each needs its own entry in
  `detector/exercise_signals.py` and `detector/faults.py` before it can be scored this way.

## 3. Stage-2 pose-model bake-off: `--compare-pose-models`

Ch 39: model selection is "religion into measurement," not a debate. This turns "BlazePose or
MoveNet or RTMPose?" (`VISION_ARCHITECTURE.md` Stage 2 / §5) into a table the golden set decides.
**This is the tooling, not the verdict** -- the real comparison needs real recorded clips run
through all 3 candidates (`GOLDEN_SET_PROTOCOL.md` §8's bake-off minimum, ~23 clips), which don't
exist yet. Right now this runs end-to-end on one synthetic multi-model clip
(`squat_bakeoff_side_001`) purely to prove the tooling is correct.

### The three candidates (`config.py`'s `POSE_MODEL_CANDIDATES`)

| name | landmarks | dims | why this one |
|---|---|---|---|
| `blazepose_33` | 33 | 3D (world landmarks) | richest skeleton; 3D is a VISION_ARCHITECTURE.md §2 candidate fix for the front/side rep-count gap (RC5) |
| `movenet_17` | 17 | 2D | the existing baseline (COCO-17, "accurate, fast") |
| `rtmpose_halpe26` | 26 | 2D | **RTMPose-m on Halpe-26** (not plain-COCO RTMPose) -- Halpe-26 extends COCO-17 with head/neck/hip-center/toe/heel points, closer to BlazePose's richness, so the 3-way comparison is actually informative on skeleton detail, not just speed. Good-GYM (VISION_ARCHITECTURE.md's cited reference) uses RTMPose via `rtmlib`; this repo doesn't pin which keypoint convention Good-GYM itself uses, so Halpe-26 was chosen deliberately rather than assumed. |

No model name/weights/runtime is hardcoded in the harness or the capture tool -- both iterate
this registry. Add a 4th candidate by adding one entry here, one `detector/keypoint_map.py`
mapping, and one `detector/pose_capture/` adapter.

### Capturing keypoints: `detector/pose_capture/`

```
python -m detector.pose_capture --list                              # availability + install hints
python -m detector.pose_capture --model blazepose_33 --dry-run       # schema/writer self-test, no runtime needed
python -m detector.pose_capture --model blazepose_33 \               # the real capture
    --video path/to/clip.mp4 --clip-id squat_clean_side_001 --golden golden/
```

Run from `evals/gate0/`. Each adapter's model-runtime import is **lazy** (inside `infer_frames()`,
not at module load) -- the ONLY non-deterministic, heavy-dependency part of this whole pipeline is
isolated there, so `run_detector` and every scorer downstream of a frozen `keypoints.jsonl` stay
fully deterministic (verified by `test_run_detector_output_is_identical_across_models_for_equivalent_skeletons`
in `test_golden_loader.py`).

**All three adapters are live-tested** (`detector/pose_capture/README.md`) -- each was run
end-to-end through this exact `capture_clip()`/CLI path against a real throwaway video, with
`num_poses`/`multi_person_config` per ADR-300 so every candidate yields all people in frame, not
just the top-1. None of the three runtimes are installed in *this* repo's own dev environment by
default (`--list` reports them unavailable here) -- they were verified in an isolated venv outside
the repo; see `detector/pose_capture/README.md` for exact versions, install steps, and the two
real bugs live-testing caught (wrong coordinate space, wrong rtmlib class) that a docs-only sketch
had missed. `--dry-run` proves the schema-validation + writer plumbing independent of any runtime
being installed. **Nothing here fakes keypoints as real data** -- a dry run writes a synthetic
frame to a throwaway temp file, validates it, and discards it; it never touches `golden/`.

Capture writes exactly two files per (model, clip):
`golden/poses/<model>/<clip_id>.keypoints.jsonl` and a companion `.capture_meta.json` (frame
count, average latency, capture environment). **Never the video itself** -- `GOLDEN_SET_PROTOCOL.md`
§1's privacy invariant. Delete/offline the source video yourself once capture is done.

Latency in `.capture_meta.json` is **capture-machine wall-clock** timed around each frame's
inference call, labeled with `capture_env` (e.g. "Windows-11 ... / python 3.13 (capture-machine,
not on-device)") -- explicitly **not** on-device mobile latency, which needs a real Android
benchmark harness this Python tool doesn't attempt. A clip with no `.capture_meta.json` (every
clip in the current synthetic fixture) shows `n/a (synthetic)` in the table rather than a
fabricated number.

Model size (`approx_size_mb` in the registry) is `None`/`n/a` for all three candidates right now
-- nobody has installed the real runtimes here to measure actual weights-file size, and this
harness doesn't guess numbers it hasn't measured.

### Reading the table

```
python aggregate.py --golden golden/ --compare-pose-models
```

One row per candidate, columns: clips available, rep-accuracy, no-phantom-reps, subject-lock,
pooled form precision/recall (micro-averaged across every flag -- one number per model, not the
per-flag breakdown `--mode full` prints), latency, size. A model with zero `golden/poses/<model>/`
clips prints as "no clips yet" -- expected right now, not a failure. **The tool never declares a
winner**; exit code is non-zero only on a genuinely broken golden set (a schema/validation error),
never because one model's numbers are worse than another's. Read `VISION_ARCHITECTURE.md` §5 and
`ROADMAP.md`'s Stage 2 exit gate, then decide once `GOLDEN_SET_PROTOCOL.md` §8's real clips exist.

### Known Stage-2 simplifications

- `approx_size_mb` is only measured for `blazepose_33` so far (the one .task file downloaded and
  weighed this session) -- `movenet_17`/`rtmpose_halpe26` still show `None`/`n/a` until someone
  measures their real installed weights.
- The bake-off table's precision/recall is pooled (micro-averaged across every flag) for one row
  per model; a real bake-off decision should also read the full per-flag breakdown (`--mode full`
  per pose model) before concluding a model is better, per Ch 39's "a single number can hide a
  collapsing one."
- `movenet_17`'s emitted coordinates are normalized to the letterbox-padded input, not corrected
  back to the source frame's own aspect ratio -- a small systematic offset on non-square video;
  see `detector/pose_capture/README.md`'s "known caveat" section.
- Still only one real clip has been run through all three adapters (a throwaway plumbing
  smoke-test, not golden-set data) -- `GOLDEN_SET_PROTOCOL.md` §8's ~23-clip bake-off minimum is
  what the table needs before it means anything.

## Labeling: `labeling/`

Turns a PT's filled spreadsheet into a frozen golden-set clip
(`GOLDEN_SET_PROTOCOL.md` §7) -- no engineering help needed to fill it, no hand-written JSON.

```
python -m labeling templates --out-dir label_work/       # blank clips_template.csv + reps_template.csv
python -m labeling templates --list-faults squat         # valid error_ids for squat, read from exercises/squat.json
python -m labeling export --clips label_work/clips_template.csv \
    --reps label_work/reps_template.csv --golden golden/  # CSV -> labels.json + MANIFEST.json
python -m labeling validate --golden golden/              # same checks CI runs
```

Run from `evals/gate0/`. Two CSVs, one row each:

- **`clips_template.csv`** (one row per clip): `clip_id, exercise, clip_type, view, lighting,
  fitness_level, actual_reps, num_people_in_frame, subject_track_id, labeler, pt_verified`.
- **`reps_template.csv`** (one row per rep): `clip_id, rep_idx, faults` -- `faults` is
  `;`-separated `error_id`s from that exercise's library, empty for a clean rep.

`labeling/export.py` is deliberately mechanical: it only reshapes CSV rows into the schema's JSON
shape and enforces CSV-structural integrity (a required column, a well-formed integer, no
duplicate clip_id/rep_idx) -- it never checks domain rules. `labeling/validate.py` does that,
collecting **every** issue across the whole golden set into one report (not just the first, unlike
`golden_loader.py`'s fail-fast loading) so a PT fixing a spreadsheet gets the full list at once:

- every fault id exists in that exercise's library and resolves to a severity (reuses
  `exercise_lib.py`'s existing `medium` -> `med` alias -- see below, not re-decided here)
- `phantom_bench`/`phantom_empty` clips have `actual_reps == 0`, `reps == []` -- **`bystander` is
  NOT phantom-like** (see below): it must have `actual_reps > 0` (the user's real count) and a
  marked `subject.subject_track_id`
- a `normal` or `bystander` clip's rep rows cover `1..actual_reps` exactly -- catches a PT
  skipping a row
- `keypoints.jsonl` frames are schema-valid, for every `poses/<model>/` this clip has captures
  under (missing captures are a **warning**, not an error -- capture and labeling can happen in
  either order)
- `MANIFEST.json` and each `labels.json` agree field-for-field (catches copy-paste drift)

**`bystander` is a real-rep clip, not phantom-like -- resolved.** An earlier revision of this
harness had `bystander` requiring `actual_reps == 0` (matching a stale reading of
`EVAL_HARNESS_STAGE0_SPEC.md` §5 against `GOLDEN_SET_PROTOCOL.md` §4, which describes a
bystander's `actual_reps` as "the user's real count"). The canonical answer, now consistent across
`EVAL_HARNESS_STAGE0_SPEC.md` §5/§7, `EVAL_STRATEGY.md`, `EXERCISE_LIBRARY.md` §5, and
`ROADMAP.md`: **only `phantom_bench`/`phantom_empty` are zero-rep.** A bystander clip proves the
skeleton stays on the user (subject-lock, `scorers/subject_lock.py`) *while still counting the
user's real reps* -- it flows into ordinary rep-accuracy and form-P/R scoring exactly like a
`normal` clip, and `scorers/phantom.py`'s zero-reps gate never touches it.

## Live detector API: `prototype_api/`

Step 1 of the live-vision-prototype build (`VISION_ARCHITECTURE.md`): a thin FastAPI service that
wraps `detector/adapter.py`'s `run_detector` so the live prototype and this eval harness share
**one detector** -- no JS reimplementation, no logic drift. `python -m prototype_api` runs it
locally; see `prototype_api/README.md` for the full request/response contract, session-buffering
model, and the interim (not Stage-6) coaching-cue layer. `prototype_api/test_parity.py` is the
proof this actually holds: the API's result for a given frame sequence is asserted identical to
calling `run_detector` directly, against real golden-set fixtures.

## Effectiveness report: `effectiveness_report.py`

Step 3 of the live-vision-prototype build: turns one `kinetiq-demo3` session export + a trainer's
filled fault labels into a single effectiveness read — rep-accuracy plus form precision/recall and
insufficient-evidence counts, via the exact scorers the golden-set gate uses. Pure glue: no new
scoring rule, no reimplementation — `labeling/export.py` and `labeling/validate.py` build the
golden set exactly as they already do, `scorers/form_pr.py` scores it exactly as `aggregate.py`
does, and a parity check compares the live app's own `detected.json` against a fresh offline
`run_detector` recompute over the same `keypoints.jsonl` (they should always agree; a mismatch
means a client/API buffer desync, not a scoring disagreement — see the script's module docstring).

### Runbook

1. **Record.** Run `kinetiq-demo3` against a real, reachable `prototype_api` — pick an exercise,
   do a real set, Stop, enter the actual rep count, Export bundle. This downloads a `.zip`; unzip
   it somewhere (`<clip_id>.keypoints.jsonl`, `<clip_id>.detected.json`, `clips_template.csv`,
   `reps_template.csv`, `README.txt` — see `kinetiq-demo3/README.md`'s "Effectiveness capture").

2. **Trainer labels (a human step — this tool never fabricates it).** Open
   `reps_template.csv` and fill in the blank `faults` column per rep (`;`-separated `error_id`s
   from `exercises/<exercise>.json`, blank = clean rep) based on what the trainer actually
   observed live — there is no video to review. Once done, set `pt_verified` to `true` in
   `clips_template.csv`. `effectiveness_report.py` refuses to score a clip whose `pt_verified` is
   still `false` by default (blank faults are ambiguous between "clean, confirmed" and "not
   reviewed yet" — only this flag tells them apart); `--allow-unverified` overrides it for a
   preview, but a preview's numbers are never a real result.

3. **One command:**
   ```
   python effectiveness_report.py --bundle-dir <unzipped bundle dir> --golden golden_local/
   ```
   Runs `labeling export` → `labeling validate` (writing/merging into `--golden`, exactly as the
   existing workflow already does — see `Labeling: labeling/` above), the parity check, then
   prints rep-accuracy + severity-gated per-flag precision/recall + insufficient-evidence, all
   under a loud caveat header (small n, single-user BlazePose only — no subject-lock is exercised
   at all, interim non-Stage-6 cues, and a reminder that only a real camera session's numbers
   mean anything — never a stubbed/Playwright run's). Exits non-zero if the parity check fails or
   the trainer-verification gate blocks; the `--golden` directory it writes is a normal golden
   set afterward — re-run `aggregate.py --golden golden_local/ --mode full` or
   `--compare-pose-models` on it directly, and it merges with any other clips already there
   rather than overwriting them.

## Unit tests

Stdlib `unittest` except `prototype_api/` (needs `pip install -r prototype_api/requirements.txt`
-- FastAPI/uvicorn/pydantic/httpx; everything else in this directory is still dependency-free).
Run from this directory or the repo root:

```
python -m unittest discover -s evals/gate0 -p "test_*.py" -v
```

`scorers/test_*.py` cover each scoring dimension in isolation over tiny synthetic clips;
`test_exercise_lib.py` and `test_golden_loader.py` cover the severity alias and schema validation,
including against the real `exercises/*.json` and the synthetic `golden/` fixture (including the
Stage-3 hysteresis/visibility fixtures, proven through the full harness, not just in isolation);
`detector/test_*.py` cover the Stage-1 reference detector's specialists, plus
`detector/test_flag_hysteresis.py` for the Stage-3 mechanism itself (one-frame-doesn't-flag,
sustained-does, visibility gating, severity strictness) over synthetic frame lists;
`detector/pose_capture/test_*.py` cover the capture tool's writer/schema/CLI plumbing using a fake
in-memory adapter (no real ML runtime needed to test it); `test_aggregate.py` covers the Stage-2
bake-off table and the Stage-3 insufficient-evidence report section; `labeling/test_*.py` cover
the CSV-template writer, the exporter (good clip, phantom clip, duplicate/malformed rows), and the
validator (a good clip, a phantom clip, an unknown fault id, and a fault whose exercise-library
entry has no severity at all, via a temp library override -- the real `exercises/*.json` always
declare one today); `prototype_api/test_*.py` cover the session buffer, the interim cue layer
(against the real exercise library -- this is what proves two of its cues are genuinely over the
word cap), the HTTP contract, and `test_parity.py`'s core "API == run_detector" proof (see
`prototype_api/README.md`, above); `test_effectiveness_report.py` covers a synthetic
kinetiq-demo3-shaped bundle end-to-end (clean-clip scoring, a seeded fault's false-negative, the
trainer-verification gate blocking/allowing, and a deliberately corrupted `detected.json` proving
the parity check actually catches a real live/offline divergence) -- also verified by hand against
a real bundle exported by a live-driven `kinetiq-demo3` session (see the script's own runbook,
above).
