-- Migration: 001_initial_schema_v2.sql
-- Description: Kinetiq v2 initial schema. Full PRD_v2 data model provisioned now;
--              behaviour ships by phase (ADR-105). pgvector + memory tables present
--              from day one (ADR-103). Health context is sensitive + RLS-scoped (ADR-106).
-- Conventions: RLS enabled on every user-owned table, policies defined inline.
--              Migrations are append-only — never edit after apply; add a new migration.
-- Applied: [pending]

-- =============================================
-- EXTENSIONS
-- =============================================
CREATE EXTENSION IF NOT EXISTS "pgcrypto";   -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS "vector";     -- pgvector, Memory Agent (Phase 2)

-- =============================================
-- ENUM TYPES  (named, reusable, validated at the DB boundary)
-- =============================================
CREATE TYPE fitness_level   AS ENUM ('beginner', 'intermediate', 'advanced');
CREATE TYPE record_type      AS ENUM ('form_score', 'reps_per_set', 'total_reps_session');
CREATE TYPE score_source     AS ENUM ('deterministic', 'model_assisted');
CREATE TYPE challenge_status AS ENUM ('active', 'completed', 'expired', 'dismissed');
CREATE TYPE pair_status      AS ENUM ('pending', 'active', 'declined', 'ended');

-- =============================================
-- USERS  (v1 fields + PRD_v2 §8 personalisation, collected at onboarding)
-- =============================================
CREATE TABLE users (
  id                               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email                            text UNIQUE NOT NULL,
  display_name                     text,
  fitness_level                    fitness_level,
  goals                            text[] NOT NULL DEFAULT '{}',  -- weight_loss|strength|consistency
  -- ── PRD_v2 §8 personalisation (collected MVP, used MVP+P2) ──
  health_context                   text[] NOT NULL DEFAULT '{}',  -- knee_injury|back_injury|shoulder_injury|hypertension|diabetes|none
  equipment_available              text[] NOT NULL DEFAULT '{}',  -- none|dumbbells|resistance_bands|pull_up_bar|barbell
  preferred_session_time           time,
  preferred_session_duration_minutes int NOT NULL DEFAULT 15 CHECK (preferred_session_duration_minutes BETWEEN 5 AND 120),
  -- ── consent + lifecycle ──
  health_consent_granted_at        timestamptz,                   -- ADR-106: null until explicit consent
  onboarding_completed_at          timestamptz,
  last_active_at                   timestamptz,
  created_at                       timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE users ENABLE ROW LEVEL SECURITY;
CREATE POLICY users_select_own ON users FOR SELECT USING (auth.uid() = id);
CREATE POLICY users_update_own ON users FOR UPDATE USING (auth.uid() = id);

-- =============================================
-- EXERCISES  (v1 + PRD_v2 §8.4 contraindications + v2 model_assist block)
-- =============================================
CREATE TABLE exercises (
  id                    text PRIMARY KEY,                 -- 'squat','pushup','lunge'
  name                  text NOT NULL,
  demo_video_url        text,
  target_muscles        text[] NOT NULL DEFAULT '{}',
  difficulty            fitness_level NOT NULL,
  equipment             text[] NOT NULL DEFAULT '{}',
  estimated_duration_seconds int,
  is_premium            boolean NOT NULL DEFAULT false,   -- free tier: 3 exercises (PRD_v2 §10)
  reference_keypoints   jsonb NOT NULL DEFAULT '{}',      -- correct pose + per-error keypoint signatures + named thresholds
  coaching_cues         jsonb NOT NULL DEFAULT '{}',      -- setup/execution/per-flag/good_rep/set_complete_*
  contraindications     jsonb NOT NULL DEFAULT '{}',      -- PRD_v2 §8.4 per health-condition modifications
  rep_counting          jsonb NOT NULL DEFAULT '{}',      -- phase machine definition
  model_assist          jsonb NOT NULL DEFAULT '{}',      -- ADR-100: feature window + derived features (inert until P2)
  created_at            timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE exercises ENABLE ROW LEVEL SECURITY;
CREATE POLICY exercises_public_read ON exercises FOR SELECT USING (true);

-- =============================================
-- SESSIONS  (v1 + delta-vs-last support via index on (user,exercise,time))
-- =============================================
CREATE TABLE sessions (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id          uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  exercise_id      text NOT NULL REFERENCES exercises(id),
  sets_target      int,
  reps_per_set_target int,
  sets_completed   int NOT NULL DEFAULT 0 CHECK (sets_completed >= 0),
  total_reps       int NOT NULL DEFAULT 0 CHECK (total_reps >= 0),
  avg_form_score   float CHECK (avg_form_score BETWEEN 0 AND 10),
  form_flags       jsonb NOT NULL DEFAULT '{}',           -- {"knee_cave_left":5,"shallow_depth":2}
  score_source     score_source NOT NULL DEFAULT 'deterministic',
  duration_seconds int CHECK (duration_seconds >= 0),
  trace_id         uuid,
  started_at       timestamptz NOT NULL DEFAULT now(),
  completed_at     timestamptz
);

ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;
CREATE POLICY sessions_select_own ON sessions FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY sessions_insert_own ON sessions FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE INDEX sessions_user_id_idx       ON sessions (user_id);
CREATE INDEX sessions_completed_at_idx  ON sessions (completed_at DESC);
-- Powers form_score_delta_vs_last (BR-6): last session on same exercise.
CREATE INDEX sessions_user_ex_time_idx  ON sessions (user_id, exercise_id, completed_at DESC);

-- =============================================
-- REP_METRICS  (v2: per-rep granularity — feeds adaptive difficulty, model-assist eval, analytics)
-- One row per completed rep. Keypoint-derived features only (ADR-101).
-- =============================================
CREATE TABLE rep_metrics (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id        uuid NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  user_id           uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  set_number        int NOT NULL,
  rep_number        int NOT NULL,
  form_score        float CHECK (form_score BETWEEN 0 AND 10),
  score_source      score_source NOT NULL DEFAULT 'deterministic',
  confidence        float CHECK (confidence BETWEEN 0 AND 1),
  form_flags        text[] NOT NULL DEFAULT '{}',
  derived_features  jsonb NOT NULL DEFAULT '{}',           -- joint angles, tempo, symmetry, ROM
  created_at        timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE rep_metrics ENABLE ROW LEVEL SECURITY;
CREATE POLICY rep_metrics_select_own ON rep_metrics FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY rep_metrics_insert_own ON rep_metrics FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE INDEX rep_metrics_session_idx ON rep_metrics (session_id);

-- =============================================
-- STREAKS  (v1 + streak-freeze support, PRD_v2 §9.2)
-- =============================================
CREATE TABLE streaks (
  user_id            uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  current_streak     int NOT NULL DEFAULT 0,
  longest_streak     int NOT NULL DEFAULT 0,
  last_session_date  date,
  freezes_available  int NOT NULL DEFAULT 0,   -- earned after 7-day streak (Phase 3)
  freeze_last_earned date,
  updated_at         timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE streaks ENABLE ROW LEVEL SECURITY;
CREATE POLICY streaks_select_own ON streaks FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY streaks_update_own ON streaks FOR UPDATE USING (auth.uid() = user_id);

-- =============================================
-- PERSONAL_RECORDS  (PRD_v2 §9.2 — MVP gamification)
-- =============================================
CREATE TABLE personal_records (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  exercise_id  text NOT NULL REFERENCES exercises(id),
  record_type  record_type NOT NULL,
  value        float NOT NULL,
  achieved_at  timestamptz NOT NULL DEFAULT now(),
  session_id   uuid REFERENCES sessions(id) ON DELETE SET NULL,
  UNIQUE (user_id, exercise_id, record_type)   -- one current record per type; updated on new best
);

ALTER TABLE personal_records ENABLE ROW LEVEL SECURITY;
CREATE POLICY pr_select_own ON personal_records FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY pr_insert_own ON personal_records FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY pr_update_own ON personal_records FOR UPDATE USING (auth.uid() = user_id);

-- =============================================
-- BADGES  (PRD_v2 §9.3 — Phase 3; catalog + per-user awards)
-- =============================================
CREATE TABLE badge_catalog (
  id              text PRIMARY KEY,            -- 'first_rep','consistent','form_focus',...
  name            text NOT NULL,
  description     text NOT NULL,
  trigger_spec    jsonb NOT NULL DEFAULT '{}', -- machine-checkable trigger definition
  cohort_affinity text NOT NULL DEFAULT 'both' -- habit_formation|assisted_training|both
);
ALTER TABLE badge_catalog ENABLE ROW LEVEL SECURITY;
CREATE POLICY badge_catalog_public_read ON badge_catalog FOR SELECT USING (true);

CREATE TABLE user_badges (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id    uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  badge_id   text NOT NULL REFERENCES badge_catalog(id),
  earned_at  timestamptz NOT NULL DEFAULT now(),
  session_id uuid REFERENCES sessions(id) ON DELETE SET NULL,
  UNIQUE (user_id, badge_id)                    -- awarded once, permanently
);
ALTER TABLE user_badges ENABLE ROW LEVEL SECURITY;
CREATE POLICY user_badges_select_own ON user_badges FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY user_badges_insert_own ON user_badges FOR INSERT WITH CHECK (auth.uid() = user_id);

-- =============================================
-- WORKOUT_PLANS  (Planner Agent, Phase 2 — schema-ready now, ADR-105)
-- =============================================
CREATE TABLE workout_plans (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  week_of     date NOT NULL,
  plan        jsonb NOT NULL DEFAULT '{}',     -- generated schedule: day -> [exercise, sets, reps]
  generated_by text,                            -- model name @ generation time
  created_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, week_of)
);
ALTER TABLE workout_plans ENABLE ROW LEVEL SECURITY;
CREATE POLICY plans_select_own ON workout_plans FOR SELECT USING (auth.uid() = user_id);

-- =============================================
-- CHALLENGES  (PRD_v2 §9.3 weekly challenges — Phase 3)
-- =============================================
CREATE TABLE challenges (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  week_of      date NOT NULL,
  text         text NOT NULL,
  target_spec  jsonb NOT NULL DEFAULT '{}',     -- machine-checkable completion criteria
  status       challenge_status NOT NULL DEFAULT 'active',
  reward_badge_id text REFERENCES badge_catalog(id),
  created_at   timestamptz NOT NULL DEFAULT now(),
  resolved_at  timestamptz
);
ALTER TABLE challenges ENABLE ROW LEVEL SECURITY;
CREATE POLICY challenges_select_own ON challenges FOR SELECT USING (auth.uid() = user_id);

-- =============================================
-- WEEKLY_SUMMARIES  (PRD_v2 §9.3 — Phase 3, strong-model narrative, pre-generated)
-- =============================================
CREATE TABLE weekly_summaries (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id             uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  week_of             date NOT NULL,
  narrative           text NOT NULL,
  sessions_this_week  int NOT NULL DEFAULT 0,
  sessions_prev_week  int NOT NULL DEFAULT 0,
  best_form_score     jsonb,                      -- {"exercise_id","value"}
  top_flag            jsonb,                      -- {"flag","count"}
  generated_by        text,
  created_at          timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, week_of)
);
ALTER TABLE weekly_summaries ENABLE ROW LEVEL SECURITY;
CREATE POLICY weekly_summaries_select_own ON weekly_summaries FOR SELECT USING (auth.uid() = user_id);

-- =============================================
-- ACCOUNTABILITY_PAIRS  (PRD_v2 §9.4 — Phase 3, opt-in; share streak + last-session only)
-- =============================================
CREATE TABLE accountability_pairs (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  inviter_id    uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  invitee_id    uuid REFERENCES users(id) ON DELETE CASCADE,
  invite_email  text,
  status        pair_status NOT NULL DEFAULT 'pending',
  created_at    timestamptz NOT NULL DEFAULT now(),
  CHECK (inviter_id <> invitee_id)
);
ALTER TABLE accountability_pairs ENABLE ROW LEVEL SECURITY;
CREATE POLICY pairs_select_member ON accountability_pairs FOR SELECT
  USING (auth.uid() = inviter_id OR auth.uid() = invitee_id);

-- =============================================
-- FORM_TRENDS  (Memory Agent, Phase 2 — pgvector; per-user, per-exercise embeddings, ADR-103)
-- =============================================
CREATE TABLE form_trends (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  exercise_id   text NOT NULL REFERENCES exercises(id),
  window_start  date NOT NULL,
  window_end    date NOT NULL,
  flag_counts   jsonb NOT NULL DEFAULT '{}',     -- aggregated flags over the window
  avg_form_score float,
  summary_text  text,                             -- short narrative for the Coaching Agent
  embedding     vector(1536),                     -- semantic recall (model-dim configurable)
  created_at    timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE form_trends ENABLE ROW LEVEL SECURITY;
CREATE POLICY form_trends_select_own ON form_trends FOR SELECT USING (auth.uid() = user_id);
CREATE INDEX form_trends_user_ex_idx ON form_trends (user_id, exercise_id);
-- IVFFlat index added in a later migration once data exists (needs rows to train).

-- =============================================
-- NOTES
-- =============================================
-- Service-role writes (Progress/Memory/Engagement agents) bypass RLS and run server-side only.
-- Health-context columns are gated at the application layer (ADR-106): writes rejected until
-- health_consent_granted_at is set AND the legal-gate flag is enabled.
-- Reference keypoints + coaching cues + contraindications are seeded from exercises/*.json on boot
-- (see 002_seed_exercises_v2.sql).
