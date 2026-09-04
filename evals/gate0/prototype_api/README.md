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

That runs the API alone. To run the **whole prototype** (API + PWA + your own webcam), see the next
section.

## Running the whole prototype locally (real webcam)

The fastest confidence check before any cloud deploy: your real camera, your real reps, on this
machine, no HTTPS and no cloud account needed.

```powershell
cd evals\gate0\prototype_api
.\run_local.ps1                      # bash twin: ./run_local.sh
```

It starts **both** processes and leaves them running until Ctrl+C:
`prototype_api` on `http://localhost:8000`, and the `kinetiq-demo3` PWA on `http://localhost:8080`
(served from the sibling repo — pass `-Demo3Path` if yours isn't next to `kinetiq-v2`). It sets
`PROTOTYPE_API_CORS_ORIGINS` to the PWA's local origin, waits for `/health`, and prints the URL.

**Why no HTTPS is needed here:** `http://localhost` is a **secure context** by browser spec, so
`getUserMedia` (the camera) works; and an HTTP page calling an HTTP API is same-scheme, so there's
no mixed-content block either. Both of those stop being true the moment you want this on a *phone*
— a different device reaches this machine by LAN IP or a public URL, neither of which is a secure
context over plain HTTP. That's the whole reason the cloud path exists.

Needs internet on first run: the PWA fetches the MediaPipe pose model from a CDN.

### Click-by-click (your part — the webcam session)

1. Open **`http://localhost:8080`**.
2. First time only: paste **`http://localhost:8000`** into the home screen's **API URL** field →
   **Save API URL**. (Stored in that browser's `localStorage`. It takes priority over `config.js`,
   so setting it here does **not** disturb the deployed Render URL baked into `config.js`.)
3. Pick **Squat**.
4. **Start** → allow camera when the browser asks.
5. Do **~5 squats**, in frame, side or diagonal to the camera. Watch the rep count and cue update.
6. **Stop** → **Validate**: enter the number of reps you *actually* did (this is the ground truth
   the accuracy number is computed against) plus view/lighting/fitness metadata.
7. **Summary** → **Export bundle** → saves a `.zip`.

### Score that export

Unzip the bundle, then — because faults are a human judgment call this tool never fabricates — open
`reps_template.csv` and fill the `faults` column per rep (semicolon-separated `error_id`s from
`exercises/squat.json`; blank = clean rep), and set `pt_verified` to `true` in `clips_template.csv`.
Then:

```
cd evals/gate0
python effectiveness_report.py --bundle-dir <unzipped-bundle-dir> --golden golden/
```

Prints rep-accuracy, severity-gated form precision/recall, and a parity check (does the live app's
`detected.json` match a fresh offline `run_detector` recompute over the exported `keypoints.jsonl`?
It should be identical — same deterministic algorithm, same frames — so a mismatch means a
client/API batch desync, not a scoring disagreement).

For a quick look before a trainer has labeled anything, `--allow-unverified` skips the sign-off gate
— but its precision/recall numbers are a preview, never a real result. Rep-accuracy is meaningful
either way, since that only needs the count you typed in step 6.

## CORS (needed for kinetiq-demo3, or any other browser client)

The PWA client is served from a different origin than wherever this process runs, so the browser
enforces CORS on every request — without it, every call is blocked before it reaches this code.
`PROTOTYPE_API_CORS_ORIGINS` (env var, comma-separated) sets the allowed origins; defaults to `*`
(any origin). That default is a **deliberate prototype-only choice** — no auth, no cookies, only
keypoints cross this API, so an open origin list doesn't expose anything sensitive. Do not carry
`*` into the real `/v2` product API.

```
PROTOTYPE_API_CORS_ORIGINS="https://your-pwa.example.com" python -m prototype_api
```

## Health check

`GET /health` — plain, unauthenticated (nothing to protect in a no-auth prototype), returns
`{"status": "ok", "supported_exercises": [...]}`. The deploy sanity check: confirm this responds
(`curl`, or just open the URL in a phone browser — a plain navigation, not a CORS-governed fetch)
*before* ever pointing the PWA at a deployed instance. `check_local.sh` (below) automates this
plus a real `/prototype/assess` round-trip.

## Deploying for a real gym session (HTTPS)

`kinetiq v3/DEPLOY_RUNBOOK.md` is the strategic runbook (why HTTPS, the smoke test, session-day
checklist) — this section is the concrete "how" it links to for the API side. `kinetiq-demo3`'s
own README has the PWA side.

The PWA needs an HTTPS URL for this API reachable from the tester's network — `localhost` only
works for a browser running on the same machine as this process. Two paths:

- **Path R — Render (recommended for anything global).** A real hosted HTTPS service. Testers
  anywhere can reach it; no laptop involved. This is the primary path — start here.
- **Path A — cloudflared quick tunnel (same-network / one-off).** Fastest to stand up, but it
  points at *your laptop*, which has to stay awake and online for the whole session, and the URL
  changes every restart.

### Path R — Render Docker web service (recommended, global)

`render.yaml` at the **repo root** is a ready-to-connect Render Blueprint for this service:
`runtime: docker`, `dockerfilePath: ./evals/gate0/prototype_api/Dockerfile`, `dockerContext: .`,
`healthCheckPath: /health`, and `PROTOTYPE_API_CORS_ORIGINS` declared with `sync: false` (so no
real value is committed — you set it in the dashboard once the PWA's URL exists).

**Connecting the repo to Render, and setting that env var, are your steps** — they need your Render
account; nothing here signs you up or provisions anything. The exact dashboard sequence, and the
chicken-and-egg wiring order between the two services, are in
`kinetiq v3/DEPLOY_RUNBOOK.md` §"Deploying to Render (the global path)".

**Free-tier spin-down** — the free plan idles a web service after ~15 minutes of no traffic; the
next request pays a **30–60s cold start**. That is on top of this service's own recompute cost, and
it lands on the *first* request of a session, exactly when a tester is watching. Mitigations are in
the runbook.

#### What is and isn't verified about the image

The `Dockerfile` was verified by **staging its exact `COPY` set into a clean tree** (nothing else
present) and running the literal container `CMD` against it. That proved:

- every module `run_detector` transitively imports resolves from the copied paths alone —
  `detector/`, `gate_config.py`, `golden_loader.py`, `exercise_lib.py`, `prototype_api/`, plus
  `backend/app/core/config.py` (reached via `gate_config.py`'s `sys.path` insert, as a PEP-420
  namespace package — there are no `__init__.py` files under `backend/app/`, and none are needed);
- the two pieces of **relative-path arithmetic** land correctly at the container's layout:
  `gate_config.py`'s `parents[2]/"backend"` → `/app/backend`, and `config.py`'s
  `parents[3]/"exercises"` → `/app/exercises`, from which all **14** exercise contracts load;
- `uvicorn`'s console script puts the CWD on `sys.path` (its `--app-dir` defaults to `""`, and
  `run()` does `sys.path.insert(0, app_dir)`) — so the `CMD`'s bare `prototype_api.main:app`
  resolves given the final `WORKDIR /app/evals/gate0`. Checked against the **installed uvicorn
  0.35.0**, the exact version `requirements.txt` pins, not from memory;
- `check_local.sh` passes against a server started that way.

Two **negative controls** confirmed the check isn't vacuous: with `backend/app/core/` removed the
app fails to import at all, and with `exercises/` removed it — see the warning below.

> ⚠️ **`/health` alone cannot prove the image is built correctly.** With `exercises/` missing,
> `load_exercise_library()` globs a non-existent directory, silently returns `{}`, and the service
> still boots and answers `GET /health` with **200 OK** — while every real `POST /prototype/assess`
> returns **500**. Render's health check would report that service *healthy*. So after deploying,
> always run `check_local.sh <url>` (below): its step 2 does a real assess round-trip and catches
> exactly this. (Noted, not fixed — changing `load_exercise_library()`'s behaviour is a detector-side
> change and out of scope here.)

**Not verified: an actual `docker build`.** Docker Desktop is not installed on this dev machine, and
installing it needs admin/UAC + WSL2 + likely a reboot — not something completable unattended. So
the base image and the `pip install` layer are unproven here; everything the `Dockerfile`'s own
`COPY`/`WORKDIR`/`CMD` lines control is proven by the staging test above. To prove the rest locally
before trusting Render:

```
cd kinetiq-v2
docker build -f evals/gate0/prototype_api/Dockerfile -t kinetiq-prototype-api .
docker run -p 8000:8000 -e PROTOTYPE_API_CORS_ORIGINS="http://localhost:8080" kinetiq-prototype-api
evals/gate0/prototype_api/check_local.sh http://127.0.0.1:8000
```

Otherwise Render's own build is the first real build — a failure there shows up in its build log,
and the `/health` check gates the rollout.

### Path A — cloudflared quick tunnel (same-network / one-off)

```
cd evals/gate0 && python -m prototype_api      # terminal 1 -- leave running
cd evals/gate0/prototype_api && ./tunnel.sh    # terminal 2
```

`tunnel.sh` checks `cloudflared` is installed and that `prototype_api` is already answering
`/health`, then starts a **cloudflared quick tunnel** and prints an `https://*.trycloudflare.com`
URL. Preferred over `ngrok`: ngrok's free tier shows an interstitial warning page on first load
that blocks the PWA's `fetch()` calls outright (a script can't click through it); cloudflared's
quick tunnel has no such page and needs no signup or account.

