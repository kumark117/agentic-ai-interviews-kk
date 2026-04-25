import asyncio
import os

import pytest
from fakeredis.aioredis import FakeRedis
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.v1 import routes as routes_module
from agents.streamer import event_service
from app.db.base import get_db_session
from app.main import app
from app.models.models import Base

TEST_DB_URL = "sqlite+aiosqlite:///./test_ai_agentic_interview.db"


@pytest.fixture()
def client():
    os.environ["AI_DISABLE_CLEANUP_WORKER"] = "1"
    engine = create_async_engine(TEST_DB_URL, future=True)
    session_local = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
    fake_redis = FakeRedis(decode_responses=True)

    async def setup_db() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(setup_db())

    async def override_db():
        async with session_local() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db
    routes_module.redis_client = fake_redis
    event_service.AsyncSessionLocal = session_local

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()

    async def teardown() -> None:
        await fake_redis.aclose()
        await engine.dispose()

    asyncio.run(teardown())
