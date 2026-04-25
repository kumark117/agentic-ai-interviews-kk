import asyncio
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from agents.evaluator.mock_agent import MockEvaluatorAgent
from agents.interviewer.mock_agent import MockInterviewerAgent
from agents.orchestrator.rules import next_difficulty, recommendation
from agents.streamer.event_service import format_sse, publish_event, replay_events_by_last_event_id
from app.core.config import settings
from app.db.base import get_db_session
from app.models.models import Answer, Difficulty, EndReason, Evaluation, Event, EventType, Question, QuestionSource, Session, SessionStatus, WeaknessMap
from app.schemas.api import ErrorResponse, HealthResponse, SessionEventDTO, StartSessionRequest, StartSessionResponse, SubmitAnswerRequest, SubmitAnswerResponse
from app.services.llm_capacity import llm_semaphore
from app.services.lock_service import SessionBusyError, acquire_session_lock, start_lock_heartbeat
from app.services.rate_limit import check_rate_limit
from app.services.redis_client import redis_client

router = APIRouter()
evaluator = MockEvaluatorAgent()
interviewer = MockInterviewerAgent()


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _require_session(db: AsyncSession, session_id: str, token: str | None, token_name: str = "X-Session-Token") -> Session:
    if not token:
        raise HTTPException(status_code=401, detail={"error": "unauthorized", "message": f"Missing {token_name}"})
    session = await db.get(Session, session_id)
    if not session or session.session_token != token:
        raise HTTPException(status_code=401, detail={"error": "unauthorized", "message": "Invalid session token"})
    return session


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", service=settings.app_name, version=settings.app_version)


@router.post("/sessions", response_model=StartSessionResponse)
async def create_session(payload: StartSessionRequest, request: Request, db: AsyncSession = Depends(get_db_session)) -> StartSessionResponse:
    client_ip = request.client.host if request.client else "unknown"
    if not await check_rate_limit(redis_client, f"rl:sessions:ip:{client_ip}", 10, 60) or not await check_rate_limit(redis_client, "rl:sessions:global", 50, 60):
        raise HTTPException(status_code=429, detail={"error": "session_creation_rate_limited", "message": "Too many interview sessions are being created. Please try again shortly."})
    now = _now()
    session_id = f"sess_{uuid.uuid4().hex[:12]}"
    session_token = f"tok_{uuid.uuid4()}"
    qid = f"q_{uuid.uuid4().hex[:8]}"
    qtext = "Explain how React reconciliation works."
    db.add(
        Session(
            session_id=session_id,
            session_token=session_token,
            candidate_id=payload.candidate_id,
            candidate_name=payload.candidate_name,
            role=payload.role,
            experience_level=payload.experience_level,
            interview_type=payload.interview_type,
            status=SessionStatus.QUESTIONING,
            end_reason=None,
            current_question_id=qid,
            current_difficulty=Difficulty.medium,
            max_questions=payload.max_questions,
            questions_asked=1,
            last_activity_at=now,
            created_at=now,
            updated_at=now,
        )
    )
    await db.commit()
    db.add(
        Question(
            question_id=qid,
            session_id=session_id,
            text=qtext,
            difficulty=Difficulty.medium,
            topic="react_fundamentals",
            source=QuestionSource.fallback_bank,
            created_at=now,
        )
    )
    await db.commit()
    return StartSessionResponse(session_id=session_id, session_token=session_token, status=SessionStatus.QUESTIONING, current_question={"question_id": qid, "text": qtext, "difficulty": Difficulty.medium}, stream_url=f"/api/v1/sessions/{session_id}/stream?token={session_token}")


