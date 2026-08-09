# BRD.md — Business Requirements Document: Kinetiq v2

> Virtual Physical Trainer (VPT)
> Companion to `PRD_v2.md` (product baseline) and `CLAUDE.md` (engineering governance).
> The BRD states *what the business needs to be true*; the PRD states *what we build*; this document
> takes precedence over the PRD where they conflict on business intent.
> PRD_v2 is treated as a baseline open to revision — see §11.
> Last updated: 2026-07-06 · Status: Draft for review

---

## 1. Document Purpose

This BRD captures the business rationale, stakeholders, scope, requirements, and success criteria for
Kinetiq v2. It exists to align product, engineering, design, and leadership on *why* v2 is being built
and *what outcomes* define success — independent of implementation detail. Where the PRD answers "what
feature," this document answers "what business problem and what proof it's solved."

---

## 2. Business Context & Problem Statement

Home and gym exercisers lack real-time feedback. Two failure modes follow, and they are not equally
expensive:

1. **Poor form → injury risk and ineffective training.** Visible, but affects a minority of sessions.
2. **No accountability loop → users quit before results.** This is the common and expensive failure:
   the majority of fitness-app users churn inside the first week.

The v1 MVP validated the **session UX** — via a no-camera PWA demo with tap-to-count reps and
simulated coaching cues — and confirmed the flow feels "coached, not just tracked." It did **not**
validate that on-device, camera-only rep counting is technically achievable: no real vision pipeline
was built or measured in v1. That claim is unproven and is now gated behind **Gate 0** (the
`kinetiq-demo2` camera spike — see ADR-110): >90% rep accuracy on real mid-range Android devices
before any v2 agent/backend build proceeds. v1 also did not prove durable retention, and it left two
structural gaps:

- **The personalisation gap:** v1 collected goals and fitness level but deferred their use
  indefinitely, so the data needed to personalise was never actually exercised.
- **The intelligence ceiling:** v1's deterministic-only vision and Haiku-only coaching capped how
  nuanced and personal the experience could become.

v2 exists to close both gaps and to convert a working demo into a retention engine.

---

## 3. Business Goals & Objectives

| # | Business goal | Measurable objective |
|---|---|---|
| BG-1 | Win on habit formation, not just form correction | D7 retention > 40% (habit cohort), D30 > 15% |
| BG-2 | Prove the core loop is trustworthy | Rep accuracy > 90%, form-flag accuracy > 80%, completion > 70% |
| BG-3 | Make the product feel personal from session one | Health-context callouts + personalised coaching live in MVP; measured "feels personalised" in beta |
| BG-4 | Build a defensible coaching-quality moat | Coaching cue quality > 4/5 (LLM-as-judge), hallucination < 2% |
| BG-5 | Establish a credible path to revenue | Freemium live; paywall shown only post-value; premium conversion baseline established |
| BG-6 | Do all of the above without compromising privacy or safety | Zero raw-video transmission; zero medical-advice incidents; DPDP-compliant health-data handling |

---

## 4. Stakeholders

| Stakeholder | Interest in v2 |
|---|---|
| Product owner | Retention outcomes, scope discipline, phase-gate decisions |
| Engineering | Re-architecture feasibility, latency/cost budgets, data model durability |
| Design / UX | Onboarding flow, habit-loop moments, positive-reinforcement UX |
| Data / ML | Vision accuracy, model-assisted form layer evaluation, coaching evals |
| Legal / Compliance | Health-data (DPDP Act) sign-off, medical-disclaimer placement, ToS |
| Founders / Leadership | Market positioning, monetisation, funding-relevant retention metrics |
| End users (Cohort 1 & 2) | A trainer that is accurate, encouraging, private, and worth returning to |

---

## 5. Users & Market

**Cohort 1 — Habit Formation:** beginners and inconsistent exercisers needing structure, streaks, and
gentle accountability. India Tier-1 cities, English-first, age 22–38.

**Cohort 2 — Assisted Training:** active users and gym-goers wanting precision form correction and
adaptive programming. Same demographic, higher fitness literacy.

Both cohorts share one free-tier MVP. No separate UX tracks until post-MVP D7 data justifies the split
(carried from PRD baseline). Premium features lean toward Cohort 2.

