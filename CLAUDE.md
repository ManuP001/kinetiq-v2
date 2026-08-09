# CLAUDE.md — Kinetiq v2 (Virtual Physical Trainer)

> Root governance file for the v2 build. Load this first.
> Companion docs: `BRD.md` (business requirements), `ARCHITECTURE.md` (system design + ADRs),
> `API_CONTRACTS.md` (service contracts), `PRD_v2.md` (carried forward from v1, treated as a
> **baseline to question, not a frozen spec**).
> Last updated: 2026-07-06

---

## 0. How to Read This Repo

Kinetiq v2 is a re-architecture, not a refactor. v1 (`../kinetiq`) **designed** a deterministic,
geometry-only vision stack and a 3-agent backend, and validated the session UX via a no-camera PWA
demo (`kinetiq-demo`: tap-to-count reps, simulated cues). **Real camera-based rep counting was never
built or measured in v1.** Gate 0 (ADR-110) exists to close that evidence gap via the `kinetiq-demo2`
camera spike before any v2 backend/agent build. v2 assumes a **stronger model budget** and rebuilds
the intelligence layer around it.

The single most important framing: **PRD_v2 is a baseline.** Its MVP scope, its phase gates, and its
feature list are starting points we are explicitly licensed to challenge. When a PRD_v2 constraint
conflicts with a better design that the v2 model budget makes possible, raise it — do not silently
comply, and do not silently override. Flag the tension, propose the change, get a decision, record it
as an ADR in `ARCHITECTURE.md`.

Order of precedence when documents disagree:

1. `CLAUDE.md` (this file) — engineering standards and the re-architecture mandate
2. `ARCHITECTURE.md` ADRs — recorded design decisions
3. `BRD.md` — what the business needs to be true
4. `PRD_v2.md` — product baseline (questionable)

---

## 1. What Changed from v1 → v2 (The Mandate)

| Dimension | v1 | v2 |
|---|---|---|
| Form detection | Deterministic geometric rules only (no LLM in vision path) | **Hybrid**: deterministic fast-path for rep counting + a model-assisted reasoning layer for nuanced form scoring, novel error modes, and exercises without hand-written rules |
| Agent count | 3 (Vision, Coaching, Progress) | **6** (Vision, Coaching, Planner, Memory, Progress, Engagement) — Planner/Memory/Engagement gated by phase but **designed into the schema from day one** |
| Personalisation data | `goals`, `fitness_level` collected, used "post-MVP" (i.e. never) | **Collect-all-at-onboarding**: health context, equipment, preferred time/duration captured in MVP, schema-ready for Phase 2+ |
| Memory | Session-scoped only | Long-term per-user, per-exercise form trends via pgvector (Phase 2), schema present from day one |
| Coaching model | Claude Haiku, static cues from library | Tiered: cheap model on the hot path, **stronger model (Sonnet-class) for set summaries, weekly recaps, and re-engagement**, all health-context- and memory-aware |
| Gamification | Streak only | Streak + PR flags (MVP), badges/challenges/social (later) — **all tables and events defined now**, populated by phase |
| Data model | 4 tables | Full PRD_v2 model: users+health, sessions, rep_metrics, streaks, personal_records, badges, challenges, weekly_summaries, accountability_pairs, exercises+contraindications |

**Rule:** Build behaviour by phase, but build the **schema and contracts for the full model now.** The
expensive v1 mistake was deferring data collection until the feature shipped, which meant the data
never existed when the feature arrived. We do not repeat that.

---

## 2. Privacy Invariant (Non-Negotiable, Unchanged from v1)

This survives the re-architecture untouched and overrides any design that conflicts with it.

- **Raw video never leaves the device.** Pose estimation runs on-device. Only keypoint data (and,
  where the model-assisted path is used, derived numeric features over keypoints) crosses the network.
