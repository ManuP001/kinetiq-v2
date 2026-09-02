# prototype_api — the live detector API

Step 1 of the live-vision-prototype build (`kinetiq v3/VISION_ARCHITECTURE.md`). A thin FastAPI
service that wraps the **existing, eval-validated** `run_detector`
(`evals/gate0/detector/adapter.py`) so the live app and the eval harness share **one detector**.

**Principle: one detector, two consumers.** The Python detector in `evals/gate0/detector` is the
only detection logic that exists. This service imports and calls it — it never reimplements or
forks a rule. `test_parity.py` is the proof: for a given frame sequence, the API's result is
identical to calling `run_detector` directly on the same frames. If a change ever makes that test
fail, the API has drifted from the detector, which is a bug by definition, not a feature.

This is **not** the full `/v2` product API — no auth, no database, no persistence beyond an
in-memory per-process session buffer — and **not** Stage-6 coaching (the cue layer below is
explicitly interim). See `CLAUDE.md` §7 for what v3 does not do yet.

## Run it locally

```
cd evals/gate0
pip install -r prototype_api/requirements.txt
python -m prototype_api
```

Starts uvicorn on `http://127.0.0.1:8000` (single worker, no reload, no TLS — development only).
Interactive docs at `http://127.0.0.1:8000/docs`.

## The contract

### `POST /prototype/assess`

**Request body:**

```json
{
  "session_id": "abc123",
  "exercise_id": "squat",
  "frames": [
    {"t_ms": 0, "pose_model": "movenet_17",
     "people": [{"track_id": 0, "kp": [[0.5, 0.5, null, 0.9], ...], "box": [0.4, 0.4, 0.2, 0.2]}]}
  ],
  "reset": false
}
```

- `session_id` — any non-empty string the client controls; identifies the server-side frame
  buffer (see "Session buffering" below).
- `exercise_id` — one of `squat`, `pushup`, `lunge` (`detector/exercise_signals.scoped_exercises()`
  — the Stage-1 reference detector's scope, `ROADMAP.md`). Anything else is a 422.
- `frames` — new keypoint frames since the last call, in the Stage-0 schema
  (`EVAL_HARNESS_STAGE0_SPEC.md` §5: `{t_ms, pose_model, people: [{track_id, kp: [[x,y,z,vis],...], box}]}`).
  Can be empty (e.g. a client just polling current state without new data).
- `reset` — `true` clears this session's buffer **before** appending `frames` this call (start a
  new set without restarting the process).

**Every frame is validated with `golden_loader.validate_frame_schema`** — the exact function the
golden set is frozen against, imported not reimplemented. This is also what enforces the privacy
invariant (`CLAUDE.md` §2): a request carrying anything that isn't keypoints (an image, a raw
pixel array) has no `t_ms`/`pose_model`/`people`/`kp` shape and fails this check before it ever
reaches the detector. **One bad frame anywhere in the batch rejects the whole request** — nothing
is partially appended.

**Response body (200):**

```json
{
  "rep_count": 2,
  "rep_in_progress": false,
  "phase": "top",
  "current_flags": [],
  "insufficient_evidence": [],
  "subject_lock_ok": true,
  "coaching_cue": "Full range — great push-up",
  "cue_warning": null
}
```

