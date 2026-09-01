from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from app.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.rabbitmq import get_publisher
from app.core.redis import get_redis
from app.database import engine
from app.routers import api_keys, auth, queues, tasks, workers

settings = get_settings()


async def _check_db() -> tuple[bool, str]:
    try:
        from sqlalchemy import text
        from sqlalchemy.exc import SQLAlchemyError
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        return True, "ok"
    except SQLAlchemyError as exc:
        return False, str(exc)


async def _check_redis() -> tuple[bool, str]:
    try:
        import redis.exceptions
        client = await get_redis()
        await client.ping()
        return True, "ok"
    except (redis.exceptions.ConnectionError, OSError) as exc:
        return False, str(exc)


async def _check_rabbitmq() -> tuple[bool, str]:
    try:
        import aio_pika.exceptions
        publisher = await get_publisher()
        if publisher._connection is None or publisher._connection.is_closed:
            return False, "connection is closed"
        return True, "ok"
    except (aio_pika.exceptions.AmqpError, OSError) as exc:
        return False, str(exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    from app.database import engine
    await engine.dispose()

app = FastAPI(
    title="TaskForge",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.app_env == "development" else None,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exception handlers
register_exception_handlers(app)

# Custom Prometheus metrics endpoint for Prometheus scrape config
@app.get("/api/v1/metrics")
async def metrics_endpoint():
    from prometheus_client import generate_latest
    from starlette.responses import Response
    return Response(generate_latest(), media_type="text/plain; charset=utf-8")

# Routers
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(api_keys.router, prefix="/api/v1/api-keys", tags=["api-keys"])
app.include_router(tasks.router, prefix="/api/v1/tasks", tags=["tasks"])
app.include_router(workers.router, prefix="/api/v1/workers", tags=["workers"])
app.include_router(queues.router, prefix="/api/v1/queues", tags=["queues"])

# Prometheus instrumentator — exclude healthz and the custom metrics endpoint
Instrumentator(
    should_group_status_codes=True,
    should_instrument_requests_inprogress=True,
    excluded_handlers=["/healthz", "/api/v1/metrics"],
).instrument(app)


@app.get("/healthz", tags=["system"])
async def healthz():
    db_ok, db_msg = await _check_db()
    redis_ok, redis_msg = await _check_redis()
    rabbitmq_ok, rabbitmq_msg = await _check_rabbitmq()

    all_ok = db_ok and redis_ok and rabbitmq_ok

    components = {
        "database": {"status": "ok" if db_ok else "error", "detail": db_msg},
        "redis": {"status": "ok" if redis_ok else "error", "detail": redis_msg},
        "rabbitmq": {"status": "ok" if rabbitmq_ok else "error", "detail": rabbitmq_msg},
    }

    if all_ok:
        return {"status": "ok", "components": components}

    return {"status": "error", "components": components}, 503