- No frame, image, or video buffer is transmitted to any server or third-party model — including the
  model-assisted form reasoning layer. That layer consumes **keypoint time-series and derived
  features**, never pixels.
- No biometric data persisted beyond the session summary without explicit, revocable user consent.
- Health context (Section 7) is sensitive personal data under India's DPDP Act. It is stored
  encrypted at rest, access-controlled by RLS, and never sent to any model except as the minimal
  structured modifier defined in the coaching contract.

If a proposed feature requires sending pixels off device, it is out of scope until a separate,
explicitly-approved privacy review says otherwise.

---

## 3. Stack

| Layer | Technology | Role |
|---|---|---|
| Mobile | React Native (TypeScript, strict) | Camera, on-device pose, session UI |
| Pose estimation | MediaPipe Pose (on-device), MoveNet fallback | 33-keypoint skeleton, on-device only |
| Backend | FastAPI (Python 3.12+), Pydantic v2 | Orchestration, agents, form reasoning |
| Database | Supabase (Postgres 15 + Auth + RLS) | All persistent state |
| Vector store | pgvector (same Postgres) | Memory Agent embeddings (Phase 2) |
| Models | Tiered (see §5) | Coaching, summaries, planning, memory synthesis |
| Analytics | PostHog | Funnel, retention, rep-accuracy events |
| Payments | Razorpay (India), Stripe (intl, later) | Premium tier |
| Notifications | FCM / APNs (**Phase 1**: single daily streak-at-risk push only — ADR-108; full re-engagement suite Phase 3) | Streak-at-risk cue, re-engagement |

All constants — model names, thresholds, latency budgets, streak windows — live in
`backend/app/core/config.py`. **No magic numbers inline, anywhere.** This rule is inherited from v1
and strengthened: thresholds that v1 hardcoded in form rules (`0.05` knee-cave margin, etc.) become
named, per-exercise, config-driven values in v2.

---

## 4. Engineering Standards

Carried forward from v1 `backend/CLAUDE.md`, still in force:

- **Python 3.12+**, async-first. Every route and DB call is `async def`. No blocking I/O in handlers.
- **Pydantic v2** for every request/response. No untyped `dict` in handlers. `schemas.py` is the
  single source of truth; TypeScript types are generated from it.
- **Structured logging only** (`structlog`). No `print()`. Every agent action logs with a `trace_id`.
- **Absolute imports**, type annotations on every signature.
- **API versioned under `/v2/`.** (v1 used `/v1/`; v2 endpoints are a new namespace, not edits to v1.)
- **Migrations are numbered and append-only.** Never edit an applied migration. RLS enabled on every
  table, policy added in the same migration as the `CREATE TABLE`.
- **Prompts live in `prompts/` as versioned files**, never inline in Python. Always set `max_tokens`.
  Always log `input_tokens`/`output_tokens`.
- **Fail loudly.** An agent that cannot produce a valid output returns a typed error with a code —
  never a plausible-looking invalid result. This matters more in v2 because the model-assisted path
  can produce confident nonsense; the deterministic guardrail must be able to veto it.

---

## 5. Agent Architecture (v2)

Six agents. Three exist in MVP; three are schema-and-contract-ready but behaviour-gated.

### 5.1 Model Tiering

The re-architecture's core lever is spending model capability where it changes outcomes and staying
cheap on the hot path.

| Path | Latency budget | Model tier | Why |
|---|---|---|---|
| Per-rep form scoring (hot) | < 120 ms | **Deterministic + on-device** | No network LLM call. Geometry + a small on-device classifier. |
| Set summary / live nuance | < 600 ms | **Cheap model (Haiku-class)** | Short, frequent, latency-sensitive. |
| Weekly recap / re-engagement / plan generation | seconds, async | **Strong model (Sonnet-class)** | Quality and personalisation matter; not latency-bound. |
| Memory synthesis (form-trend narratives) | async, batch | **Strong model** | Reasoning over history; runs off the hot path. |

