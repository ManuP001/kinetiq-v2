# PRD v2 — Virtual Physical Trainer (Kinetiq)

> Supersedes PRD.md.
> Changes from v1: Added Section 7 (Habit Loop), Section 8 (User Health Context & Personalisation Schema), Section 9 (Gamification Roadmap). Sections 1–6 carry forward from PRD.md with minor updates.
> Last updated: 2026-06-09

---

## 1. Problem

Home and gym workouts lack real-time feedback. Users either train with incorrect form (risking injury) or never build a consistent habit because there's no accountability or coaching loop.

The second failure mode is more common and more expensive: **most users quit before they see results.** The product cannot win on form correction alone — it must also win on habit formation.

---

## 2. Solution

An AI-powered virtual fitness trainer using only a phone camera — no hardware required — that provides real-time rep counting, form correction cues, and a habit-building system designed to keep users returning past Day 7.

---

## 3. Core Promise

"The only fitness app that gives you a live coaching experience AND a habit-building journey — using just your phone's camera."

---

## 4. Users

**Cohort 1: Habit Formation** — Beginners and inconsistent exercisers who need structure, streaks, and gentle accountability. India Tier 1 cities. English-first. Age 22–38.

**Cohort 2: Assisted Training** — Active users and gym-goers who want precision form correction and adaptive programming. Same demographic, higher fitness literacy.

Both cohorts are served by the same free-tier MVP. No separate UX tracks until post-MVP D7 retention data justifies the split.

---

## 5. MVP Scope

Governed by CLAUDE-VPT-MVP.md. Summary:
- 3 exercises (squat, push-up, lunge)
- Real-time rep counting via MediaPipe (on-device)
- Basic form detection (knee cave, shallow depth, elbow flare)
- Session summary with form score
- Streak mechanic
- Free tier only

---

## 6. Success Metrics

**Phase 1 (MVP):**
- Rep counting accuracy > 90%
- Form flag accuracy > 80%
- Session completion rate > 70%
- D3 return rate > 50%

**Phase 2 (Intelligence):**
- Coaching cue quality > 4/5 on LLM-as-Judge
- Hallucination rate < 2%

**Phase 3 (Engagement):**
- D7 retention > 40% for habit cohort
- D14 retention > 25%
- D30 retention > 15%

---

## 7. Habit Loop Design

This section is new. It governs every UX and product decision that affects whether users return.

### 7.1 The Loop

Kinetiq's habit loop follows the cue → routine → reward structure, with a feedback mechanism that strengthens the loop over time.

```
CUE ──────────────────────► ROUTINE ──────────────────► REWARD
(trigger to open app)        (the session)               (what they get)
        ▲                                                      │
        └──────────────── REINFORCEMENT ◄──────────────────────┘
                          (makes cue stronger)
```

**Cue (what brings them back):**
- Streak at risk: "Your 5-day streak resets in 4 hours" — the most powerful cue in MVP
- Scheduled time: user sets a preferred workout time in onboarding; notification fires at that time (Phase 3)
- Environmental: home screen widget showing streak + today's exercise (Phase 3)
- Social: accountability partner trained today (Phase 3)

In MVP, the streak-at-risk notification is the only cue mechanism. It must be implemented correctly — too early (24 hours before) feels low-stakes; too late (1 hour before) feels anxious. Default: fires at 7pm if no session logged, configurable. **Note (ADR-108):** this requires FCM/APNs in Phase 1, scoped to this single daily push only; the full notification/re-engagement suite remains Phase 3.

**Routine (the session):**
- Must be completable in under 15 minutes for Habit Formation cohort — this is a hard constraint
- Progressive overload must be visible within 2 weeks — users need to feel the routine is doing something
- The first 3 sessions are the most fragile — onboarding difficulty must be calibrated low enough that no user quits in sessions 1–3

**Reward (what they get that makes them want to return):**

| Reward Type | When Delivered | MVP? |
|---|---|---|
| Streak increment (progress reward) | End of every session | ✅ MVP |
| Form score improvement callout | When form score improves vs last session on same exercise | ✅ MVP |
| Personal record (PR) flag | First time a rep target is hit cleanly | ✅ MVP |
| Session completion confirmation | Always — the summary screen is itself a reward | ✅ MVP |
| Weekly progress summary | Every Monday — last 7 days at a glance | Phase 3 |
| Milestone badges | Day 7, Day 14, Day 30 streaks; first clean set; first 100 reps | Phase 3 |
| Leaderboard position | Weekly form score ranking (opt-in) | Phase 3 |
| Accountability pair nudge | "Your partner just completed their session" | Phase 3 |

