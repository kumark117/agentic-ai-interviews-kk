# AI Agentic Interview Functional Spec V5.0
# Status: FROZEN ✅ — V5.0 FULLSTACK READY FOR CURSOR CODE GENERATION
# Based on: V4.8 + Final Freeze + Version Promotion to V5.0
# Repo Style: Mono-repo, all backend agents under `backend/`

---

## Changelog: V4.8 → V5.0

| # | Issue | Fix Applied |
|---|-------|-------------|
| 1 | `event_seq` missing from SSE wire format examples | Added `event_seq` to all example `data:` payloads in Section 8.4 |
| 2 | Duplicate step `3.` in SSE replay list (Section 4.4) | Renumbered correctly to steps 1–4 |
| 3 | `last_activity_at` missing from Session schema | Added to Session schema (9.1); updated on every answer submit and session creation |
| 4 | `end_reason` missing from Session schema | Added to Session schema (9.1): `candidate_completed \| max_questions_reached \| inactive_timeout \| manual` |
| 5 | Report has no `incomplete` flag for timed-out sessions | Added `is_complete: boolean` and `end_reason` to report response (8.6) |
| 6 | Frontend spec added | Section 18A: Next.js/React/TypeScript stack, components, SSE flow, FE/BE contract check |
| 7 | `EvaluationPayload` type referenced but never defined | Added full TypeScript type definition in Section 18A.3 |
| 8 | Section 17 labelled "Non-Goals for V4.7" | Corrected to V4.8 |

---

## Changelog: V4.5 → V4.6 (retained)

| # | Issue | Fix Applied |
|---|-------|-------------|
| 1 | No auth on candidate-facing endpoints | Session token issued at session creation; required on `/answers` and `/stream` |
| 2 | Redis lock TTL vs. turn budget math | Heartbeat renewal added explicitly to Orchestrator turn flow (Step 4a) |
| 3 | Answer idempotency unspecified | Idempotency rule added: duplicate `question_id` submissions rejected with 409 |
| 4 | SSE reconnection / replay missing | `Last-Event-ID` support specified; Postgres replay contract defined |
| 5 | Weakness map cap undefined | Cap set: max 2 follow-up questions per weak topic |
| 6 | `evaluation_started` event missing from turn flow | Added explicitly as Step 6 in Orchestrator turn flow |
| 7 | Confidence field under-specified | LLM prompt contract and server-side derivation rules defined |
| 8 | GET /sessions/{session_id} exposes no auth | Session token required on all session-scoped endpoints |
| 9 | Report `recommendation` field unspecified | Threshold-based rules engine defined |
| 10 | `max_questions` validation missing | Valid range: 1–20 |
| 11 | Difficulty progression unspecified | Rules defined in Interviewer Agent section |
| 12 | `interview_type` open string | Enum defined |
| 13 | Error event payload missing | Error event payload shape specified |
| 14 | Metrics endpoint rate limit missing | Rate limit: 60 req/min per API key |
| 15 | Redis lock acquisition failure unspecified | Added retry/backoff, session_busy/429 behavior, and stuck lock guidance |
| 16 | Session creation had no rate limit | Added POST /sessions rate limits and active-session prioritization |
| 17 | End session endpoint not idempotent | Calling end on an already-ended session now returns 200 OK |
| 18 | LLM semaphore behavior undefined | Added semaphore queueing, queue_delay events, and fallback rules |
| 19 | Weakness map could be polluted by LOW confidence/fallback scores | Weakness map updates only on HIGH confidence non-fallback evaluations |
| 20 | Session timeout cleanup under-specified | Added 10-minute inactivity auto-END cleanup rule |
| 21 | Event ordering guarantee under-specified | Added per-session monotonic event_seq and replay ordering rule |
| 22 | SSE token in URL risk not acknowledged | Added V1 token-hardening rules and later-phase signed URL note |

---

## 1. Problem Statement

Build a real-time AI Interviewer system that:

- Conducts autonomous, adaptive interviews
- Evaluates candidate answers with structured scoring
- Streams progress and results live to the UI
- Supports reliable operation for N = 50 concurrent users
- Is designed to scale toward N = 200 with controlled tradeoffs
- Handles duplicate submissions, stuck locks, queue pressure, and safe session cleanup explicitly
- Uses separate backend agents/processes while staying in one mono-repo

---

## 2. Architecture Summary

### Repo Decision

Use a mono-repo.

All backend logic, agents, schemas, DB access, Redis, and API routes live under:

```text
backend/
```

Frontend lives separately:

```text
frontend/
```

### Backend Runtime Model

The backend contains multiple logical agents:

1. Orchestrator Agent
2. Interviewer Agent
3. Evaluator Agent
4. Streamer / SSE service

For the first build, these run as separate backend modules/processes under the same repo.

Do not split into separate repos yet.

---

## 3. Authentication & Session Tokens

### Session Token

On session creation (`POST /api/v1/sessions`), the server issues a `session_token` — a cryptographically random UUID (v4).

The token is returned in the session creation response and must be supplied by the client on all subsequent requests for that session.

### Token Usage

