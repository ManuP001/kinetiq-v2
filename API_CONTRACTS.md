# API_CONTRACTS.md — Kinetiq v2 (TypeScript ↔ Python)

> All contracts between the React Native app and the FastAPI backend.
> Canonical schema source: `backend/app/core/schemas.py` (Pydantic v2).
> Generated TypeScript types: `apps/mobile/src/types/generated.ts`.
> Namespace: `/v2/` (v1 `/v1/` contracts are untouched — see ADR-107).
> Last updated: 2026-07-06

---

## General Conventions

- Base URL (dev): `http://localhost:8000/v2`
- Base URL (prod): `https://api.kinetiq.app/v2`
- `Content-Type: application/json`; authenticated requests carry `Authorization: Bearer {supabase_jwt}`.
- Error envelope (never HTTP 200 with an error body):
  ```json
  { "error": "Human-readable message", "code": "ERROR_CODE", "trace_id": "uuid" }
  ```
- Timestamps: ISO-8601 strings across the boundary.
- **Privacy invariant:** request bodies carry keypoints and derived features only — never image/video.

---

## Endpoints

### POST /v2/sessions
Start a session.

**Request**
```json
{ "exercise_id": "squat", "sets_target": 3, "reps_per_set_target": 10 }
```
**Response 201**
```json
{ "session_id": "uuid", "exercise_id": "squat", "started_at": "ISO-8601",
  "applied_personalisation": { "default_sets": 3, "default_reps": 10,
    "health_modifiers": ["knee_injury"] },
  "trace_id": "uuid" }
```
`applied_personalisation` reflects fitness-level defaults and any health-context modifiers resolved at
session start. **Error codes:** `EXERCISE_NOT_FOUND`, `AUTH_REQUIRED`, `EXERCISE_CONTRAINDICATED`.

---

### POST /v2/sessions/{session_id}/assess
**Batched, non-blocking metrics upload (ADR-109).** The device is authoritative for rep count, safety
flags, and base form score — all computed on-device with zero network. The app calls this endpoint at
**set boundaries** (or session end / next connectivity) with the batch of per-rep keypoint-derived
metrics. The server persists `rep_metrics`, may return a warm-path set-summary cue, and echoes the
server-side view of the assessment for reconciliation. The client **never blocks a rep on this call**
and skips it gracefully offline. The advisory model layer (Phase 2) does not run on this path.

**Request**
```json
{
  "frame_keypoints": [
    { "landmark_index": 0, "x": 0.5, "y": 0.3, "z": -0.1, "visibility": 0.98 }
  ],
  "derived_features": { "left_knee_angle": 92.0, "right_knee_angle": 95.0,
    "torso_lean_deg": 22.0, "tempo_ms": 1800 },
  "timestamp_ms": 12450,
  "rep_completed": false, "set_completed": false,
  "current_rep": 4, "current_set": 2
}
```
`derived_features` is optional and advisory-only; rep count and safety flags are computed from
keypoints regardless.

**Response 200**
```json
{
  "rep_count": 4, "rep_in_progress": true, "confidence": 0.87,
  "form_flags": ["knee_cave_left"], "form_score": 7.5, "score_source": "deterministic",
  "phase": "descending",
  "coaching_cue": { "cue_text": "Good depth — push your left knee out on the way up",
    "cue_type": "form_correction", "confidence_level": "directive" },
  "trace_id": "uuid"
}
```
`score_source` is `"deterministic"` on the hot path; becomes `"model_assisted"` only after an async
refinement (fetched via the session record, never inline). Notes from v1 carry over: `coaching_cue` is
`null` when none should fire; `confidence < 0.7` for 3 consecutive frames →
`form_flags=["low_confidence"]` + camera-guidance cue. **Error codes:** `SESSION_NOT_FOUND`,
`INVALID_KEYPOINTS`, `SESSION_ALREADY_COMPLETE`.

---

### POST /v2/sessions/{session_id}/complete
Finalise. Triggers Progress Agent (sync) and, in Phase 2+, Memory/Engagement agents (async).

**Request**
```json
{ "sets_completed": 3, "total_reps": 27, "duration_seconds": 420 }
```
**Response 200**
```json
{
  "session_id": "uuid", "avg_form_score": 7.1,
  "form_flags": { "knee_cave_left": 5, "shallow_depth": 2 },
  "streak_day": 4, "streak_updated": true,
  "personal_records": [ { "record_type": "form_score", "exercise_id": "squat", "value": 7.1,
    "is_new": true } ],
  "form_score_delta_vs_last": 0.6,
  "completed_at": "ISO-8601", "trace_id": "uuid"
}
```
`form_score_delta_vs_last` powers the Day-1→Day-2 return moment (BR-6). `personal_records` lists any PR
newly set this session. **Error codes:** `SESSION_NOT_FOUND`, `SESSION_ALREADY_COMPLETE`,
`DB_WRITE_FAILED`.