@router.post("/sessions/{session_id}/answers", response_model=SubmitAnswerResponse, responses={409: {"model": ErrorResponse}, 429: {"model": ErrorResponse}, 401: {"model": ErrorResponse}})
async def submit_answer(session_id: str, payload: SubmitAnswerRequest, x_session_token: str | None = Header(default=None), db: AsyncSession = Depends(get_db_session)) -> SubmitAnswerResponse:
    session = await _require_session(db, session_id, x_session_token)
    if session.status != SessionStatus.QUESTIONING:
        raise HTTPException(status_code=409, detail={"error": "invalid_state", "message": "Session is not accepting answers."})
    try:
        async with acquire_session_lock(redis_client, session_id) as lock_token:
            heartbeat = await start_lock_heartbeat(redis_client, session_id, lock_token)
            try:
                if await db.scalar(select(Answer).where(and_(Answer.session_id == session_id, Answer.question_id == payload.question_id))):
                    raise HTTPException(status_code=409, detail={"error": "answer_already_submitted", "message": f"An answer for question {payload.question_id} has already been submitted."})
                session.last_activity_at = _now()
                session.updated_at = _now()
                await publish_event(db, redis_client, session_id, EventType.thinking, {"message": "Thinking..."})
                await publish_event(db, redis_client, session_id, EventType.evaluation_started, {"question_id": payload.question_id})
                question = await db.get(Question, payload.question_id)
                if question is None or question.session_id != session_id:
                    raise HTTPException(status_code=409, detail={"error": "invalid_question", "message": "Question does not belong to this session."})
                prev = await db.scalar(select(Evaluation.score).where(Evaluation.session_id == session_id).order_by(Evaluation.created_at.desc()).limit(1))
                try:
                    await asyncio.wait_for(llm_semaphore.acquire(), timeout=2.0)
                except TimeoutError:
                    await publish_event(db, redis_client, session_id, EventType.queue_delay, {"message": "High load (~5-7s delay)"})
                    evaluation = await evaluator.evaluate(question.text, "", prev)
                else:
                    try:
                        evaluation = await evaluator.evaluate(question.text, payload.answer_text, prev)
                    finally:
                        llm_semaphore.release()
                answer_id = f"ans_{uuid.uuid4().hex[:10]}"
                db.add(Answer(answer_id=answer_id, session_id=session_id, question_id=payload.question_id, answer_text=payload.answer_text, created_at=_now()))
                db.add(Evaluation(evaluation_id=f"eval_{uuid.uuid4().hex[:10]}", session_id=session_id, question_id=payload.question_id, answer_id=answer_id, score=evaluation.score, feedback=evaluation.feedback, confidence=evaluation.confidence, fallback_flag=evaluation.fallback_flag, source=evaluation.source, created_at=_now()))
                await publish_event(db, redis_client, session_id, EventType.evaluation_completed, {"question_id": payload.question_id, "score": evaluation.score, "feedback": evaluation.feedback, "confidence": evaluation.confidence.value, "fallback_flag": evaluation.fallback_flag, "source": evaluation.source.value})
                if session.questions_asked >= session.max_questions:
                    session.status = SessionStatus.END
                    session.end_reason = EndReason.max_questions_reached
                    session.updated_at = _now()
                    await publish_event(db, redis_client, session_id, EventType.interview_completed, {"end_reason": "max_questions_reached"})
                else:
                    session.current_difficulty = next_difficulty(session.current_difficulty, evaluation.score)
                    previous_questions = (
                        await db.execute(
                            select(Question.text)
                            .where(Question.session_id == session_id)
                            .order_by(Question.created_at.asc())
                        )
                    ).scalars().all()
                    try:
                        await asyncio.wait_for(llm_semaphore.acquire(), timeout=2.0)
                    except TimeoutError:
                        await publish_event(db, redis_client, session_id, EventType.queue_delay, {"message": "High load (~5-7s delay)"})
                        next_question = await interviewer.generate_next_question(session.current_difficulty, previous_questions)
                    else:
                        try:
                            next_question = await interviewer.generate_next_question(session.current_difficulty, previous_questions)
                        finally:
                            llm_semaphore.release()
                    if evaluation.confidence.value == "HIGH" and evaluation.fallback_flag is False:
                        weakness = await db.scalar(select(WeaknessMap).where(and_(WeaknessMap.session_id == session_id, WeaknessMap.topic == question.topic)))
                        if weakness is None:
                            db.add(WeaknessMap(session_id=session_id, topic=question.topic, low_score_count=1 if evaluation.score <= 3 else 0, follow_up_count=0, last_score=evaluation.score, updated_at=_now()))
                        else:
                            if evaluation.score <= 3:
                                weakness.low_score_count += 1
                            weakness.last_score = evaluation.score
                            weakness.updated_at = _now()
                    db.add(Question(question_id=next_question.question_id, session_id=session_id, text=next_question.text, difficulty=next_question.difficulty, topic=next_question.topic, source=next_question.source, created_at=_now()))
                    session.current_question_id = next_question.question_id
                    session.questions_asked += 1
                    session.updated_at = _now()
                    await publish_event(db, redis_client, session_id, EventType.question_generated, {"question_id": next_question.question_id, "text": next_question.text, "difficulty": next_question.difficulty.value})
                await db.commit()
            except IntegrityError:
                await db.rollback()
                raise HTTPException(status_code=409, detail={"error": "answer_already_submitted", "message": f"An answer for question {payload.question_id} has already been submitted."})
            finally:
                heartbeat.cancel()
    except SessionBusyError:
        raise HTTPException(status_code=429, detail={"error": "session_busy", "message": "Another turn is already being processed for this session. Please wait for the next question or retry shortly."})
    return SubmitAnswerResponse(status="processing", message="Answer received. Evaluation started. Listen to SSE stream for updates.")


