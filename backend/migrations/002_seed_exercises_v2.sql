-- Migration: 002_seed_exercises_v2.sql
-- Description: Seed the 3 MVP exercises and the badge catalog.
--              Full reference_keypoints / coaching_cues / contraindications / model_assist
--              are loaded from exercises/*.json at application boot; this seed inserts the
--              base rows so foreign keys resolve before the boot loader runs.
-- Applied: [pending]

-- ── Exercises (minimal rows; JSON blobs hydrated on boot) ──
INSERT INTO exercises (id, name, target_muscles, difficulty, equipment, estimated_duration_seconds, is_premium)
VALUES
  ('squat',  'Bodyweight Squat', ARRAY['quads','glutes','hamstrings'],                 'beginner', ARRAY[]::text[], 120, false),
  ('pushup', 'Push-Up',          ARRAY['chest','triceps','anterior_deltoid','core'],   'beginner', ARRAY[]::text[], 120, false),
  ('lunge',  'Forward Lunge',    ARRAY['quads','glutes','hamstrings','hip_flexors'],    'beginner', ARRAY[]::text[], 150, false)
ON CONFLICT (id) DO NOTHING;

-- ── Badge catalog (PRD_v2 §9.3; awards happen in Phase 3) ──
INSERT INTO badge_catalog (id, name, description, cohort_affinity) VALUES
  ('first_rep',     'First Rep',     'Complete your first session.',                          'both'),
  ('consistent',    'Consistent',    'Reach a 7-day streak.',                                  'habit_formation'),
  ('form_focus',    'Form Focus',    'Form score above 9.0 on any session.',                  'assisted_training'),
  ('clean_week',    'Clean Week',    '5 sessions in 7 days, averaging under 2 form flags.',    'both'),
  ('century',       'Century',       '100 total reps, cumulative across any exercise.',        'habit_formation'),
  ('depth_charge',  'Depth Charge',  '50 squats with form score above 8.0.',                  'assisted_training'),
  ('comeback',      'Comeback',      'Log a session after a 7+ day lapse.',                    'both'),
  ('streak_shield', 'Streak Shield', 'Use a streak freeze and resume the next day.',           'habit_formation'),
  ('monthly',       'Monthly',       '20 sessions in a calendar month.',                       'both'),
  ('quarterly',     'Quarterly',     '60 sessions in 90 days.',                                'both')
ON CONFLICT (id) DO NOTHING;