**Reinforcement (what strengthens the cue over time):**
- Streak visibility on home screen — the number itself becomes motivating as it grows
- Weekly recap delivered on Monday showing last week's sessions, form trend, streak progress
- The app should never let a D3 lapse happen silently — a user who misses Day 3 gets a personalised re-engagement message, not a generic "we miss you" push

### 7.2 Critical Retention Windows

Based on fitness app benchmarks, three windows determine long-term retention:

**Day 1 → Day 3:** The first return. User must experience a meaningful improvement or recognition between sessions 1 and 2. In MVP this is: form score comparison between session 1 and 2 on the same exercise. If form improved, say so specifically. If not, say what to focus on.

**Day 7:** The streak threshold. Users who reach a 7-day streak are significantly more likely to reach Day 30. The Day 7 moment must be treated as a milestone — not just a streak number, a celebrated product moment. Design this explicitly (see Gamification section).

**Day 14 → Day 30:** Habit formation. At this point the user should have a clear sense of progression — stronger, better form, consistent schedule. The Memory Agent (Phase 2) is the mechanism for delivering this. Without it, the app cannot sustain retention past Day 14.

### 7.3 Re-engagement Logic

Users who lapse must receive a differentiated response based on streak length lost:

| Lapse after | Message tone | Action |
|---|---|---|
| 1–2 day streak | Low urgency — "No streak lost. Start fresh today." | Single soft notification |
| 3–6 day streak | Mild urgency — "You were on a 5-day streak. Pick up where you left off." | Notification + home screen prompt |
| 7+ day streak | High urgency — specific acknowledgment of what they built | Personalised message surfacing their best session data |
| 14+ day streak | Treat as a relationship, not a metric — "You'd built something real. One missed day doesn't erase that." | Premium re-engagement flow (Phase 2) |

Re-engagement messages must never: guilt-trip, use streak loss as punishment framing, or feel automated and generic. Every message must reference something specific — their last exercise, their form score, their actual streak number.

### 7.4 Positive Reinforcement Rule (non-negotiable)

Every form assessment — in the live session, in the session summary, in any coaching cue — must surface a positive signal before a correction. This is not optional and not just UX polish. Users who feel competent return. Users who feel criticised quit.

Implementation rule: The Coaching Agent prompt must enforce: "Before flagging a form issue, acknowledge what is correct in the current rep. Lead with positive. Correction follows."

Example — WRONG: "Knee cave detected on left side. Fix this."
Example — RIGHT: "Good depth on that rep. Left knee drifted in slightly — push it out on the way up."

---

## 8. User Health Context & Personalisation Schema

This section is new. It governs data collection, storage, and use for personalisation.

### 8.1 The Personalisation Gap in v1

The v1 BRD collected `goals` and `fitness_level` in onboarding, then said "these are used post-MVP by the Planner Agent." This creates a problem: the data needed to personalise never gets collected because it's deferred.

**The rule going forward: collect all personalisation-relevant data in MVP onboarding, even if it is only used in Phase 2+. The cost of adding an onboarding field is low. The cost of not having the data when you need it is a re-onboarding flow that kills retention.**

### 8.2 Revised Onboarding — Data Collection

The revised onboarding collects data across 4 screens (up from 3). Screen 4 is the health context screen.

**Screen 1:** Training goal (unchanged — Build Strength / Stay Consistent / Lose Weight)

**Screen 2:** Training frequency (unchanged — Beginner / Regular / Serious)

**Screen 3:** Health context + equipment + preferred time/duration (NEW — canonical composition per ADR-110; the "or as a standalone screen" ambiguity is resolved: everything below lives on Screen 3)
- "Do you have any of the following? (Select all that apply)"
  - Knee pain or prior knee injury
  - Lower back pain or prior back injury
  - Shoulder pain or prior shoulder injury
  - High blood pressure / hypertension
  - Type 2 diabetes
  - None of the above

This is not a medical form. It is a coaching modifier. Users must be told exactly this on screen:
"This helps us calibrate coaching cues and flag exercises that need modification. We are not a medical service — if you have a diagnosed condition, always check with your doctor before starting any exercise programme."

Store as `users.health_context: text[]`.

Screen 3 additionally collects (ADR-110):
- Equipment available (none / dumbbells / resistance bands / pull-up bar / barbell) → `users.equipment_available`
- Preferred workout time → `users.preferred_session_time`
- Preferred session duration (10/15/20/30 min) → `users.preferred_session_duration_minutes`