@router.get("/sessions/{session_id}/stream")
async def stream_session_events(request: Request, session_id: str, token: str = Query(...), db: AsyncSession = Depends(get_db_session)) -> StreamingResponse:
    await _require_session(db, session_id, token, token_name="token")
    last_event_id = request.headers.get("last-event-id")
    replay_events = await replay_events_by_last_event_id(db, session_id, last_event_id) if last_event_id else []
    baseline = max((e.event_seq for e in replay_events), default=0)
    if baseline == 0:
        latest = await db.scalar(select(Event.event_seq).where(Event.session_id == session_id).order_by(Event.event_seq.desc()).limit(1))
        baseline = int(latest or 0)

    async def event_generator():
        last_seq = baseline
        for event in replay_events:
            last_seq = max(last_seq, event.event_seq)
            yield format_sse(event)
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(f"session:{session_id}:events")
        try:
            while True:
                if await request.is_disconnected():
                    break
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.5)
                if message and message.get("type") == "message":
                    event = SessionEventDTO.model_validate(json.loads(message["data"]))
                    last_seq = max(last_seq, event.event_seq)
                    yield format_sse(event)
                    continue
                missing = (await db.execute(select(Event).where(Event.session_id == session_id, Event.event_seq > last_seq).order_by(Event.event_seq.asc()))).scalars().all()
                for row in missing:
                    event = SessionEventDTO(event_id=row.event_id, event_seq=row.event_seq, session_id=row.session_id, event_type=row.event_type, payload=row.payload, created_at=row.created_at)
                    last_seq = max(last_seq, event.event_seq)
                    yield format_sse(event)
                if not missing:
                    await asyncio.sleep(0.5)
        finally:
            await pubsub.unsubscribe(f"session:{session_id}:events")
            await pubsub.close()

    return StreamingResponse(event_generator(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"})


@router.get("/sessions/{session_id}")
async def get_session_details(session_id: str, x_session_token: str | None = Header(default=None), db: AsyncSession = Depends(get_db_session)):
    session = await _require_session(db, session_id, x_session_token)
    average_score = await db.scalar(select(func.avg(Evaluation.score)).where(Evaluation.session_id == session_id))
    return {"session_id": session.session_id, "candidate_id": session.candidate_id, "status": session.status, "role": session.role, "experience_level": session.experience_level, "current_question_id": session.current_question_id, "questions_asked": session.questions_asked, "max_questions": session.max_questions, "average_score": float(average_score or 0.0), "last_activity_at": session.last_activity_at, "created_at": session.created_at, "updated_at": session.updated_at}


@router.post("/sessions/{session_id}/end")
async def end_session(session_id: str, body: dict, x_session_token: str | None = Header(default=None), db: AsyncSession = Depends(get_db_session)):
    session = await _require_session(db, session_id, x_session_token)
    if session.status == SessionStatus.END:
        return {"session_id": session.session_id, "status": SessionStatus.END, "message": "Session already ended."}
    reason = body.get("reason", EndReason.manual.value)
    if reason not in {r.value for r in EndReason}:
        reason = EndReason.manual.value
    session.status = SessionStatus.END
    session.end_reason = EndReason(reason)
    session.updated_at = _now()
    await publish_event(db, redis_client, session_id, EventType.interview_completed, {"end_reason": reason})
    await db.commit()
    return {"session_id": session.session_id, "status": SessionStatus.END, "message": "Interview session ended."}


@router.get("/sessions/{session_id}/report")
async def get_final_report(session_id: str, x_session_token: str | None = Header(default=None), db: AsyncSession = Depends(get_db_session)):
    session = await _require_session(db, session_id, x_session_token)
    rows = (await db.execute(select(Answer, Question, Evaluation).join(Question, Question.question_id == Answer.question_id).join(Evaluation, Evaluation.answer_id == Answer.answer_id).where(Answer.session_id == session_id).order_by(Answer.created_at.asc()))).all()
    total = 0.0
    weighted_total = 0.0
    den = 0.0
    results = []
    for answer, question, evaluation in rows:
        total += evaluation.score
        w = 1.0 if evaluation.confidence.value == "HIGH" else 0.5
        weighted_total += evaluation.score * w
        den += w
        results.append({"question_id": question.question_id, "question": question.text, "answer": answer.answer_text, "score": evaluation.score, "confidence": evaluation.confidence.value, "feedback": evaluation.feedback})
    overall = round(total / len(results), 2) if results else 0.0
    weighted = round(weighted_total / den, 2) if den else 0.0
    is_complete = session.end_reason in {EndReason.candidate_completed, EndReason.max_questions_reached}
    rec = recommendation(weighted) if is_complete else None
    report = {"session_id": session.session_id, "candidate_id": session.candidate_id, "status": session.status, "is_complete": is_complete, "end_reason": session.end_reason.value if session.end_reason else None, "overall_score": overall, "weighted_score": weighted, "strengths": ["Clear communication"] if weighted >= 6 else [], "weaknesses": ["Needs deeper tradeoff analysis"] if weighted < 7.5 else [], "question_results": results, "recommendation": rec}
    if not is_complete:
        report["note"] = "This report is partial. The interview ended before all questions were completed."
    return report


@router.get("/metrics")
async def metrics(x_api_key: str | None = Header(default=None), db: AsyncSession = Depends(get_db_session)):
    if not x_api_key:
        raise HTTPException(status_code=401, detail={"error": "unauthorized", "message": "Missing X-API-Key"})
    if not await check_rate_limit(redis_client, f"rl:metrics:{x_api_key}", 60, 60):
        raise HTTPException(status_code=429, detail={"error": "rate_limited", "message": "Too many metrics requests for this API key."})
    active_sessions = await db.scalar(select(func.count()).select_from(Session).where(Session.status != SessionStatus.END))
    return {"active_sessions": int(active_sessions or 0), "queue_depth": 0, "avg_evaluator_latency_ms": 0, "avg_interviewer_latency_ms": 0, "llm_calls_in_progress": 0, "redis_status": "ok", "postgres_status": "ok"}