| Endpoint | Auth Required |
|---|---|
| `POST /api/v1/sessions` | None (public, rate-limited) |
| `POST /api/v1/sessions/{id}/answers` | `X-Session-Token` header |
| `GET /api/v1/sessions/{id}/stream` | `X-Session-Token` query param (`?token=`) |
| `GET /api/v1/sessions/{id}` | `X-Session-Token` header |
| `POST /api/v1/sessions/{id}/end` | `X-Session-Token` header |
| `GET /api/v1/sessions/{id}/report` | `X-Session-Token` header |
| `GET /api/v1/health` | None |
| `GET /api/v1/metrics` | API key (internal only) |

### Token Validation Rules

- Token must match the session on record in Postgres.
- Mismatched or missing token returns `401 Unauthorized`.
- Token is stored as a non-secret string in the sessions table for V1.
- Token is not rotated mid-session.
- Token is valid only for the lifetime of the interview session.
- Token must never be logged in application logs, access logs, analytics logs, or UI logs.
- Because the SSE endpoint receives the token in the URL query string, production deployments should configure reverse proxies to redact the `token` query parameter from logs.
- Later phase: replace raw token query param with a short-lived signed SSE URL.

Note: `X-Session-Token` is passed as a query param on the SSE endpoint because `EventSource` in browsers does not support custom headers.

---

## 4. Core Agents

### 4.1 Orchestrator Agent

Role: deterministic state-machine controller.

Responsibilities:

- Start interview sessions
- Maintain session state
- Accept user answers
- Enforce answer idempotency
- Update `last_activity_at` on every answer submit
- Renew Redis lock heartbeat during long turns
- Call Evaluator
- Call Interviewer
- Emit streaming events
- Enforce latency budgets
- Apply fallback rules
- End sessions

Important rule:

The Orchestrator does not make intelligent content decisions. It only coordinates.

---

### 4.2 Interviewer Agent

Role: autonomous question generator.

Inputs:

- Candidate profile
- Role being interviewed for
- Session history
- Previous answers
- Previous scores
- Weakness map
- Current difficulty

Output:

- Next interview question
- Optional rationale/debug metadata
- Difficulty level

Constraints:

- Timeout: 5 seconds
- max_iterations: 6
- Soft target: 3–4 reasoning/tool steps
- Enforced cap: after 4 iterations, terminate unless critical

**Difficulty progression rules:**

- Initial difficulty: `medium`
- If last score ≥ 8: increase difficulty one level (medium → hard)
- If last score ≤ 3: decrease difficulty one level (hard → medium, medium → easy)
- Difficulty cannot go below `easy` or above `hard`
- Fallback questions from the fallback bank inherit the current difficulty level

Fallback:

If Interviewer exceeds timeout, return a safe fallback question from a predefined question bank at the current difficulty level.

---

### 4.3 Evaluator Agent

Role: score candidate answer.

Inputs:

- Current question
- Candidate answer
- Expected rubric
- Role level
- Session context

Output:

```json
{
  "score": 7,
  "feedback": "Good explanation, but missed tradeoffs.",
  "confidence": "HIGH",
  "fallback_flag": false,
  "source": "llm"
}
```

**Confidence field rules:**

The LLM is prompted to self-report confidence using these criteria:

- Return `HIGH` if the answer is sufficiently detailed to evaluate against the rubric.
- Return `LOW` if the answer is too short, off-topic, in a different language, or otherwise ambiguous.

Example prompt fragment:

```text
Return confidence: HIGH if you can evaluate the answer against the rubric.
Return confidence: LOW if the answer is too vague, off-topic, or unclear to score reliably.
```

Server-side override: regardless of LLM output, set `confidence: LOW` and `fallback_flag: true` if:

- The LLM call times out.
- The LLM returns a malformed response.

Constraints:

- Score scale: 0–10
- Timeout: 4 seconds

Fallback on timeout:

```json
{
  "score": 5,
  "feedback": "Evaluation timed out. Neutral fallback score applied.",
  "confidence": "LOW",
  "fallback_flag": true,
  "source": "fallback_timeout"
}
```

If previous score exists for the session, reuse previous score instead of defaulting to 5.

LOW confidence scores are weighted lower in final report using weight = 0.5.

---

### 4.4 Streamer / SSE Service

Role: reliable real-time event delivery to frontend.

Fast path:

- Redis Pub/Sub

Durable fallback:

- Postgres events table

Write path:

```text
Event → Redis Pub/Sub
Event → Postgres async write
```

Read path:

```text
SSE reads Redis first
If no Redis event within 500ms, poll Postgres events table
```

**SSE reconnection and replay:**

The SSE endpoint supports the standard `Last-Event-ID` header (sent automatically by the browser `EventSource` on reconnect).

When `Last-Event-ID` is present:

1. Resolve `Last-Event-ID` to its stored `event_seq` for that session.
2. Query Postgres `events` table for all events for this session with `event_seq > last_event_seq`, ordered by `event_seq` ascending.
3. Replay those events immediately over the new SSE connection before resuming live Redis streaming.
4. If `Last-Event-ID` is absent or not found in Postgres, stream from the current live position only.

All events written to Postgres must store their `event_id` as the SSE `id:` field so the browser can track position.

Critical implementation rule:

Postgres event writes must be async / non-blocking. A slow Postgres write must never delay Redis streaming.

---

## 5. Session State Machine

