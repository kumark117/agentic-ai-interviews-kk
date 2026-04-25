import asyncio
import os
from contextlib import asynccontextmanager
from contextlib import suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.routes import router as v1_router
from app.core.config import settings
from app.db.base import engine, init_db_schema
from app.services.cleanup_worker import cleanup_inactive_sessions
from app.services.redis_client import redis_client


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.effective_auto_create_schema:
        await init_db_schema()

    disable_cleanup = settings.effective_disable_cleanup_worker or os.getenv("AI_DISABLE_CLEANUP_WORKER", "0") == "1"
    cleanup_task: asyncio.Task | None = None
    if not disable_cleanup:
        cleanup_task = asyncio.create_task(cleanup_inactive_sessions())

    try:
        yield
    finally:
        if cleanup_task is not None:
            cleanup_task.cancel()
            with suppress(asyncio.CancelledError):
                await cleanup_task
        await redis_client.aclose()
        await engine.dispose()


app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(v1_router, prefix=settings.api_prefix)