---

## 6. Scope

### 6.1 In Scope (v2, by phase)

**Phase 1 (MVP):** 3 bodyweight exercises; on-device rep counting; deterministic basic form detection;
session summary with form score; streak; PR flags; 4-screen onboarding capturing full personalisation
data; health-context callouts and softened coaching; free tier only.

**Phase 2 (Intelligence):** model-assisted form reasoning layer (advisory); Planner Agent
(personalised weekly plans); Memory Agent (per-exercise form trends); memory-aware coaching; adaptive
difficulty; premium tier launch.

**Phase 3 (Engagement):** badges, weekly challenges, weekly progress summaries, streak-at-risk and
re-engagement notifications, opt-in social (accountability pairs / leaderboards).

**Phase 4 (Agentic):** proactive plan adjustment, AI-generated personal milestones, optional health-app
integration.

### 6.2 Out of Scope (all phases)

Wearable integration; nutrition tracking as a primary feature; live human coaching; real-time
multi-user sessions; medical-grade rehabilitation programmes. Kinetiq is **not a medical device.**

### 6.3 Schema-now, behaviour-later principle

The full Phase 1–4 data model is built in MVP even though behaviour ships by phase. This is a business
requirement, not an engineering preference: deferring data collection cost v1 its personalisation
ability. **BR: no personalisation-relevant field is deferred past MVP onboarding.**

---

## 7. Business Requirements

Each requirement is testable and phase-tagged. `MUST` = release-blocking for its phase.

### 7.1 Core Loop & Vision

- **BR-1 (MUST, P1):** A user can select an exercise, perform it, and have reps counted on-device with
  > 90% accuracy across 3 lighting conditions and 3 body types.
- **BR-2 (MUST, P1):** Basic form errors (knee cave, shallow depth, elbow flare) are flagged with
  > 80% agreement with a human reviewer.
- **BR-3 (MUST, P1):** Rep count and safety flags come from the deterministic layer and are never
  overridden by any model output.
- **BR-4 (SHOULD, P2):** A model-assisted layer refines form scoring and detects rule-less error modes
  from keypoint features only, gated by an expert-agreement eval before default-on.

### 7.2 Habit & Retention

- **BR-5 (MUST, P1):** Every completed session updates a streak and renders a session-summary reward.
- **BR-6 (MUST, P1):** The Day-1→Day-2 return moment surfaces a specific form-score comparison on the
  same exercise (improved → say so; not → say what to focus on).
- **BR-7 (MUST, P3):** Lapsed users receive re-engagement differentiated by lost-streak length, never
  guilt-framed, always referencing specific user data.
- **BR-8 (MUST, all):** Maximum one push notification per day, user-controllable.

### 7.3 Personalisation & Health

- **BR-9 (MUST, P1):** Onboarding collects goals, fitness level, health context, equipment, preferred
  time, and preferred duration — even where used only later.
- **BR-10 (MUST, P1):** A user with a relevant health flag sees a contraindication callout on the
  affected exercise and receives softened, suggestion-framed coaching for related corrections.
- **BR-11 (MUST, P1):** The non-medical disclaimer appears in onboarding and ToS.
- **BR-12 (MUST, P1):** Health-context collection in production is blocked until Legal sign-off.

### 7.4 Coaching Quality & Safety

- **BR-13 (MUST, all):** Every form assessment leads with a positive signal before any correction.
- **BR-14 (MUST, all):** No medical advice; any pain signal routes to "stop and consult a professional."
- **BR-15 (MUST, all):** No fabricated biomechanics; cues grounded in the Exercise Library.
- **BR-16 (MUST, P2):** Coaching cue quality > 4/5 (LLM-as-judge), hallucination < 2%.

### 7.5 Privacy & Compliance

- **BR-17 (MUST, all):** Raw video never leaves the device; only keypoints/derived features transit.
- **BR-18 (MUST, all):** Health context stored encrypted, RLS-scoped, DPDP-compliant; leaderboards
  default to anonymous.
- **BR-19 (MUST, P1):** No biometric data persisted beyond session summary without explicit consent.

