import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator

import logging

from app.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.core.rabbitmq import get_publisher
from app.core.redis import get_redis
from app.database import engine
from app.routers import api_keys, auth, metrics, queues, tasks, workers

settings = get_settings()
configure_logging(
    service_name="api",
    log_level=settings.log_level,
    json_format=(settings.log_format == "json"),
)
cors_origins_list = [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]


async def _check_db() -> tuple[bool, str]:
    try:
        from sqlalchemy import text
        from sqlalchemy.exc import SQLAlchemyError
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        return True, "ok"
    except (SQLAlchemyError, OSError, Exception) as exc:
        return False, str(exc)


async def _check_redis() -> tuple[bool, str]:
    try:
        import redis.exceptions
        client = await get_redis()
        await client.ping()
        return True, "ok"
    except (redis.exceptions.RedisError, OSError, Exception) as exc:
        return False, str(exc)


async def _check_rabbitmq() -> tuple[bool, str]:
    try:
        import aio_pika.exceptions
        publisher = await get_publisher()
        if publisher.connection is None or publisher.connection.is_closed:
            return False, "connection is closed"
        return True, "ok"
    except (aio_pika.exceptions.AmqpError, OSError) as exc:
        return False, str(exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    relay_task = None
    if settings.outbox_relay_enabled:
        from app.outbox.relay import OutboxRelayService
        relay_service = OutboxRelayService()
        relay_task = asyncio.create_task(relay_service.start())
        logging.getLogger("api").info("Spawned in-process OutboxRelayService.")
    try:
        yield
    finally:
        if relay_task:
            relay_task.cancel()
            try:
                await relay_task
            except asyncio.CancelledError:
                pass
        from app.database import engine
        await engine.dispose()

app = FastAPI(
    title="TaskForge",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.app_env == "development" else None,
)

@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if settings.app_env == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# OpenTelemetry Instrumentation (FEAT-03)
if settings.otel_enabled:
    from app.core.tracing import init_tracer
    init_tracer(
        service_name=settings.otel_service_name,
        otlp_endpoint=settings.otel_exporter_otlp_endpoint,
    )
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument_app(app)
    except Exception as otel_err:
        logging.getLogger("api").warning("FastAPI OTel instrumentation skipped: %s", otel_err)
    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
    except Exception as sql_err:
        logging.getLogger("api").warning("SQLAlchemy OTel instrumentation skipped: %s", sql_err)

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
app.include_router(metrics.router, prefix="/api/v1/metrics", tags=["metrics"])


@app.get("/api/v1/handlers", tags=["tasks"], summary="List registered handlers")
async def get_handlers_root():
    from app.worker.handlers import list_handlers
    return {"handlers": list_handlers()}


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

    return JSONResponse(status_code=503, content={"status": "error", "components": components})
