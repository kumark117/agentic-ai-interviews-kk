import asyncio
import time

from app.models.models import Event
from agents.streamer import event_service
from app.api.v1 import routes as routes_module


def test_health_endpoint(client) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_missing_token_returns_401_on_answer(client) -> None:
    response = client.post("/api/v1/sessions/sess_missing/answers", json={"question_id": "q_001", "answer_text": "sample"})
    assert response.status_code == 401


def test_duplicate_answer_returns_409(client) -> None:
    start = client.post("/api/v1/sessions", json={"candidate_id": "cand_123", "candidate_name": "Kumar", "role": "Senior React + AI Engineer", "experience_level": "senior", "interview_type": "frontend_ai_fullstack", "max_questions": 8}).json()
    sid = start["session_id"]
    tok = start["session_token"]
    qid = start["current_question"]["question_id"]
    assert client.post(f"/api/v1/sessions/{sid}/answers", headers={"X-Session-Token": tok}, json={"question_id": qid, "answer_text": "React reconciliation compares trees."}).status_code == 200
    dup = client.post(f"/api/v1/sessions/{sid}/answers", headers={"X-Session-Token": tok}, json={"question_id": qid, "answer_text": "dup"})
    assert dup.status_code == 409


def test_session_busy_returns_429_when_lock_exists(client) -> None:
    start = client.post("/api/v1/sessions", json={"candidate_id": "cand_lock", "candidate_name": "Lock", "role": "Backend Engineer", "experience_level": "mid", "interview_type": "backend_systems", "max_questions": 3}).json()
    sid = start["session_id"]
    tok = start["session_token"]
    qid = start["current_question"]["question_id"]
    asyncio.run(routes_module.redis_client.set(f"session:{sid}:lock", "existing-lock", ex=18))
    resp = client.post(f"/api/v1/sessions/{sid}/answers", headers={"X-Session-Token": tok}, json={"question_id": qid, "answer_text": "busy"})
    assert resp.status_code == 429


def test_event_seq_is_monotonic_per_session(client) -> None:
    start = client.post("/api/v1/sessions", json={"candidate_id": "cand_seq", "candidate_name": "Seq", "role": "Fullstack Engineer", "experience_level": "mid", "interview_type": "fullstack_general", "max_questions": 3}).json()
    sid = start["session_id"]
    tok = start["session_token"]
    qid = start["current_question"]["question_id"]
    assert client.post(f"/api/v1/sessions/{sid}/answers", headers={"X-Session-Token": tok}, json={"question_id": qid, "answer_text": "Detailed answer to trigger full flow and multiple events."}).status_code == 200
    time.sleep(0.5)

    async def fetch_event_seqs() -> list[int]:
        async with event_service.AsyncSessionLocal() as db:
            rows = (await db.execute(Event.__table__.select().with_only_columns(Event.event_seq).where(Event.session_id == sid).order_by(Event.event_seq.asc()))).all()
            return [row[0] for row in rows]

    seqs = asyncio.run(fetch_event_seqs())
    assert seqs == sorted(seqs)
    assert seqs[0] == 1
    assert len(seqs) == len(set(seqs))
