import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, select

from agents.streamer.event_service import publish_event
from app.db.base import AsyncSessionLocal
from app.models.models import EndReason, EventType, Session, SessionStatus
from app.services.redis_client import redis_client

logger = logging.getLogger(__name__)


async def cleanup_inactive_sessions(poll_seconds: int = 30) -> None:
    while True:
        try:
            async with AsyncSessionLocal() as db:
                cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
                inactive_sessions = (
                    await db.execute(
                        select(Session).where(and_(Session.status != SessionStatus.END, Session.last_activity_at < cutoff))
                    )
                ).scalars().all()
                for session in inactive_sessions:
                    session.status = SessionStatus.END
                    session.end_reason = EndReason.inactive_timeout
                    session.updated_at = datetime.now(timezone.utc)
                    await publish_event(
                        db, redis_client, session.session_id, EventType.interview_completed, {"end_reason": EndReason.inactive_timeout.value}
                    )
                await db.commit()
        except Exception:
            logger.exception("Cleanup worker iteration failed.")
        await asyncio.sleep(poll_seconds)
