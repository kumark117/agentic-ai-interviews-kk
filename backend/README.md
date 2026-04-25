# Backend Run Modes

Use `AI_INTERVIEW_MODE` to select infrastructure profile:

- `local-lite` -> SQLite + FakeRedis (no Docker/services)
- `local-full` -> local Postgres + local Redis
- `remote` -> managed Postgres + managed Redis

## 1) local-lite (fast debug)

1. Copy `.env.local-lite.example` to `.env`
2. Install deps: `python -m pip install -r requirements.txt`
3. Start API: `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`

Notes:

- SQLite file: `local_dev.db`
- schema auto-created
- cleanup worker disabled by default in this mode

## 2) local-full (real local infra)

1. Install local Postgres + Redis
2. Copy `.env.local-full.example` to `.env` and update passwords if needed
3. Run migrations: `python -m alembic upgrade head`
4. Start API: `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`

## 3) remote (deploy envs)

1. Use `.env.remote.example` as reference in your host (Render/Railway/etc.)
2. Set managed `AI_INTERVIEW_POSTGRES_DSN` and `AI_INTERVIEW_REDIS_DSN`
3. Run migrations on deploy/startup: `python -m alembic upgrade head`

## Optional overrides

You can still override advanced flags directly:

- `AI_INTERVIEW_USE_SQLITE_LOCAL`
- `AI_INTERVIEW_USE_FAKEREDIS_LOCAL`
- `AI_INTERVIEW_AUTO_CREATE_SCHEMA`
- `AI_INTERVIEW_DISABLE_CLEANUP_WORKER`
