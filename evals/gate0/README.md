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
3. **Bootstrap the detector output.** Stage 0 doesn't yet have an offline detector adapter that
   re-runs over frozen keypoints (that's Stage 1 — `EVAL_HARNESS_STAGE0_SPEC.md` §12). Until then,
   capture the demo's live per-rep output during recording into `<clip_id>.detected.json`
   (schema in spec §5). A real offline detector run will overwrite these later; they are **not**
   frozen the way labels/keypoints are.
4. **Freeze.** Add the clip's row to `MANIFEST.json`, get PT sign-off, and commit all four files
   (`labels.json`, `keypoints.jsonl`, `detected.json`, the `MANIFEST.json` update) together.
   Per `EVAL_STRATEGY.md` §3: never edit an existing golden case in the same commit as a model or
   threshold change — the yardstick has to hold still to know whether a score moved because the
   system improved or the goalposts did.
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
  <clip_id>.detected.json       # bootstrap detector output (committed for now; Stage 1
                                 # regenerates this from keypoints.jsonl instead)
```

Run `python golden_loader.py golden/` on its own as a quick schema lint (fault ids exist in the
exercise library, every fault has a severity, clip types and views are valid, keypoints are
well-formed) without running the full scorer suite.

### Synthetic fixture data

**The `golden/` directory currently ships only synthetic, hand-authored fixture data** (see
`golden/MANIFEST.json`'s `_synthetic_fixture` flag) — four small clips (`squat_bench_phantom_001`,
`pushup_good_side_001`, `pushup_bystander_001`, `squat_badform_001`) that exist purely so
`scorers/*.py`, `golden_loader.py`, and `aggregate.py --golden golden/ --mode full` run and pass
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

### Known Stage-0 simplifications

- A fault that never appears (as a ground-truth fault or a detected flag) anywhere in the golden
  set is simply absent from the form-P/R report — it is not auto-failed, but it's also not
  actually being tested. A real frozen golden set needs enough cases per fault for its floor to
  mean something.
- Subject-lock and rep-count numbers come from the detector's own self-reported
  `detected.json`, not from re-running a detector over `keypoints.jsonl` — see "Bootstrap the
  detector output" above.
- The coaching-cue judge is a cheap stub (length + banned-term list), not the calibrated
  LLM-as-judge `EVAL_STRATEGY.md` §2 describes. That lands in Stage 6.

## Unit tests

Stdlib `unittest`, no dependencies. Run from this directory or the repo root:

```
python -m unittest discover -s evals/gate0 -p "test_*.py" -v
```

`scorers/test_*.py` cover each scoring dimension in isolation over tiny synthetic clips;
`test_exercise_lib.py` and `test_golden_loader.py` cover the severity alias and schema validation,
including against the real `exercises/*.json` and the synthetic `golden/` fixture.