**Screen 4:** Auth (unchanged — Google / email)

### 8.3 User Health Context Schema

```sql
-- Add to existing users table
ALTER TABLE users ADD COLUMN health_context text[] DEFAULT '{}';
-- Values: 'knee_injury', 'back_injury', 'shoulder_injury', 
--          'hypertension', 'diabetes', 'none'

ALTER TABLE users ADD COLUMN equipment_available text[] DEFAULT '{}';
-- Values: 'none', 'dumbbells', 'resistance_bands', 'pull_up_bar', 'barbell'
-- Collected on onboarding Screen 3 (ADR-110)

ALTER TABLE users ADD COLUMN preferred_session_time time;
-- Collected on onboarding Screen 3 (ADR-110)
-- Used by notification system in Phase 3

ALTER TABLE users ADD COLUMN preferred_session_duration_minutes int DEFAULT 15;
-- 10 / 15 / 20 / 30 — user-declared, used by Planner Agent

ALTER TABLE users ADD COLUMN onboarding_completed_at timestamptz;
ALTER TABLE users ADD COLUMN last_active_at timestamptz;
```

### 8.4 How Health Context Affects MVP Behaviour

Even in MVP, with no Planner Agent, health context must affect the product in two places:

**1. Exercise contraindication flags**

Each exercise in the Exercise Library gains a `contraindications` field:

```json
{
  "exercise_id": "squat",
  "contraindications": {
    "knee_injury": {
      "flag": true,
      "modification": "Reduce depth. Stop at the point where you feel knee discomfort. Consider a box squat.",
      "show_on": ["exercise_detail", "live_session_start"]
    },
    "back_injury": {
      "flag": true,
      "modification": "Keep torso more upright. Avoid forward lean. Stop if you feel lumbar pressure.",
      "show_on": ["exercise_detail"]
    },
    "hypertension": {
      "flag": false,
      "modification": "Avoid breath-holding (Valsalva). Breathe continuously throughout the rep.",
      "show_on": ["exercise_detail"]
    }
  }
}
```

When a user with `knee_injury` in their health_context opens a squat exercise detail, show a single-line callout: "You've noted a knee concern — see our modification below." This is not a block; it is a personalised heads-up.

**2. Coaching Agent modifier in MVP**

The coaching_agent_mvp.md prompt must include health context as a system-level modifier:

```
User health context: {user.health_context}
If health context includes knee_injury: soften knee cave corrections to suggestions only.
  WRONG: "Push your left knee out."
  RIGHT: "Try tracking your knee over your toe — only as far as feels comfortable."
If health context includes hypertension: add breath cue to every set completion message.
  Add: "Breathe out on the way up."
```

### 8.5 Personalisation Roadmap

What personalisation looks like at each phase:

**MVP (Phase 1):**
- Health context modifies exercise detail callouts
- Health context modifies coaching cue tone (softer for injury flags)
- Fitness level adjusts default sets/reps on Exercise Detail screen
  - Beginner: default 2 sets × 8 reps
  - Intermediate: default 3 sets × 10 reps
  - Advanced: default 4 sets × 12 reps
- Goal adjusts welcome message on Home screen only

**Phase 2 (Intelligence):**
- Planner Agent generates personalised weekly workout plans using goals + fitness_level + health_context + session history
- Memory Agent tracks per-exercise form trends; Coaching Agent references these ("Your left knee cave has improved — you've flagged it 3 fewer times this week")
- Adaptive difficulty: if form score > 8.5 for 2 sessions on same exercise, Planner Agent increases rep target

**Phase 3 (Engagement):**
- Personalised rest day recommendations based on session frequency + declared health context
- Re-engagement messages reference user-specific data (last exercise, last form score, streak peak)
- Optional: integration with health data (Apple Health / Google Fit step count, sleep data) for recovery context

**Phase 4 (Agentic):**
- Proactive plan adjustments — "You've done 4 squat sessions this week. Today should be push-up or rest."
- Nutrition context integration (if user opts in)
- Injury prevention flags: "You've had left knee cave in 8 of your last 10 squat sessions — we recommend this corrective drill before your next session"

---

## 9. Gamification Roadmap

This section is new. It sequences every gamification mechanic by phase with clear rationale.

### 9.1 Design Principles

**Earned, not decorative.** Every reward must be triggered by real behaviour. No badges for signing up. No streaks that count passive days. No points for opening the app.

**Intrinsic before extrinsic.** The primary reward must always be the user's own progress — improved form score, more reps, better consistency. Extrinsic rewards (badges, leaderboards, points) amplify this; they do not replace it.