### 7.6 Monetisation

- **BR-20 (MUST, P2):** Freemium live; premium gates personalised plans, coach memory, advanced
  analytics, full exercise library, streak freeze.
- **BR-21 (MUST, P2):** Paywall never appears before the user has completed session 1; first paywall is
  a non-blocking post-session-1 callout.
- **BR-22 (MUST, P2):** Payments via Razorpay (India, UPI + cards); Stripe international later.

### 7.7 Gamification Integrity

- **BR-23 (MUST, all):** Excluded patterns from PRD_v2 §9.6 are build-blocking: no energy/lives, no
  pay-to-recover-streak, no comparative shame, no notification spam, no dark patterns, no unearned
  rewards.
- **BR-24 (MUST, all):** All rewards are earned by real behaviour; streak loss is visible but never
  shamed; social and leaderboards are opt-in.

---

## 8. Success Metrics (Acceptance Criteria)

| Phase | Metric | Target |
|---|---|---|
| P1 | Rep-counting accuracy | > 90% |
| P1 | Form-flag accuracy | > 80% |
| P1 | Session completion rate | > 70% |
| P1 | D3 return rate | > 50% |
| P2 | Coaching cue quality (LLM-as-judge) | > 4/5 |
| P2 | Coaching hallucination rate | < 2% |
| P2 | Model-assisted form-score expert agreement | gate TBD, set before default-on |
| P3 | D7 retention (habit cohort) | > 40% |
| P3 | D14 retention | > 25% |
| P3 | D30 retention | > 15% |
| All | Raw-video transmission incidents | 0 |
| All | Medical-advice / unsafe-cue incidents | 0 |

---

## 9. Assumptions

- On-device MediaPipe is accurate enough on mid-range Android in good lighting; MoveNet cloud fallback
  covers the low-confidence tail (keypoints only, never pixels).
- A stronger model budget is available for off-hot-path work (summaries, planning, memory, re-engagement).
- Beta users (India Tier-1, English) are representative enough to validate the loop.
- Legal sign-off on health data is obtainable on a timeline that does not block MVP launch of the
  non-health portions.

---

## 10. Risks & Dependencies

| Risk | Impact | Mitigation |
|---|---|---|
| Vision accuracy below gate on low-end devices | Core loop untrustworthy | Cloud keypoint fallback; rollback rule (stop, diagnose, don't paper over with copy) |
| Health-data legal sign-off delayed | Personalisation depth blocked | Ship loop without health collection; feature-flag health onboarding behind sign-off |
| Model-assisted layer produces confident-but-wrong scores | Erodes trust / safety | Advisory-only; deterministic veto; expert-agreement gate before default-on |
| Personalisation feels like a checkbox, not real | Retention upside unrealised | Test "feels personalised" explicitly in P1 beta (PRD_v2 §12 Q5) |
| Notification tuning wrong (too early/late) | Habit loop weak or annoying | Configurable streak-at-risk timing; ≤ 1/day cap; beta-tune |
| Premium conversion unproven | Revenue path unclear | Value-first paywall placement; measure from first cohort |

**Key dependencies:** Exercise Library seeded before agent work; Supabase + RLS before any user data;
Legal sign-off before production health collection; Phase-2 eval gates before Phase-3 engagement build.

---

## 11. Open Business Questions (PRD_v2 is a Baseline)

PRD_v2's MVP scope and phase gates are explicitly open to revision. Decisions needed:

1. **Streak freeze** — premium-only or earnable by all? (Earnable aligns with the positive-reinforcement
   principle.)
2. **Health-context liability** — confirm disclaimer + ToS scope with Legal before any collection.
3. **Leaderboard anonymisation** — confirm anonymous-by-default satisfies DPDP.
4. **D7 gate failure path** — if D7 > 40% is not met by Phase 2 completion, delay Phase 3 or re-examine
   the core loop?
5. **MVP personalisation depth** — is contraindication-callout + default sets/reps enough to *feel*
   personalised, or does it read as a checkbox? Test in P1 beta.
6. **Model-assisted vision scope (v2-specific)** — how much of the form-scoring nuance moves to the
   model layer vs. stays determini