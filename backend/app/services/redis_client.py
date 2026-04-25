from redis.asyncio import Redis

from app.core.config import settings

if settings.effective_use_fakeredis_local:
    from fakeredis.aioredis import FakeRedis

    redis_client = FakeRedis(decode_responses=True)
else:
    redis_client = Redis.from_url(settings.redis_dsn, decode_responses=True)