**Cohort-appropriate.** The Habit Formation cohort responds to consistency rewards and social accountability. The Assisted Training cohort responds to performance records and competitive ranking. These are different psychological hooks — do not conflate them in one design.

**Never punish.** Streak loss is visible but never shamed. Leaderboards are opt-in. No "you failed your goal" language anywhere in the product.

### 9.2 Phase 1 MVP — Mechanic: Streak + PR Flags

Only two gamification mechanics in MVP. Both are deterministic — no new infrastructure required.

**Streak:**
- Definition: one completed session per calendar day (UTC+5:30 for India). Minimum 1 set to count.
- Streak resets if no session logged for > 36 hours (buffer for timezone variance and late-night sessions).
- Display: large number on Home screen, 7-dot week view, streak count on Session Summary.
- Milestone moments (Day 3, Day 7, Day 14, Day 30): distinct visual treatment on Session Summary. These are the only moments in MVP where the UI departs from normal — brief animation, specific congratulations copy. See Design Prompts for spec.
- Streak recovery mechanic (Phase 3): one "streak freeze" per month, earned after a 7-day streak.

**Personal Record (PR) flag:**
- Definition: best form score ever achieved on a given exercise, or most reps completed in a single set with form score > 7.0.
- Triggered: on Session Summary when either threshold is newly exceeded.
- Display: PR badge overlaid on the form score dial on Session Summary. Copy: "New personal best — {metric}."
- No confetti, no full-screen animation — one well-placed badge is enough.
- Stored in: `personal_records` table (see schema below).

```sql
CREATE TABLE personal_records (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid REFERENCES users(id),
  exercise_id text,
  record_type text,         -- 'form_score' | 'reps_per_set' | 'total_reps_session'
  value float,
  achieved_at timestamptz,
  session_id uuid REFERENCES sessions(id)
);
```

### 9.3 Phase 3 — Mechanic: Badges, Challenges, Weekly Summary

Add only after Phase 2 eval gate passed (coaching quality validated).

**Badge System:**

Badges are awarded once, permanently. They live on the Profile screen and are surfaced on the Session Summary when first earned.

| Badge | Trigger | Cohort affinity |
|---|---|---|
| First Rep | Complete first session | Both |
| Consistent | 7-day streak | Habit Formation |
| Form Focus | Form score > 9.0 on any session | Assisted Training |
| Clean Week | 5 sessions in 7 days, 0 form flags average < 2 per session | Both |
| Century | 100 total reps (cumulative, any exercise) | Habit Formation |
| Depth Charge | 50 squats with form score > 8.0 | Assisted Training |
| Comeback | Session logged after 7+ day lapse | Both |
| Streak Shield | Use a streak freeze and resume the next day | Habit Formation |
| Monthly | 20 sessions in a calendar month | Both |
| Quarterly | 60 sessions in 90 days | Both |

Design rule: badges are small, text-first, no emoji. They display on Profile as a grid of earned items. Unearned badges are hidden (not locked/greyed) — discovery is more satisfying than a wall of locked items.

**Weekly Challenges:**

A single challenge issued every Monday. Auto-generated by the Planner Agent based on user history. Examples:
- "10 clean squats (form score > 8) before Sunday"
- "Complete 3 sessions this week"
- "Hit a personal best on push-ups"

Challenge is optional. No penalty for not completing. Reward: a specific badge or streak bonus.
Displayed as a card on the Home screen below exercise cards. Dismissable.

**Weekly Progress Summary (Monday delivery):**

A generated narrative summary of last week. Delivered as an in-app card on Monday + optional push notification.

Content structure:
1. Sessions completed last week vs week before
2. Best form score of the week (exercise + score)
3. Most common form flag — with one tip
4. Streak status
5. This week's challenge (if Phase 3 is active)

Generated by Claude Haiku from session data. Prompt must enforce: lead with positive, max 4 sentences, no generic wellness language.

Example output:
> "4 sessions last week — your best week yet. Squat form score hit 8.3 on Thursday. Left knee alignment is still your focus area: it flagged in 6 of 12 squat reps. Keep your streak going — you're on Day 11."

### 9.4 Phase 3 — Mechanic: Social Accountability

Social features are cohort-specific. Do not build one feature that tries to serve both cohorts — they have different motivations.

**Habit Formation cohort — Accountability Pairs:**
- User can invite one person (friend, partner, colleague) as an accountability pair
- Both users see each other's streak status and last session date only — no form scores, no reps
- The emotional hook is consistency, not competition
- One nudge per day maximum: "Your partner trained today. Your move."
- Opt-in only. No social features without explicit user action.

