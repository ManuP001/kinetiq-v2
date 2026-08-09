# ARCHITECTURE.md — Kinetiq v2

> System design and Architecture Decision Records for the v2 re-architecture.
> This is the canonical place to record any deviation from the `PRD_v2.md` baseline.
> Last updated: 2026-07-06

---

## 1. System Overview

Dual-stack: React Native mobile (TypeScript) + FastAPI backend, Supabase (Postgres + pgvector + Auth +
RLS) for state, tiered models for intelligence. The defining v2 change is a **two-layer Vision Agent**
and a **six-agent backend** whose schema exists in full from day one but whose behaviour ships by phase.

```
┌───────────────────────────────────────────────────────────┐
│                     React Native App                       │
│   Camera · MediaPipe Pose (on-device) · Session UI         │
│   Deterministic rep counter + safety rules run HERE         │
└───────────────┬───────────────────────────────────────────┘
                │  keypoints + derived features ONLY (never pixels)
                │  POST /v2/sessions/{id}/assess
                ▼
┌───────────────────────────────────────────────────────────┐
│                      FastAPI Backend                       │
│                                                            │
│  HOT PATH (<120ms, no network LLM)                         │
│   Vision Agent · deterministic layer (authoritative)       │
│      └─ rep count + safety flags + base form score         │
│                                                            │
│  WARM PATH (<600ms, cheap model)                          │
│   Coaching Agent · set summaries, synthesised cues         │
│      (health-context + memory aware)                       │
│                                                            │
│  COLD PATH (async, strong model)                          │
│   Vision Agent · model-assisted reasoning (advisory, P2)   │
│   Planner Agent (P2) · Memory Agent (P2) · Engagement (P3) │
│                                                            │
│  Progress Agent · deterministic, writes session + streak   │
└───────────────┬───────────────────────────────────────────┘
                │
        ┌───────┴────────┐
        ▼                ▼
 ┌─────────────┐   ┌──────────────┐
 │  Supabase   │   │  Model tiers │
 │ Postgres +  │   │ hot/warm/cold│
 │ pgvector +  │   └──────────────┘
 │ Auth + RLS  │
 └─────────────┘
```

Three model tiers map to three latency paths. The hot path never makes a network LLM call — it is the
v1 deterministic engine, preserved. The cold path is where v2 spends its stronger model budget, off the
critical latency line.

---

## 2. Architecture Decision Records

ADRs 001–006 below carry forward from v1 (`../kinetiq/ARCHITECTURE.md`). ADRs 100+ are v2-specific and
are where the re-architecture and any `PRD_v2` baseline deviations are recorded.

### Carried forward from v1 (still in force)

- **ADR-001 — On-device pose estimation.** Only keypoints leave the device. Privacy, latency, cost.
  **Reaffirmed and strengthened in v2** (see ADR-101).
- **ADR-002 — Deterministic form logic.** Geometric rules for form. **Amended by ADR-100** — still the
  authoritative layer, now augmented by an advisory model layer.
- **ADR-004 — Progress Agent has no LLM.** Streak/PR logic is deterministic. **Unchanged.**
- **ADR-005 — Supabase as primary DB.** **Unchanged**, extended with pgvector (ADR-103).
- **ADR-006 — No RAG in MVP.** **Amended by ADR-103** — RAG/memory schema exists now, behaviour in P2.

### v2 ADRs

#### ADR-100 — Two-layer Vision Agent (deterministic-authoritative + model-advisory)
**Decision:** Keep the deterministic geometry layer as the authoritative source for rep count and
safety flags. Add an advisory, model-assisted reasoning layer (Phase 2) that consumes keypoint
time-series + derived features and may refine the form score and add nuanced cues, but **cannot
override rep count or safety flags.**
**Rationale:** v1's determinism gave auditability, testability, and a < 120 ms hot path; v1's ceiling
was nuance. The stronger v2 model budget can add nuance without surrendering those properties — as long
as the model layer is advisory and the deterministic layer holds veto.
**Tradeoff:** Two code paths to maintain and a reconciliation rule (deterministic wins on conflict).
Accepted: the alternative — a model in the hot path — breaks latency, cost, and auditability at once.
**Status:** Accepted. Model layer default-OFF until the ADR-102 eval gate passes.

#### ADR-101 — Pixels never reach any model
**Decision:** The model-assisted form layer consumes only keypoints and derived numeric features
(joint-angle curves, tempo, symmetry, ROM), never image data.
**Rationale:** Preserves ADR-001's privacy invariant even as we add model intelligence. Also keeps the
model input small and cheap.
**Tradeoff:** The model cannot see things keypoints miss (e.g. exact foot placement texture). Accepted
— privacy is non-negotiable and keypoint features cover the MVP error modes.
**Status:** Accepted, binding.