---

### GET /v2/exercises
List the library. **Response 200**
```json
{ "exercises": [ { "id": "squat", "name": "Bodyweight Squat",
  "target_muscles": ["quads","glutes","hamstrings"], "difficulty": "beginner",
  "equipment": [], "demo_video_url": "https://..." } ] }
```

---

### GET /v2/exercises/{exercise_id}
Full detail including coaching cues and contraindications (resolved against the caller's health context
when authenticated). **Response 200**
```json
{
  "id": "squat", "name": "Bodyweight Squat",
  "target_muscles": ["quads","glutes","hamstrings"], "difficulty": "beginner",
  "equipment": [], "demo_video_url": "https://...",
  "estimated_duration_seconds": 120,
  "coaching_cues": { "setup": "Stand hip-width apart, toes slightly out",
    "knee_cave_left": "Push your left knee out", "shallow_depth": "Sit a little deeper",
    "good_rep": "Good depth — keep it up" },
  "active_contraindications": [
    { "condition": "knee_injury", "flag": true,
      "modification": "Reduce depth. Stop where you feel knee discomfort. Consider a box squat.",
      "show_on": ["exercise_detail","live_session_start"] } ]
}
```
`active_contraindications` is filtered to the caller's `health_context`; empty/omitted when anonymous.
**Error codes:** `EXERCISE_NOT_FOUND`.

---

### PATCH /v2/users/me/profile
Persist onboarding/personalisation data. **Health fields rejected unless the server-side legal-gate flag
is enabled (ADR-106).**

**Request**
```json
{ "fitness_level": "beginner", "goals": ["strength","consistency"],
  "health_context": ["knee_injury"], "equipment_available": ["dumbbells"],
  "preferred_session_time": "19:00", "preferred_session_duration_minutes": 15 }
```
**Response 200** — echoes the stored profile. **Error codes:** `AUTH_REQUIRED`,
`HEALTH_COLLECTION_DISABLED`, `INVALID_ENUM_VALUE`.

---

### GET /v2/users/me/home  (Phase 1)
Home-screen payload: streak, today's status, PR highlights, personalised welcome.
```json
{ "current_streak": 5, "longest_streak": 11, "week_dots": [true,true,false,true,true,false,false],
  "completed_today": false, "welcome_message": "Let's stay consistent, Manu.",
  "recent_prs": [ { "exercise_id": "squat", "record_type": "form_score", "value": 8.3 } ] }
```

---

### GET /v2/users/me/weekly-summary  (Phase 3, async-generated)
Strong-model narrative recap. Returns the most recent stored summary; never generated inline.
```json
{ "week_of": "2026-06-15", "narrative": "4 sessions last week — your best week yet...",
  "sessions_this_week": 4, "sessions_prev_week": 2,
  "best_form_score": { "exercise_id": "squat", "value": 8.3 },
  "top_flag": { "flag": "knee_cave_left", "count": 6 }, "streak_day": 11,
  "challenge": { "id": "uuid", "text": "10 clean squats before Sunday" } }
```

---

## TypeScript Types (generated from Pydantic)

Location: `apps/mobile/src/types/generated.ts`

```typescript
// DO NOT EDIT — generated from backend/app/core/schemas.py

export interface KeyPoint {
  landmarkIndex: number; x: number; y: number; z: number; visibility: number;
}

export interface DerivedFeatures {
  leftKneeAngle?: number; rightKneeAngle?: number; torsoLeanDeg?: number;
  leftElbowAngle?: number; rightElbowAngle?: number; tempoMs?: number; symmetry?: number;
}

export interface CoachingCue {
  cueText: string;
  cueType: "form_correction" | "encouragement" | "set_summary" | "safety_warning" | "camera_guidance";
  confidenceLevel: "directive" | "suggestion";
}

export interface FormAssessment {
  repCount: number; repInProgress: boolean; confidence: number;
  formFlags: string[]; formScore: number;
  scoreSource: "deterministic" | "model_assisted";
  phase: "ascending" | "descending" | "bottom" | "top" | "standing" | "unknown";
  coachingCue: CoachingCue | null; traceId: string;
}

export interface PersonalRecord {
  recordType: "form_score" | "reps_per_set" | "total_reps_session";
  exerciseId: string; value: number; isNew: boolean;
}

export interface SessionResult {
  sessionId: string; avgFormScore: number; formFlags: Record<string, number>;
  streakDay: number; streakUpdated: boolean;
  personalRecords: PersonalRecord[]; formScoreDeltaVsLast: number | null;
  completedAt: string; traceId: string;
}

export interface Contraindication {
  condition: string; flag: boolean; modification: string; showOn: string[];
}

export interface Exercise {
  id: string; name: string; targetMuscles: string[];
  difficulty: "beginner" | "intermediate" | "advan