| field | type | source |
|---|---|---|
| `rep_count` | int | `DetectedClip.detected_reps` |
| `rep_in_progress` | bool | `DetectedClip.rep_in_progress` (`detector/rep_counter.py`'s live FSM state) |
| `phase` | `"top"` \| `"descending"` \| `"ascending"` | `DetectedClip.phase` — no distinct "bottom" state; the FSM's descending→ascending transition happens at a single sample, not a held state |
| `current_flags` | list[str] | the **latest completed rep**'s committed flags (`[]` if no rep has completed yet) |
| `insufficient_evidence` | list[str] | the latest completed rep's sustained-but-unjudgeable flags |
| `subject_lock_ok` | bool | is the locked subject present in the most recent frame (`subject_track_sequence[-1] is not None`) |
| `coaching_cue` | str \| null | see "Coaching cue layer" below; `null` if no rep has completed yet |
| `cue_warning` | str \| null | **not part of the original 7-field spec** — see below; `null` on every normal response |

**Error responses** (structured, not a bare stack trace):

```json
{"error": "unknown_exercise", "detail": "exercise_id must be one of ('squat', 'lunge', 'pushup'), got 'deadlift'"}
```

| status | `error` | when |
|---|---|---|
| 422 | `unknown_exercise` | `exercise_id` isn't squat/pushup/lunge |
| 422 | `invalid_frame` | a frame fails `validate_frame_schema` (also FastAPI's own default 422 for a malformed request body, e.g. missing `session_id`) |
| 413 | `session_buffer_full` | this call would push the session's buffer past `PROTOTYPE_SESSION_MAX_FRAMES` |

## Session buffering

Per `session_id`, frames are buffered **server-side, in memory, single process**
(`session_buffer.py`) — `reset: true` clears it. On every call, `run_detector` re-runs over the
**whole accumulated buffer**, not just the new frames — the simplest-correct choice for a
prototype-length set (a few minutes), and it's what makes the parity property exact: the API's
result is always identical to calling `run_detector` fresh over that same accumulated sequence,
by construction.

**Latency characteristic**: each call costs `O(frames buffered so far)`, not `O(new frames this
call)` — a session sending small batches late in a long set re-scores everything from the start
each time. Fine for a prototype; a real product would need incremental/streaming detection state,
out of scope here. `PROTOTYPE_SESSION_MAX_FRAMES` (`config.py`, ~3600 = 2 minutes at 30fps, not a
tuned product limit) bounds how large a single session's buffer — and therefore this cost — can
grow; exceeding it is a 413, not a silent frame drop.

A process restart loses every session (no persistence). This is a prototype-scale limitation, not
an oversight.

## Coaching cue layer — explicitly interim

`cues.py` maps a completed rep's committed flags to plain text already defined in
`exercises/<id>.json`'s `coaching_cues` — **this is not the Stage-6 calibrated LLM judge**
(`VISION_ARCHITECTURE.md` Stage 6, `EVAL_HARNESS_STAGE0_SPEC.md` §10/§12), and never invents cue
copy. Positive-first (`CLAUDE.md` §2): a clean rep (no committed flags) gets `coaching_cues.good_rep`;
a flagged rep gets the cue for the **first** committed flag, in the exact order `run_detector`'s
own `flags` list already produced (never re-ordered here).

**Word cap, flagged not hidden**: every cue is checked against `LIVE_CUE_MAX_WORDS` (8,
`config.py`), counted with the same `len(text.split())` `aggregate.py`'s existing Stage-0
coaching-cue assertion already uses. **An over-cap cue is never silently truncated** — it's a copy
bug in the exercise library, and cutting words would hide the bug along with the words. Two real
ones this check found (not hypothetical):

- `squat.json`'s `shallow_depth` cue — "Sit a little deeper — hip crease to knee level" (10 words)
- `pushup.json`'s `shallow_pushup` cue — "Go a little lower — elbows to 90 degrees" (9 words)

Both still exceed the cap once the em dash is counted as a token by the same convention
`aggregate.py` already uses — see `test_cues.py`. When the API returns an over-cap cue, the full
(untruncated) text is still returned in `coaching_cue`, `cue_warning` is set to a message naming
the flag/word-count, and a server-side warning is logged. `cue_warning` is **not** one of the 7
fields the build task originally specified — it was added specifically to satisfy "flag, don't
silently truncate" without inventing a new top-level error path for what is, functionally, still a
successful response.

## Tests

```
cd evals/gate0
python -m unittest discover -s prototype_api -p "test_*.py" -v
```

- `test_session_buffer.py` — the in-memory buffer's own behavior (accumulate, reset, isolation,
  the max-frames safeguard).
- `test_cues.py` — the cue-mapping layer against the **real** exercise library (this is what
  proves the two over-cap cues above are real, not fixture artifacts).
- `test_main.py` — the HTTP contract: validation, structured errors, session lifecycle
  (reset/accumulate/isolation), the buffer-full safeguard, the cue/`cue_warning` behavior.
- `test_parity.py` — **the core proof**: for real golden-set fixtures (pushup with 2 reps + a
  bystander, squat with seeded knee-cave faults), across a full buffer, a mid-rep partial buffer,
  and frames split across multiple incremental calls, the API's `rep_count`/`rep_in_progress`/
  `phase`/`current_flags`/`insufficient_evidence`/`subject_lock_ok` are asserted equal to calling
  `run_detector` directly on the same frames.

## What changed in the shared detector to make this possible

`detector/rep_counter.py`'s `count_reps()` only ever returned **closed** rep events — correct for
the eval harness (a frozen clip either has a rep or it doesn't) but insufficient for "what is the
user doing right now, mid-rep". Rather than re-deriving that in this API (which would be exactly
the forking this whole service exists to avoid), the FSM loop was extracted into a shared
`_run_fsm()` helper; `count_reps()` is now a thin wrapper (byte-identical signature/behavior, all
existing tests pass unchanged) and a new `count_reps_with_state()` also returns the live phase.
`detector/adapter.py`'s `DetectedClip` now carries `phase`/`rep_in_progress`, which this API reads
directly — one implementation, read by two consumers, not two implementations kept in sync by
hand.

## Out of scope (this build)

- The PWA client (next prompt).
- The full `/v2` product API, auth, database.
- Stage-6 calibrated coaching cues.
- On-device JS/TS detection of any kind — the Python detector is authoritative; nothing here is a
  spec for a client-side reimplementation.