```text
INIT
  → QUESTIONING
  → EVALUATING
  → DECIDING
  → QUESTIONING
  → END
```

### State Meanings

| State | Meaning |
|---|---|
| INIT | Session created |
| QUESTIONING | Candidate is viewing/responding to a question |
| EVALUATING | Evaluator is scoring the answer |
| DECIDING | Orchestrator decides next action |
| END | Interview complete |

---

## 6. Latency Budget

Total target turn budget: around 12 seconds.

| Component | Budget |
|---|---:|
| Queue wait | ≤ 2s normal, ≤ 5–7s peak |
| Evaluator | ≤ 4s |
| Interviewer | ≤ 5s |
| Buffer | ~1s |

### UX Rules

| Delay | UI Message |
|---|---|
| < 1s | no special message |
| 1–3s | Thinking... |
| 3–5s | Slight delay (~3s) |
| > 5s | High load (~5–7s delay) |

Immediate event after answer submit:

```json
{
  "event_type": "thinking",
  "payload": {
    "message": "Thinking..."
  }
}
```

---

## 7. Concurrency Rules

Target validated load:

```text
N = 50 concurrent users
```

Design target:

```text
N = 200 concurrent users
```

LLM semaphore:

```text
20 concurrent LLM calls
```

Overflow:

- queue requests
- surface queue delay to UI
- prioritize active sessions over new sessions

**LLM semaphore enforcement:**

Before any Evaluator or Interviewer LLM call, acquire the global LLM semaphore.

If semaphore is full:

1. Queue the call.
2. Emit `queue_delay` event with estimated delay bucket.
3. Wait up to 2 seconds for a slot.
4. If still no slot is available:
   - Evaluator path: use fallback evaluation.
   - Interviewer path: use fallback question bank.
5. Release semaphore in a `finally` block after each LLM call attempt.

Redis lock:

```text
lock key: session:{session_id}:lock
TTL: 18 seconds
heartbeat: every 5 seconds (see turn flow Step 5a)
```

**Lock acquisition failure rule:**

If the session lock cannot be acquired:

1. Emit `queue_delay` event if an SSE connection exists.
2. Retry lock acquisition with exponential backoff.
3. Maximum attempts: 3.
4. Total wait budget: ≤ 2 seconds.
5. If still not acquired, return `429 session_busy`.
6. Do not persist a new answer or start evaluation.

Error response:

```json
{
  "error": "session_busy",
  "message": "Another turn is already being processed for this session. Please wait for the next question or retry shortly."
}
```

**Stuck process rule:**

If a worker crashes while holding the lock, Redis TTL expiry releases the lock automatically. DB-level idempotency on `(session_id, question_id)` remains the final safety guard.

**Turn-in-progress rule:**

If a lock already exists for the session, treat it as a turn already in progress and do not start a second evaluation cycle for the same session.

---

## 8. API Endpoints

Base path:

```text
/api/v1
```

---

### 8.1 Health Check

```http
GET /api/v1/health
```

Response:

```json
{
  "status": "ok",
  "service": "ai-agentic-interview",
  "version": "5.0"
}
```

---

### 8.2 Start Interview Session

```http
POST /api/v1/sessions
```

Request:

```json
{
  "candidate_id": "cand_123",
  "candidate_name": "Kumar",
  "role": "Senior React + AI Engineer",
  "experience_level": "senior",
  "interview_type": "frontend_ai_fullstack",
  "max_questions": 8
}
```

**Validation:**

- `experience_level`: enum — `junior | mid | senior`
- `interview_type`: enum — `frontend_ai_fullstack | backend_systems | fullstack_general | data_ml | devops`
- `max_questions`: integer, valid range 1–20

**Rate limit:**

- 10 requests/minute per IP for public demo usage
- 50 requests/minute global soft cap for V1 deployment
- If exceeded, return `429 Too Many Requests`
- Active interview turns must be prioritized over new session creation when LLM queue pressure is high

Error response example:

```json
{
  "error": "session_creation_rate_limited",
  "message": "Too many interview sessions are being created. Please try again shortly."
}
```

Response:

```json
{
  "session_id": "sess_abc123",
  "session_token": "tok_f3a9b2c1-...",
  "status": "QUESTIONING",
  "current_question": {
    "question_id": "q_001",
    "text": "Explain how React reconciliation works.",
    "difficulty": "medium"
  },
  "stream_url": "/api/v1/sessions/sess_abc123/stream?token=tok_f3a9b2c1-..."
}
```

Notes:

- `session_token` is issued once here. Client must store it.
- `stream_url` includes the token as a query param for `EventSource` compatibility.
- Session starts with first question. First question may come from Interviewer Agent or a predefined starter bank.
- `last_activity_at` is set to session creation time on init.

---

### 8.3 Submit Answer

```http
POST /api/v1/sessions/{session_id}/answers
```

Headers:

```http
X-Session-Token: tok_f3a9b2c1-...
```

Request:

```json
{
  "question_id": "q_001",
  "answer_text": "React uses a virtual DOM and compares previous and next trees..."
}
```

**Idempotency rule:**

If an answer for `question_id` already exists in the `answers` table for this session, return:

```http
409 Conflict
```

```json
{
  "error": "answer_already_submitted",
  "message": "An answer for question q_001 has already been submitted."
}
```