#### ADR-102 — Advisory model layer gated by expert-agreement eval
**Decision:** The model-assisted form score is default-OFF and may only be turned on by default after
it clears an expert-agreement eval (form score within agreed tolerance of expert raters across the 3
exercises).
**Rationale:** A confident-but-wrong form score erodes trust and can mislead on safety. Gate it like
any safety-relevant capability.
**Tradeoff:** Delays the nuance benefit until data + eval exist. Accepted.
**Status:** Accepted. Eval bar to be set in `evals/` before P2.

#### ADR-103 — pgvector + Memory schema from day one, behaviour in Phase 2
**Decision:** Provision pgvector and create the `form_trends` / memory tables in the initial migration;
populate and query them only in Phase 2.
**Rationale:** Avoids the v1 mistake of deferring data collection. Per-exercise form history must
accumulate from the first session so the Memory Agent has data when it ships.
**Tradeoff:** Slightly larger initial schema, unused columns early. Cheap insurance.
**Status:** Accepted.

#### ADR-104 — Tiered model routing
**Decision:** Three tiers — deterministic/on-device (hot), cheap model (warm: set summaries, live
nuance), strong model (cold: weekly recap, re-engagement, planning, memory synthesis). All model names
are config keys.
**Rationale:** Spend capability where it changes outcomes; stay cheap and fast where users feel latency.
**Tradeoff:** More config surface and routing logic. Accepted; it's the core cost/quality lever.
**Status:** Accepted.

#### ADR-105 — Full PRD_v2 data model now, behaviour by phase
**Decision:** `personal_records`, `badges`, `challenges`, `weekly_summaries`, `accountability_pairs`,
health context, equipment, preferred time/duration all exist in the initial schema. Only MVP behaviours
write to the MVP subset.
**Rationale:** Adding an onboarding field or table later is cheap; not having the data when the feature
arrives forces a re-onboarding flow that kills retention (PRD_v2 §8.1).
**Tradeoff:** Schema larger than MVP behaviour requires. Accepted.
**Status:** Accepted.

#### ADR-106 — Health context is encrypted, RLS-scoped, and legally gated
**Decision:** `health_context` is sensitive data: encrypted at rest, RLS-restricted to the owner,
excluded from analytics payloads, and only passed to the Coaching Agent as a minimal structured
modifier. Production collection is blocked behind Legal sign-off (feature flag).
**Rationale:** DPDP Act compliance and liability (PRD_v2 §12 Q2).
**Tradeoff:** A launch dependency on Legal. Accepted; the loop ships without health collection if needed.
**Status:** Accepted.

#### ADR-107 — `/v2` API namespace, not edits to `/v1`
**Decision:** v2 endpoints live under `/v2/`. v1 contracts are not edited.
**Rationale:** Clean migration, parallel running, no breakage of any v1 client.
**Status:** Accepted.

#### ADR-108 — Streak-at-risk push notification moves into Phase 1
**Decision:** FCM/APNs infrastructure ships in Phase 1, scoped to exactly one notification type: the
daily streak-at-risk push (default 7pm, configurable, ≤1/day, user-controllable). The full
re-engagement/notification suite remains Phase 3.
**Rationale:** PRD_v2 §7.1 names the streak-at-risk notification as the *only* MVP cue mechanism, but
the stack table placed FCM in Phase 3 — the MVP's primary retention lever depended on infrastructure
that wasn't scheduled for MVP. Resolves the contradiction in favour of the retention thesis (BG-1).
**Tradeoff:** Notification infra earlier than strictly minimal. Accepted — a single scheduled push is
cheap, and D3 return (>50% gate) plausibly depends on it.
**Status:** Accepted.

#### ADR-109 — Offline-first session: the device is authoritative for the hot path
**Decision:** The deterministic layer — rep counting, safety flags, base form score, and static cue
selection from the bundled Exercise Library — runs **entirely on-device**. A workout session must
complete with zero network. `POST /v2/sessions/{id}/assess` is **not** a per-frame/per-rep blocking
call: the app uploads batched keypoint-derived `rep_metrics` at set boundaries (or session end, or
next connectivity) for persistence, warm-path set summaries, and Phase-2 advisory scoring. The
backend never returns an authoritative rep count to the client mid-session.
**Rationale:** The prior contract implied a network round-trip inside the <120 ms hot path — fatal on
Indian gym/home connectivity and inconsistent with §5.2's "can run with zero network." Offline-first
also strengthens the privacy story: nothing needs to leave the device for the core loop to work.
**Tradeoff:** The Exercise Library (rules, thresholds, cues) must be bundled/synced to the client, and
server-side state is eventually-consistent with the device during a session. Accepted.
**Status:** Accepted. Supersedes the per-frame reading of `/assess` in API_CONTRACTS.md.

#### ADR-110 — Gate 0 (camera-vision spike) + onboarding canon + v1 evidence correction
**Decision:** Three housekeeping decisions recorded together. (1) **Evidence correction:** v1 never
built real camera vision — the v1 artefact was a no-camera PWA UX demo. Claims that v1 "validated
on-