Model names are config keys (`HOT_PATH_MODEL`, `COACHING_MODEL`, `PLANNER_MODEL`, `MEMORY_MODEL`),
never literals.

### 5.2 Vision Agent — the central re-architecture

**v1:** pure deterministic geometry, no LLM, ever.
**v2:** two-layer, deterministic-first.

1. **Deterministic layer (always on, on-device, authoritative for rep counting):** the rep-counting
   state machine and the hard safety rules (knee cave, depth, lumbar flexion) from v1, now
   config-driven and per-exercise. This layer is fast, testable, and is the **source of truth for rep
   count and safety flags**. It can run with zero network.
2. **Model-assisted reasoning layer (Phase 2, optional, advisory):** when enabled, a model reasons
   over a window of keypoint time-series + derived features (joint-angle curves, tempo, symmetry) to
   produce a *nuanced* form score and detect error modes that have no hand-written rule. This layer
   is **advisory**: it can refine the score and add soft cues, but it **cannot override a
   deterministic safety flag and cannot change the rep count.**

   - Consumes keypoints/features only — never pixels (see §2).
   - Output carries a confidence; low confidence falls back to the deterministic score.
   - Disabled by default in MVP. The schema (`rep_metrics`, `form_assessments`) records the inputs it
     would need so the feature can be trained/evaluated on real data before it ships.

This split is what lets v2 add nuance without sacrificing v1's auditability or its < 120 ms hot path.

### 5.3 Coaching Agent

Cue selection on the hot path from the Exercise Library (deterministic, as v1). Set summaries and any
synthesised cue use the cheap model. **Health-context- and memory-aware** in v2: the coaching contract
takes the user's `health_context` and (Phase 2) recent form trends as structured modifiers.

Non-negotiable coaching rules (from v1 + PRD_v2 §7.4):
- **Positive before correction**, always. Acknowledge a correct element of the rep before flagging.
- Never give medical advice. Pain → "Please stop and consult a qualified healthcare professional."
- Never fabricate biomechanics. All cues grounded in the Exercise Library.
- Confidence-scaled delivery: directive ≥ 0.75, suggestion below.
- Health modifiers: injury flags soften corrections to suggestions; hypertension adds a breathing cue.
- Real-time cues ≤ 8 words; set summaries ≤ 30 words. Hard caps, enforced in code.

### 5.4 Planner Agent (Phase 2, schema-ready now)

Generates personalised weekly plans from `goals + fitness_level + health_context + session history`.
Strong-model tier. Writes to `workout_plans` / `challenges`. Adaptive difficulty: rep target rises
when form score is sustained high. Contraindications gate exercise selection.

### 5.5 Memory Agent (Phase 2, schema-ready now)

Maintains long-term, per-exercise form trends (pgvector). Feeds the Coaching Agent specific,
historically-grounded cues ("left-knee cave flagged 3 fewer times this week") and the Engagement Agent
AI milestones. Strong-model tier, async/batch.

### 5.6 Progress Agent

Deterministic, no LLM (as v1). Writes session + rep_metrics, updates streak, detects and writes
personal records, emits PostHog events. Streak window and PR thresholds are config.

### 5.7 Engagement Agent (Phase 3, schema-ready now)

Owns streak-at-risk cues, re-engagement messaging (differentiated by lost-streak length per PRD_v2
§7.3), badges, challenges, weekly summaries, and (later) social. **Never punishes, never spams**
(≤ 1 push/day), every message references specific user data. Re-engagement copy is generated by the
strong model from real session data, never templated generically.

### 5.8 Shared agent rules (from v1, still binding)

- Define input + output Pydantic schema before writing logic.
- No agent calls another agent directly — they communicate through Supabase state or the orchestration
  layer.
- Every inference output carries an explicit confidence.
- One `trace_id` per session, threaded through every agent call and log line.

---

## 6. Exercise Library Contract