This prevents duplicate evaluation cycles caused by network retries or double submissions.

`last_activity_at` on the session must be updated on every successful (non-409) answer submission.

Immediate Response (first submission):

```json
{
  "status": "processing",
  "message": "Answer received. Evaluation started. Listen to SSE stream for updates."
}
```

Expected streamed events after this:

1. `thinking`
2. `evaluation_started`
3. `evaluation_completed`
4. `question_generated` OR `interview_completed`

---

### 8.4 Stream Session Events

```http
GET /api/v1/sessions/{session_id}/stream?token={session_token}
```

Protocol:

```text
Server-Sent Events (SSE)
```

**Reconnection support:**

The client `EventSource` automatically sends `Last-Event-ID` on reconnect. The server must honour this header by replaying missed events from Postgres before resuming live streaming (see Section 4.4).

Each SSE event must include an `id:` field matching its `event_id`:

```text
id: evt_001
data: {"event_id":"evt_001","event_seq":1,"session_id":"sess_abc123","event_type":"thinking",...}
```

Example SSE events:

```json
{
  "event_id": "evt_001",
  "event_seq": 1,
  "session_id": "sess_abc123",
  "event_type": "thinking",
  "payload": {
    "message": "Thinking..."
  },
  "created_at": "2026-04-25T10:30:00Z"
}
```

```json
{
  "event_id": "evt_002",
  "event_seq": 2,
  "session_id": "sess_abc123",
  "event_type": "evaluation_started",
  "payload": {
    "question_id": "q_001"
  },
  "created_at": "2026-04-25T10:30:01Z"
}
```

```json
{
  "event_id": "evt_003",
  "event_seq": 3,
  "session_id": "sess_abc123",
  "event_type": "evaluation_completed",
  "payload": {
    "question_id": "q_001",
    "score": 7,
    "feedback": "Good explanation, but add details on diffing and keys.",
    "confidence": "HIGH",
    "fallback_flag": false,
    "source": "llm"
  },
  "created_at": "2026-04-25T10:30:05Z"
}
```

```json
{
  "event_id": "evt_004",
  "event_seq": 4,
  "session_id": "sess_abc123",
  "event_type": "question_generated",
  "payload": {
    "question_id": "q_002",
    "text": "Why are keys important when rendering lists in React?",
    "difficulty": "medium"
  },
  "created_at": "2026-04-25T10:30:09Z"
}
```

```json
{
  "event_id": "evt_005",
  "event_seq": 5,
  "session_id": "sess_abc123",
  "event_type": "error",
  "payload": {
    "code": "evaluator_timeout",
    "message": "Evaluation timed out. A fallback score has been applied.",
    "fallback_applied": true
  },
  "created_at": "2026-04-25T10:30:10Z"
}
```

---

### 8.5 Get Session Details

```http
GET /api/v1/sessions/{session_id}
```

Headers:

```http
X-Session-Token: tok_f3a9b2c1-...
```

Response:

```json
{
  "session_id": "sess_abc123",
  "candidate_id": "cand_123",
  "status": "QUESTIONING",
  "role": "Senior React + AI Engineer",
  "experience_level": "senior",
  "current_question_id": "q_002",
  "questions_asked": 2,
  "max_questions": 8,
  "average_score": 7.0,
  "last_activity_at": "2026-04-25T10:30:09Z",
  "created_at": "2026-04-25T10:25:00Z",
  "updated_at": "2026-04-25T10:30:09Z"
}
```

---

### 8.6 Get Final Report

```http
GET /api/v1/sessions/{session_id}/report
```

Headers:

```http
X-Session-Token: tok_f3a9b2c1-...
```

Response:

```json
{
  "session_id": "sess_abc123",
  "candidate_id": "cand_123",
  "status": "END",
  "is_complete": true,
  "end_reason": "candidate_completed",
  "overall_score": 7.2,
  "weighted_score": 7.0,
  "strengths": [
    "Good React fundamentals",
    "Clear explanation style"
  ],
  "weaknesses": [
    "Needs deeper performance tradeoff discussion",
    "Should mention accessibility more often"
  ],
  "question_results": [
    {
      "question_id": "q_001",
      "question": "Explain how React reconciliation works.",
      "answer": "React uses a virtual DOM...",
      "score": 7,
      "confidence": "HIGH",
      "feedback": "Good explanation, but add details on diffing and keys."
    }
  ],
  "recommendation": "Proceed to technical round"
}
```

**`is_complete` rules:**

- `true` if session ended via `candidate_completed` or `max_questions_reached`
- `false` if session ended via `inactive_timeout` or `manual`

When `is_complete` is `false`, the report must include a note field:

```json
{
  "is_complete": false,
  "end_reason": "inactive_timeout",
  "note": "This report is partial. The interview ended due to inactivity before all questions were completed.",
  "recommendation": null
}
```

When `is_complete` is `false`, `recommendation` must be `null` — do not apply the scoring threshold rules to an incomplete session.

**Recommendation rules (rules engine, not LLM) — complete sessions only:**

| Weighted Score | Recommendation |
|---|---|
| ≥ 7.5 | Proceed to technical round |
| 5.0 – 7.4 | Consider with reservations |
| < 5.0 | Do not proceed |

---

### 8.7 End Session

```http
POST /api/v1/sessions/{session_id}/end
```

