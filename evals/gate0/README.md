# Gate 0 eval harness

Two independent gates live in this directory. See `EVAL_HARNESS_STAGE0_SPEC.md` (kinetiq v3) and
`EVAL_STRATEGY.md` for the full rationale; this doc is the day-to-day workflow.

| | `--data` (original Gate 0) | `--golden` (Stage-0 golden set) |
|---|---|---|
| Input | raw device exports, gitignored | frozen, committed keypoints + PT labels |
| Scores | rep-count accuracy, device x lighting coverage | + no-phantom-reps, subject-lock, form precision/recall, view robustness |
| Bar | ADR-110: >90% rep accuracy on >=5 devices x 3 lighting conditions | `EXERCISE_LIBRARY.md` §5's per-exercise vision-live gates |

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
2. **Label.** A PT/trainer reviews the recording and writes `<clip_id>.labels.json`: per-rep
   faults (as `error_id`s that exist in the relevant `exercises/*.json`), the subject's
   `subject_track_id`, view, lighting, fitness level. See the schema in
   `EVAL_HARNESS_STAGE0_SPEC.md` §5. Extract `<clip_id>.keypoints.jsonl` from the same recording
   (pose model's raw per-frame output — this is the *only* thing derived from pixels that gets
   committed).
3. **Detector output.** For squat/pushup/lunge (the exercises `detector/adapter.py` supports as
   of Stage 1), you don't need to do anything here — `python aggregate.py --golden` recomputes
   `detected.json` from `keypoints.jsonl` via `run_detector` every time it runs, reproducibly.
   For an exercise the detector doesn't support yet (a future Tier A/B/C clip added before its
   own detector logic lands), hand-author or live-capture `<clip_id>.detected.json` instead
   (schema in spec §5) — the loader falls back to it automatically. Either way, it's **not**
   frozen the way labels/keypoints are.
4. **Freeze.** Add the clip's row to `MANIFEST.json`, get PT sign-off, and commit `labels.json` +
   `keypoints.jsonl` + the `MANIFEST.json` update together (plus `detected.json` only if step 3
   needed the bootstrap fallback). Per `EVAL_STRATEGY.md` §3: never edit an existing golden case
   in the same commit as a model or threshold change — the yardstick has to hold still to know
   whether a score moved because the system improved or the goalposts did.
5. **Score.**
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
  MANIFEST.json                 # index of every clip
  <clip_id>.labels.json         # frozen ground truth (committed)
  <clip_id>.keypoints.jsonl     # frozen input, one pose frame per line (committed)
  <clip_id>.detected.json       # ONLY needed for an exercise detector/adapter.py doesn't support
                                 # yet -- see "Detector output" above. None of the current clips
                                 # need one; squat/pushup/lunge are all recomputed live.
```

Run `python golden_loader.py golden/` on its own as a quick schema lint (fault ids exist in the
exercise library, every fault has a severity, clip types and views are valid, keypoints are
well-formed) without running the full scorer suite.

### The Stage-1 reference detector (`detector/`)

`detector/adapter.py`'s `run_detector(keypoints_stream, exercise_id, config) -> DetectedClip` is
the offline, deterministic, keypoints-only implementation of
`VISION_ARCHITECTURE.md` Stages 1/3/4/5b — subject-lock, the rep-validity gate, the smoothed rep
counter, and the (unchanged) deterministic form-flag rules. It's what turns `--mode full` from
"scores whatever detected.json says" into "measures an actual algorithm against frozen input."
See its module docstrings (`detector/subject_lock.py`, `plausibility.py`, `rep_counter.py`,
`faults.py`, `exercise_signals.py`, `keypoint_map.py`) for how each stage works and why. It's
scoped to squat/pushup/lunge for now (`ROADMAP.md` Stage 1); a new exercise needs its own entry in
`exercise_signals.PRIMARY_JOINTS` and a fault evaluator in `faults.py` before the detector can
score it (`golden_loader.py` falls back to a bootstrap `detected.json` until then).

This is the harness-side reference implementation the eval gate measures against -- **not** the
live PWA/JS detector. Porting the algorithm to the live JS path is a deliberate follow-on, not
done here; every module is written as pure functions over plain dicts specifically so that port
is a transliteration, not a redesign.

### Synthetic fixture data

**The `golden/` directory currently ships only synthetic, parametrically-generated fixture data**
(see `golden/MANIFEST.json`'s `_synthetic_fixture` flag) — eight small clips covering the cases
Stage 0/1's exit gates need (clean reps, a seeded knee-cave fault, a bench misdetection, an empty
frame, a bystander, partial depth, a slow-tempo rep) that exist purely so `scorers/*.py`,
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
- `detector/adapter.py` evaluates form-flag rules once per rep, at that rep's deepest-point
  frame (falling back to the nearest frame with a valid, plausible pose if the exact deepest
  frame was a gap) — not across the rep's full trajectory. Full per-frame temporal fault
  tracking is Stage 4/5's learned form model, not this deterministic baseline.
- The Stage-1 detector is scoped to squat/pushup/lunge (`ROADMAP.md`); the 11 requested
  exercises are Stage 5, gated in one at a time, and each needs its own entry in
  `detector/exercise_signals.py` and `detector/faults.py` before it can be scored this way.

## Unit tests

Stdlib `unittest`, no dependencies. Run from this directory or the repo root:

```
python -m unittest discover -s evals/gate0 -p "test_*.py" -v
```

`scorers/test_*.py` cover each scoring dimension in isolation over tiny synthetic clips;
`test_exercise_lib.py` and `test_golden_loader.py` cover the severity alias and schema validation,
including against the real `exercises/*.json` and the synthetic `golden/` fixture.