Three MVP exercises (squat, push-up, lunge); schema designed to scale past three without change. The
library is the **contract between exercises and the Vision/Coaching agents** and must be seeded and
queryable before agent development — a hard dependency, as in v1.

v2 additions to each exercise record (see `exercises/*.json` and the SQL/Pydantic schema):
- `contraindications` — per health-context modifications and where to surface them (PRD_v2 §8.4).
- `reference_keypoints` with **per-exercise, named thresholds** (not global constants).
- `rep_counting` phase definitions (already present in v1 JSON, formalised in v2).
- `model_assist` block — the feature window + which derived features the reasoning layer should
  compute for this exercise (inert until Phase 2).

---

## 7. Health Context & Personalisation (PRD_v2 §8 — adopted, hardened)

- All personalisation data is collected at onboarding even when used only later. Onboarding grows to 4
  screens; Screen 3 is health context + equipment + preferred time/duration.
- Health context is a **coaching modifier, not a medical form.** The exact non-medical disclaimer copy
  from PRD_v2 §8.2 must appear on-screen and in ToS. **Legal sign-off is a hard gate before collecting
  `health_context` in production** (PRD_v2 §12 Q2) — flag this in the build, do not ship past it
  silently.
- MVP personalisation that must actually work: contraindication callouts on exercise detail, softened
  coaching tone for injury flags, fitness-level default sets/reps, goal-based welcome copy.

---

## 8. Gamification (PRD_v2 §9 — adopted)

Design principles are binding: **earned not decorative, intrinsic before extrinsic,
cohort-appropriate, never punish.** The "What Not to Build (Ever)" list in PRD_v2 §9.6 is a hard
exclusion list — no energy systems, no pay-to-recover-streak, no comparative shame, no notification
spam, no dark patterns, no unearned rewards. Treat violations as build-blocking.

MVP gamification: streak + PR flags only, both deterministic. Everything else is schema-ready,
behaviour-gated.

---

## 9. Eval Gates (baseline from PRD_v2 §6 — questionable)

These carry over as the starting bar. Because PRD_v2 is a baseline, propose revisions where the v2
architecture changes what's measurable (e.g. the model-assisted form layer needs a separate
LLM-as-judge form-quality eval that v1 didn't have).

- **Gate 1 (Vision):** rep accuracy > 90%, form-flag accuracy > 80%. Add for v2: model-assisted form
  score agreement with expert raters before that layer is allowed on by default.
- **Gate 2 (Retention):** completion > 70%, D3 return > 50%.
- **Phase 2 (Coaching):** cue quality > 4/5 on LLM-as-judge, hallucination < 2%.
- **Phase 3 (Engagement):** D7 > 40% (habit cohort), D14 > 25%, D30 > 15%.

Rollback rule (from v1): if Gate 1 fails after 2 tuning rounds, stop and diagnose the Vision Agent. Do
not paper over poor detection with better copy.

---

## 10. Files in This Repo

| File | Purpose |
|---|---|
| `CLAUDE.md` (this) | v2 governance + re-architecture mandate |
| `BRD.md` | Business requirements |
| `PRD_v2.md` | Product baseline (carried from v1, questionable) |
| `ARCHITECTURE.md` | System design + ADRs (the place to record any PRD_v2 override) |
| `API_CONTRACTS.md` | TypeScript ↔ Python service contracts (`/v2/`) |
| `backend/migrations/001_initial_schema_v2.sql` | Full v2 data model |
| `backend/app/core/schemas.py` | Canonical Pydantic v2 schemas |
| `exercises/{squat,pushup,lunge}.json` | Exercise library with contraindications |
| `prompts/` | Versioned agent prompts |
| `evals/` | Eval logs and judge prompts |

---

## 11. What v2 Still Does NOT Do

- Does not transmit or store raw video (ever — see §2).
- Does not let the model-assisted layer override deterministic rep count or safety flags.
- Does not collect `health_context` 