Headers:

```http
X-Session-Token: tok_f3a9b2c1-...
```

Request:

```json
{
  "reason": "candidate_completed"
}
```

Response:

```json
{
  "session_id": "sess_abc123",
  "status": "END",
  "message": "Interview session ended."
}
```

**Idempotency rule:**

If the session is already in `END` state, return `200 OK` with:

```json
{
  "session_id": "sess_abc123",
  "status": "END",
  "message": "Session already ended."
}
```

Calling `/end` repeatedly must never create duplicate report rows, duplicate completion events, or errors.

---

### 8.8 Metrics Endpoint

```http
GET /api/v1/metrics
```

Security:

- API key required (`X-API-Key` header), or
- internal network only
- Rate limit: 60 requests/minute per API key

Metrics:

```json
{
  "active_sessions": 32,
  "queue_depth": 6,
  "avg_evaluator_latency_ms": 3100,
  "avg_interviewer_latency_ms": 4200,
  "llm_calls_in_progress": 18,
  "redis_status": "ok",
  "postgres_status": "ok"
}
```

---

## 9. Core Data Schemas

Use Pydantic models in FastAPI.

---

### 9.1 Session

```json
{
  "session_id": "string",
  "session_token": "string",
  "candidate_id": "string",
  "candidate_name": "string",
  "role": "string",
  "experience_level": "junior | mid | senior",
  "interview_type": "frontend_ai_fullstack | backend_systems | fullstack_general | data_ml | devops",
  "status": "INIT | QUESTIONING | EVALUATING | DECIDING | END",
  "end_reason": "candidate_completed | max_questions_reached | inactive_timeout | manual | null",
  "current_question_id": "string | null",
  "current_difficulty": "easy | medium | hard",
  "max_questions": "integer (1–20)",
  "questions_asked": "integer",
  "last_activity_at": "datetime",
  "created_at": "datetime",
  "updated_at": "datetime"
}
```

`last_activity_at` is set on session creation and updated on every successful answer submission. The inactivity cleanup worker compares `last_activity_at` against `now()` to identify sessions to auto-END.

`end_reason` is `null` until the session reaches `END` state.

---

### 9.2 Question

```json
{
  "question_id": "string",
  "session_id": "string",
  "text": "string",
  "difficulty": "easy | medium | hard",
  "topic": "string",
  "source": "interviewer_agent | fallback_bank",
  "created_at": "datetime"
}
```

---

### 9.3 Answer

```json
{
  "answer_id": "string",
  "session_id": "string",
  "question_id": "string",
  "answer_text": "string",
  "created_at": "datetime"
}
```

Unique constraint: `(session_id, question_id)` — enforced at DB level.

---

### 9.4 Evaluation

```json
{
  "evaluation_id": "string",
  "session_id": "string",
  "question_id": "string",
  "answer_id": "string",
  "score": "number 0–10",
  "feedback": "string",
  "confidence": "HIGH | LOW",
  "fallback_flag": "boolean",
  "source": "llm | fallback_timeout",
  "created_at": "datetime"
}
```

---

### 9.5 Event

```json
{
  "event_id": "string",
  "event_seq": "integer, monotonic per session, starts at 1",
  "session_id": "string",
  "event_type": "thinking | evaluation_started | evaluation_completed | question_generated | interview_completed | error | queue_delay",
  "payload": "json",
  "created_at": "datetime"
}
```

`event_id` must be written as the SSE `id:` field so the browser tracks position for `Last-Event-ID`.

`event_seq` is monotonic per session, starting at 1. It is the authoritative ordering field for Postgres replay. If `created_at` timestamps are identical, order by `event_seq` ascending.

`event_seq` must appear in the SSE `data:` payload alongside `event_id` so clients can detect gaps if needed.

---

### 9.6 Weakness Map

```json
{
  "session_id": "string",
  "topic": "string",
  "low_score_count": "integer",
  "follow_up_count": "integer",
  "last_score": "number",
  "updated_at": "datetime"
}
```

Rules:

- `low_score_threshold` = 3 on 0–10 scale
- `follow_up_cap` = 2 — maximum follow-up questions per weak topic
- Update weakness map only when `confidence == HIGH` and `fallback_flag == false`
- LOW-confidence or fallback evaluations must not increment `low_score_count` or `follow_up_count`
- When `follow_up_count >= 2` for a topic, the Interviewer must move on to a different topic
- If `fallback_flag` is true, ask a simpler/clarifying question next, but do not mark the topic weak from that fallback result alone

---

## 10. Database Tables

Minimum Postgres tables:

```text
sessions       (includes last_activity_at, end_reason)
questions
answers        (unique constraint on session_id + question_id)
evaluations
events         (includes event_seq)
weakness_map
```

For first build, keep schema simple. Do not over-normalize.

---

## 11. Event Types

Event types:

```text
thinking
evaluation_started
evaluation_completed
question_generated
interview_completed
queue_delay
error
```

All events must be written to:

1. Redis Pub/Sub
2. Postgres events table asynchronously

**Error event payload shape:**

```json
{
  "code": "string (evaluator_timeout | interviewer_timeout | lock_failed | internal_error)",
  "message": "string (human-readable)",
  "fallback_applied": "boolean"
}
```

---