**Assisted Training cohort — Exercise Leaderboards:**
- Weekly leaderboard by exercise — top form scores in the last 7 days
- Filtered to users who have completed 3+ sessions on that exercise (prevents gaming)
- Opt-in. Users choose which exercises to appear in the leaderboard.
- Display: rank, username (anonymisable), form score only. No rep counts, no streak data on leaderboard.
- Resets weekly on Sunday midnight.

**What NOT to build:**
- No feed, no comments, no likes — this is not a social network
- No public profile by default — everything opt-in
- No group challenges that create FOMO for non-participants

### 9.5 Phase 4 — Mechanic: Adaptive Streaks and AI Milestones

**Adaptive Streaks:**
The basic streak is binary — trained or didn't. Adaptive streaks reward quality as well as consistency.

- "Quality Streak": X consecutive sessions with form score > 7.5
- "Focus Streak": X consecutive sessions on the same exercise
- These are secondary to the main streak — supplementary, not competing

**AI-generated Milestones:**
Rather than fixed badge triggers, the Memory Agent identifies meaningful personal thresholds and surfaces them:
- "That was your 50th squat session. Your average form score has gone from 5.8 to 7.9."
- "You haven't had a left knee cave flag in 3 weeks."
- "You've trained every Monday for 8 weeks straight."

These are more meaningful than generic badges because they're specific to the user's actual history. They require the Memory Agent and session history data to exist first — hence Phase 4.

### 9.6 What Not to Build (Ever)

The following gamification patterns are explicitly excluded from Kinetiq at all phases:

- **Energy systems / lives** — no artificial limits on how many sessions a user can do
- **Pay to recover a streak** — streak recovery is earned through behaviour, never purchased
- **Comparative shame** — never show a user their rank in a way that frames them as failing
- **Notification spam** — maximum 1 push notification per day, user-controllable
- **Dark patterns** — no countdown timers on discounts, no "limited offer" streak recovery prompts
- **Unearned rewards** — no points for logging in, no badges for completing onboarding

---

## 10. Monetisation

Freemium. Free tier for both cohorts. Premium (₹X/month or annual) for Assisted Training features — personalized plans, AI coach memory, advanced analytics.

Premium features:
- Personalised weekly workout plans (Planner Agent)
- AI coach memory — coaching references your session history
- Detailed form analytics — angle data, rep-by-rep breakdown
- Unlimited exercise library (free tier: 3 exercises)
- Streak freeze mechanic (1/month)
- Priority support

Payment infrastructure: Razorpay (India domestic, UPI + cards). Stripe (international, post-MVP).

**Paywall placement rule:** The paywall should only appear after a user has experienced the core value loop at least once. Never show premium upsell before session 1 is complete. First paywall moment: post-session-1 summary, as a single low-friction callout — not a modal blocking the flow.

---

## 11. Out of Scope (All Phases Beyond Phase 4)

- Wearable device integration
- Nutrition tracking as a primary feature
- Live virtual coaching with a human trainer
- Group workout sessions (real-time multi-user sessions)
- Rehabilitation programmes (medical-grade — this is not a medical device)

---

## 12. Open Questions (To Resolve Before Phase 2 Build)

1. **Streak freeze mechanics** — Should streak freeze be a premium-only feature or earnable by all users? Earnable (after 7-day streak) feels more aligned with the positive reinforcement principle and avoids punishing free users.

2. **Health context and liability** — The contraindication flags in Section 8.4 require legal review before shipping. "We are not a medical service" must be in onboarding copy AND in Terms of Service. Get legal sign-off before collecting health_context data.

3. **Leaderboard anonymisation** — Default should be anonymous (username only, no real name). Users can opt into showing their real name. Confirm this is sufficient for DPDP Act compliance (India).

4. **D7 gate timing** — The Phase 3 engagement mechanics are gated behind D7 > 40% retention. If that gate is not passed by Phase 2 completion, do we delay Phase 3 or re-examine the core loop? Decision needed before Phase 2 scoping.

5. **Personalisation depth at launch** — Section 8.4 defines MVP personalisation (contraindication callouts, default sets/reps). Is this sufficient to feel "personalised" to users, or does it feel like a checkbox? Consider testing this in the Phase 1 beta explicitly.

---

*This document supersedes PRD.md. Update at the start of each sprint.*
*Governed by: CLAUDE-VPT-MVP.md (Phase 1), CLAUDE-VPT.md (full vision)*
*Last updated: 2026-06-09*
