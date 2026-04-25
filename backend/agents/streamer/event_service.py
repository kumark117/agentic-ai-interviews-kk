import asyncio
import json
import uuid
from datetime import datetime, timezone

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import AsyncSessionLocal
from app.models.models import Event, EventType, SessionEventSequence
from app.schemas.api import SessionEventDTO


def event_channel(session_id: str) -> str:
    return f"session:{session_id}:events"


async def next_event_seq(db: AsyncSession, session_id: str) -> int:
    row = await db.get(SessionEventSequence, session_id, with_for_update=True)
    if row is None:
        row = SessionEventSequence(session_id=session_id, last_event_seq=1)
        db.add(row)
        await db.flush()
        return 1

    row.last_event_seq += 1
    await db.flush()
    return row.last_event_seq


async def publish_event(
    db: AsyncSession,
    redis: Redis,
    session_id: str,
    event_type: EventType,
    payload: dict,
) -> SessionEventDTO:
    dialect_name = db.bind.dialect.name if db.bind is not None else ""
    if dialect_name == "sqlite":
        # SQLite test mode: avoid cross-connection writer locks.
        event_seq = await next_event_seq(db, session_id)
    else:
        async with AsyncSessionLocal() as seq_session:
            event_seq = await next_event_seq(seq_session, session_id)
            await seq_session.commit()

    event = SessionEventDTO(
        event_id=f"evt_{uuid.uuid4().hex}",
        event_seq=event_seq,
        session_id=session_id,
        event_type=event_type,
        payload=payload,
        created_at=datetime.now(timezone.utc),
    )
    await redis.publish(event_channel(session_id), event.model_dump_json())

    async def _persist() -> None:
        for attempt in range(3):
            try:
                if dialect_name == "sqlite":
                    db.add(
                        Event(
                            event_id=event.event_id,
                            event_seq=event.event_seq,
                            session_id=event.session_id,
                            event_type=event.event_type,
                            payload=event.payload,
                            created_at=event.created_at,
                        )
                    )
                    return
                async with AsyncSessionLocal() as write_session:
                    write_session.add(
                        Event(
                            event_id=event.event_id,
                            event_seq=event.event_seq,
                            session_id=event.session_id,
                            event_type=event.event_type,
                            payload=event.payload,
                            created_at=event.created_at,
                        )
                    )
                    await write_session.commit()
                    return
            except Exception:
                if attempt == 2:
                    return
                await asyncio.sleep(0.1 * (2**attempt))

    if dialect_name == "sqlite":
        await _persist()
    else:
        asyncio.create_task(_persist())
    return event


async def replay_events_by_last_event_id(
    db: AsyncSession, session_id: str, last_event_id: str
) -> list[SessionEventDTO]:
    last_event_stmt = select(Event).where(Event.session_id == session_id, Event.event_id == last_event_id)
    last_event = (await db.execute(last_event_stmt)).scalar_one_or_none()
    if last_event is None:
        return []

    replay_stmt = (
        select(Event)
        .where(Event.session_id == session_id, Event.event_seq > last_event.event_seq)
        .order_by(Event.event_seq.asc())
    )
    replay_rows = (await db.execute(replay_stmt)).scalars().all()
    return [
        SessionEventDTO(
            event_id=row.event_id,
            event_seq=row.event_seq,
            session_id=row.session_id,
            event_type=row.event_type,
            payload=row.payload,
            created_at=row.created_at,
        )
        for row in replay_rows
    ]


def format_sse(event: SessionEventDTO) -> str:
    return f"id: {event.event_id}\ndata: {json.dumps(event.model_dump(mode='json'))}\n\n"
