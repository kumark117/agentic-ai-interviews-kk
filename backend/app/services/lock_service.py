import asyncio
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from redis.asyncio import Redis

from app.core.config import settings


def session_lock_key(session_id: str) -> str:
    return f"session:{session_id}:lock"


class SessionBusyError(Exception):
    pass


@asynccontextmanager
async def acquire_session_lock(redis: Redis, session_id: str) -> AsyncIterator[str]:
    token = str(uuid.uuid4())
    key = session_lock_key(session_id)
    start = time.monotonic()
    delay = 0.15
    attempts = 0
    while attempts < settings.lock_retry_attempts and (time.monotonic() - start) <= settings.lock_wait_budget_seconds:
        if await redis.set(key, token, nx=True, ex=settings.lock_ttl_seconds):
            try:
                yield token
            finally:
                if await redis.get(key) == token:
                    await redis.delete(key)
            return
        attempts += 1
        await asyncio.sleep(delay)
        delay *= 2
    raise SessionBusyError("session_busy")


async def start_lock_heartbeat(redis: Redis, session_id: str, token: str) -> asyncio.Task:
    key = session_lock_key(session_id)

    async def _heartbeat() -> None:
        while True:
            await asyncio.sleep(settings.lock_heartbeat_seconds)
            if await redis.get(key) != token:
                return
            await redis.expire(key, settings.lock_ttl_seconds)

    return asyncio.create_task(_heartbeat())