Install `cloudflared` first if you don't have it (`brew install cloudflared` / `winget install
--id Cloudflare.cloudflared` / see [Cloudflare's docs](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/)
for other platforms) — **this one install step is yours to run**, nothing here does it for you.

**Trade-off**: the laptop running both commands must stay on and connected for the whole session,
and the URL is not stable — it changes every time `tunnel.sh` (re)starts. Fine for a same-network
test you're supervising; not for handing a URL to testers elsewhere. For that, use Path R.

The image behind Path R has no pose runtime at all — this service only ever runs the geometry
detector over already-extracted keypoints, so it's just Python + fastapi/uvicorn/pydantic + the
detector/harness code. Fly/Railway work off the same `Dockerfile`; this repo just doesn't ship a
config for those specifically.

### After either path

```
./check_local.sh https://your-deployed-or-tunneled-url
```

Confirms `/health` and a real `/prototype/assess` round-trip both work against the URL you're
about to hand out — catches "wrong port" / "server not actually running" / a typo in seconds,
before anyone opens the PWA on a phone.

Then, regardless of path:
1. Set `kinetiq-demo3`'s API base URL to this HTTPS URL — `.\set-api-url.ps1 <url>` in that repo,
   or its README's deploy section.
2. Set `PROTOTYPE_API_CORS_ORIGINS` to the PWA's **exact** deployed HTTPS origin (scheme + host,
   no trailing slash, no path) — not `*`, once the PWA's real URL is known. Path A's `tunnel.sh`
   doesn't need this changed on ITS side (CORS governs which browser origins may call *this* API,
   not the reverse); Path R's `render.yaml` already declares the env var, you just set its value in
   the dashboard and restart.
3. Run the phone smoke test in `DEPLOY_RUNBOOK.md` before the real session.

The full ordered sequence across both services is in `kinetiq v3/DEPLOY_RUNBOOK.md` — it's
genuinely chicken-and-egg (each side needs the other's URL), so follow it in order rather than
improvising.

### Tear-down

- **Path A**: `Ctrl+C` the `tunnel.sh` terminal — the tunnel and its URL stop existing immediately.
- **Path R**: **suspend** the Render web service in the dashboard when the test round is done — the
  URL is public and unauthenticated while it's up. Nothing persists server-side to clean up (an
  in-memory session buffer only, gone on process exit regardless); suspending is about closing the
  open door, not about data. Resume or redeploy for the next round.

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
  "cue_warning": null,
  "reps": [
    {"idx": 1, "flags": [], "insufficient_evidence": []},
    {"idx": 2, "flags": [], "insufficient_evidence": []}
  ]
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
| `reps` | list[{idx, flags, insufficient_evidence}] | **not part of the original 7-field spec either** — the FULL per-rep history (every completed rep, not just the latest). `current_flags`/`insufficient_evidence` are redundant with `reps[-1]` and kept only for backward compatibility with the original contract; a new client should read `reps`. Necessary because a client polling every ~300–500ms (kinetiq-demo3) can have 2+ reps close between two calls -- `current_flags` alone would silently lose the intermediate rep's flags, corrupting exactly the data `labeling/`/`form_pr.py` score later. |

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
ones this check found (not hypothetical, though both have since been shortened in the exercise
library and no longer trip it — `test_cues.py` keeps a synthetic-fixture test for the mechanism
itself so this coverage doesn't depend on real cue copy staying broken):

- `squat.json`'s `shallow_depth` cue was "Sit a little deeper — hip crease to knee level" (10 words)
- `pushup.json`'s `shallow_pushup` cue was "Go a little lower — elbows to 90 degrees" (9 words)

Both exceeded the cap once the em dash was counted as a token by the same convention
`aggregate.py` already uses. When the API returns an over-cap cue, the full (untruncated) text is
still returned in `coaching_cue`, `cue_warning` is set to a message naming the flag/word-count,
and a server-side warning is logged. `cue_warning` is **not** one of the 7 fields the build task
originally specified — it was added specifically to satisfy "flag, don't
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