## 12. Orchestrator Turn Flow

```text
on answer submit:

1.  Validate session (status must be QUESTIONING)
2.  Validate session_token
3.  Check idempotency: if answer for question_id already exists → return 409
4.  Check if Redis session lock already exists
    - If lock exists → retry/backoff up to 3 attempts, total ≤ 2s
    - If still locked → return 429 session_busy
5.  Acquire Redis session lock (TTL 18s)
5a. Start lock heartbeat task: renew TTL every 5 seconds for duration of turn
6.  Update last_activity_at on session
7.  Emit thinking event (event_seq = next seq for session)
8.  Emit evaluation_started event (event_seq = next seq)
9.  Acquire LLM semaphore for Evaluator
    - If semaphore full → emit queue_delay, wait up to 2s, else fallback evaluation
10. Call Evaluator with 4s timeout
11. If timeout or error, create fallback evaluation; emit error event
12. Persist answer + evaluation
13. Update weakness map only if confidence HIGH and fallback_flag false
14. If max_questions reached → set end_reason = max_questions_reached, end interview, emit interview_completed event
15. Else acquire LLM semaphore for Interviewer
    - If semaphore full → emit queue_delay, wait up to 2s, else fallback question
16. Call Interviewer with 5s timeout (pass updated weakness map and current_difficulty)
17. If timeout, choose fallback question from bank at current difficulty
18. Update current_difficulty on session based on score
19. Persist question
20. Emit question_generated event (event_seq = next seq)
21. Cancel lock heartbeat task
22. Release lock in finally block
```

---

## 13. Session Timeout and Cleanup Rules

### Inactivity Timeout

If a session has no candidate activity for 10 minutes (determined by `last_activity_at`):

1. Mark session as `END`, set `end_reason = inactive_timeout`.
2. Release any active Redis lock if owned by the current worker.
3. Emit `interview_completed` event if the stream is still connected.
4. Generate a partial report from completed evaluations.

This prevents abandoned sessions from consuming memory, queue priority, or stale state.

### Cleanup Safety

- Cleanup must be idempotent.
- Cleanup must not duplicate `interview_completed` events.
- Cleanup must not delete answers, evaluations, or events.
- Reports generated from timed-out sessions must have `is_complete: false` and `recommendation: null`.

---

## 14. Fallback Rules

### Evaluator Timeout

Use previous score if available.

Else use:

```json
{
  "score": 5,
  "confidence": "LOW",
  "fallback_flag": true,
  "source": "fallback_timeout"
}
```

Emit an `error` event with `code: "evaluator_timeout"`.

### Interviewer Timeout

Use fallback question bank at current difficulty level.

Example easy:

```text
Can you explain that concept with a simple example?
```

Example medium:

```text
What tradeoffs would you consider when implementing this?
```

Example hard:

```text
How would this approach behave under high load or at scale?
```

Emit an `error` event with `code: "interviewer_timeout"`.

### Redis Degraded

- Continue using Postgres polling for SSE fallback
- Do not crash active sessions

### Postgres Slow

- Redis streaming must continue
- Postgres event writes are async/non-blocking

---

## 15. Cursor Build Notes

1. Build backend first.
2. Use FastAPI + Pydantic.
3. Keep all backend agents under `backend/`.
4. Implement APIs before UI polish.
5. Mock LLM calls first, then integrate real LLM.
6. Implement SSE early; include `id:` field and `event_seq` on every event.
7. Redis Pub/Sub is the fast stream path.
8. Postgres event writes must be async/non-blocking.
9. Add simple fallback question bank (at least one question per difficulty level).
10. Add unique DB constraint on `(session_id, question_id)` in `answers` table.
11. Add `event_seq` as a per-session auto-incrementing integer to the `events` table.
12. Implement `Last-Event-ID` replay from Postgres on SSE reconnect, ordered by `event_seq`.
13. Add `last_activity_at` and `end_reason` columns to `sessions` table.
14. Add inactivity cleanup worker: poll for sessions where `last_activity_at < now() - 10 minutes` and `status != END`.
15. Keep code simple and readable; avoid premature microservices.

---

## 16. First Build Scope

Build these first:

- Start session endpoint (with session_token issuance, last_activity_at init)
- Submit answer endpoint (with idempotency check, last_activity_at update)
- SSE stream endpoint (with token auth + Last-Event-ID replay via event_seq)
- Mock Evaluator
- Mock Interviewer
- Redis event publishing (with event_seq)
- Postgres event persistence
- Weakness map tracking
- Inactivity cleanup worker
- Basic final report with rules-based recommendation and is_complete flag

Then replace mock agents with real LLM agents.

---

## 17. Explicit Non-Goals for V5.0

Do not build yet:

- Kafka
- Kubernetes
- Full microservices split
- Advanced admin dashboard
- Video/audio interview handling
- Enterprise auth (OAuth, SSO)
- Multi-tenant billing
- Token rotation mid-session
- Signed SSE URLs (later phase)

These are later-phase items.


---

## 18A. Frontend Specification

V5.0 includes the frontend implementation contract alongside all backend APIs, schemas, concurrency rules, lock rules, SSE rules, and fallback rules.

### 18A.1 Frontend Tech Stack

Use:

```text
Next.js App Router
React 18+
TypeScript
Native EventSource for SSE
Plain React state/hooks for V1
```

Do not use Redux for the first build. Zustand may be considered later only if state becomes difficult to manage.

---

### 18A.2 Frontend App Structure

```text
frontend/
  app/
    page.tsx
    interview/
      [session_id]/
        page.tsx
    report/
      [session_id]/
        page.tsx

  components/
    StartInterviewForm.tsx
    QuestionPanel.tsx
    AnswerInput.tsx
    FeedbackPanel.tsx
    StatusBanner.tsx
    LogPanel.tsx
    ReportView.tsx

  lib/
    api.ts
    sse.ts
    types.ts
```

### Page Responsibilities

| Page | Responsibility |
|---|---|
| `/` | Start interview form |
| `/interview/[session_id]` | Live interview experience |
| `/report/[session_id]` | Final/partial report display |

---

### 18A.3 Frontend Data Types

```ts
type Question = {
  question_id: string;
  text: string;
  difficulty: "easy" | "medium" | "hard";
};
```

```ts
type SessionState = {
  sessionId: string;
  token: string;
  status: "QUESTIONING" | "PROCESSING" | "END";
  currentQuestion: Question | null;
  feedback: EvaluationPayload | null;
  logs: SessionEvent[];
  isStreaming: boolean;
  lastSeenSeq: number;
};
```

```ts
type EvaluationPayload = {
  question_id: string;
  score: number;
  feedback: string;
  confidence: "HIGH" | "LOW";
  fallback_flag: boolean;
  source: "llm" | "fallback_timeout";
};
```

```ts
type SessionEvent = {
  event_id: string;
  event_seq: number;
  session_id: string;
  event_type:
    | "thinking"
    | "evaluation_started"
    | "evaluation_completed"
    | "question_generated"
    | "interview_completed"
    | "queue_delay"
    | "error";
  payload: Record<string, unknown>;
  created_at: string;
};
```

Critical frontend rule:

```text
event_seq is the source of truth for ordering.
```

The frontend must ignore any event where:

```text
event.event_seq <= lastSeenSeq
```

This prevents duplicate processing during SSE reconnects.

---

### 18A.4 Start Interview Flow

Frontend calls:

```http
POST /api/v1/sessions
```

Request body must follow Section 8.2.

On success, backend returns:

```json
{
  "session_id": "sess_abc123",
  "session_token": "tok_f3a9b2c1-...",
  "status": "QUESTIONING",
  "current_question": {
    "question_id": "q_001",
    "text": "Explain how React reconciliation works.",
    "difficulty": "medium"
  },
  "stream_url": "/api/v1/sessions/sess_abc123/stream?token=tok_f3a9b2c1-..."
}
```

Frontend must:

1. Store `session_id` and `session_token` in React state.
2. Store `current_question`.
3. Navigate to `/interview/{session_id}`.
4. Open the SSE stream.

Security rule:

```text
Do not store session_token in localStorage for V1.
Prefer in-memory state. If refresh support is needed later, use secure server-side/session storage.
```

---

### 18A.5 SSE Stream Flow

Frontend opens:

```ts
const es = new EventSource(`/api/v1/sessions/${sessionId}/stream?token=${token}`);
```

Browser `EventSource` does not support custom headers, so the query token approach remains valid.

Frontend handler:

```ts
es.onmessage = (message) => {
  const event = JSON.parse(message.data) as SessionEvent;

  if (event.event_seq <= lastSeenSeq) return;

  lastSeenSeq = event.event_seq;
  handleEvent(event);
  appendToLogPanel(event);
};
```

Reconnect behavior:

- Browser automatically reconnects.
- Browser automatically sends `Last-Event-ID` when the server provides SSE `id:` fields.
- Frontend must not reset interview state on transient SSE errors.
- Frontend should display a temporary “Reconnecting...” banner on `es.onerror`.

---

### 18A.6 Submit Answer Flow

Frontend calls:

```http
POST /api/v1/sessions/{session_id}/answers
X-Session-Token: {session_token}
```

Request:

```json
{
  "question_id": "q_001",
  "answer_text": "Candidate answer text..."
}
```

Frontend behavior after submit:

1. Validate non-empty answer.
2. Disable answer input.
3. Disable submit button.
4. Set UI state to `PROCESSING`.
5. Show “Thinking...” only after the SSE `thinking` event arrives.
6. Do not manually generate the next question in the frontend.
7. Wait for SSE events.

On `409 answer_already_submitted`:

- Show a non-fatal message.
- Keep listening to SSE.
- Do not resubmit automatically.

On `429 session_busy`:

- Show “Another turn is already being processed. Please wait.”
- Keep listening to SSE.

---

### 18A.7 Event-to-UI Mapping

| Event Type | Frontend Behavior |
|---|---|
| `thinking` | Show spinner / “Thinking...” |
| `evaluation_started` | Append log entry |
| `evaluation_completed` | Show feedback and score in FeedbackPanel |
| `question_generated` | Replace current question, clear answer box, enable input |
| `queue_delay` | Show StatusBanner with delay message |
| `error` | Show warning banner/toast; continue if fallback applied |
| `interview_completed` | Set status END and navigate to report page |

---

### 18A.8 Interview Page Layout

Recommended simple layout:

```text
------------------------------------------------
StatusBanner
------------------------------------------------
QuestionPanel
------------------------------------------------
AnswerInput + Submit Button
------------------------------------------------
FeedbackPanel
------------------------------------------------
LogPanel
------------------------------------------------
```

### Component Responsibilities

| Component | Responsibility |
|---|---|
| `QuestionPanel` | Display current question and difficulty |
| `AnswerInput` | Capture answer, disable during processing |
| `FeedbackPanel` | Display latest score, feedback, confidence, fallback status |
| `StatusBanner` | Display queue delay, reconnecting, high load, warnings |
| `LogPanel` | Display all streamed events in order |
| `ReportView` | Display final or partial report |

---

### 18A.9 Log Panel Requirement

Every SSE event must be appended to the LogPanel.

Minimum log format:

```text
[1] thinking — Thinking...
[2] evaluation_started — q_001
[3] evaluation_completed — score: 7, confidence: HIGH
[4] question_generated — q_002
```

Do not display or log the `session_token`.

The LogPanel is required for debugging and demo clarity.

---

### 18A.10 Report Page Flow

On `interview_completed`, frontend navigates to:

```text
/report/{session_id}
```

Frontend calls:

```http
GET /api/v1/sessions/{session_id}/report
X-Session-Token: {session_token}
```

ReportView must handle both complete and incomplete reports.

If:

```json
{
  "is_complete": false,
  "recommendation": null
}
```

Then UI must show:

```text
Partial report — interview ended before completion.
```

Do not show “Proceed / Do not proceed” style recommendation for incomplete reports.

---

### 18A.11 Frontend Error Handling

Frontend must handle:

| Backend Error | UI Behavior |
|---|---|
| `401 Unauthorized` | Show session expired/invalid message |
| `409 answer_already_submitted` | Show duplicate answer warning; keep stream alive |
| `429 session_busy` | Show busy warning; keep stream alive |
| SSE disconnect | Show reconnecting banner |
| `error` SSE with `fallback_applied: true` | Show warning but continue interview |
| `error` SSE with `fallback_applied: false` | Show stronger error message |

---

### 18A.12 Frontend Security Rules

- Never display `session_token`.
- Never append `session_token` to LogPanel.
- Never send token to analytics.
- Never store token in localStorage for V1.
- Use in-memory state for first build.
- In later builds, use short-lived signed SSE URLs or secure server-side session handling.

---

### 18A.13 FE/BE Contract Check

| Contract Item | Backend | Frontend | Status |
|---|---|---|---|
| `session_id` | Returned by `POST /sessions` | Used for route + API calls | Aligned |
| `session_token` | Returned by `POST /sessions` | Header for APIs, query for SSE | Aligned |
| `current_question` | Returned at session start | Rendered immediately | Aligned |
| `event_id` | Sent as SSE `id:` | Browser uses for reconnect | Aligned |
| `event_seq` | Sent in `data:` payload | Used for ordering/dedupe | Aligned |
| `Last-Event-ID` | Backend replays from Postgres | Browser sends automatically | Aligned |
| `evaluation_completed` | Contains score/feedback/confidence | Rendered in FeedbackPanel | Aligned |
| `question_generated` | Contains next question | Enables next answer | Aligned |
| `interview_completed` | Final event | Navigates to report | Aligned |
| incomplete report | `recommendation: null` | Shows partial report message | Aligned |

No FE/BE mismatch is known in V5.0.

---

### 18A.14 Frontend Build Phases

Phase 1:

- Start interview
- Open SSE stream
- Show first question
- Submit answer
- Receive next question

Phase 2:

- FeedbackPanel
- LogPanel
- Queue delay banner
- Error banner

Phase 3:

- Report page
- Styling polish
- Mobile responsiveness

---

### 18A.15 Cursor Frontend Notes

Cursor must not invent extra backend endpoints for frontend convenience.

Use only the V5.0 API contract:

```text
POST /api/v1/sessions
POST /api/v1/sessions/{id}/answers
GET  /api/v1/sessions/{id}/stream?token=...
GET  /api/v1/sessions/{id}
POST /api/v1/sessions/{id}/end
GET  /api/v1/sessions/{id}/report
```

The frontend must be event-driven. It must not poll for the next question.

---

## 18. Final Build Verdict

This V5.0 spec is ready for Cursor fullstack code generation.

Architecture frozen from V4.8. V5.0 promotes the spec to a stable major version:

- `event_seq` now appears in all SSE wire format examples (Section 8.4)
- SSE replay step numbering corrected (Section 4.4, steps 1–4)
- `last_activity_at` added to Session schema, turn flow, and GET session response
- `end_reason` added to Session schema with full enum
- `is_complete` and `end_reason` added to report response; `recommendation: null` enforced for incomplete sessions
- DB tables summary updated to reflect new columns

All V4.6 foundations retained.

# STATUS: FROZEN ✅ — V5.0 READY FOR CURSOR CODE GENERATION


---

# FINAL STATUS: V5.0 FROZEN ✅ — FULLSTACK READY FOR CURSOR CODE GENERATION

Backend remains V4.8-stable.
Frontend specification locked in V5.0.
FE/BE contract is checked and aligned.

Use this document as the single source of truth for Cursor code generation. This is V5.0 — the build version.
