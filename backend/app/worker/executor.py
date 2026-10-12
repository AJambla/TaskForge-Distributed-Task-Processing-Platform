"""Executor for running task handlers under optional process sandbox and timeouts (IMP-21)."""
from __future__ import annotations

import asyncio
import inspect
import logging
import sys

from app.config import get_settings

logger = logging.getLogger("worker.executor")
_SETTINGS = get_settings()

_TIMEOUT_MAP: dict[str, str] = {
    "email_send": "task_email_timeout_seconds",
    "webhook_delivery": "task_webhook_timeout_seconds",
}


def get_timeout(task_type: str, task_payload: dict | None = None) -> int:
    """Retrieve configured timeout for task type with optional payload override."""
    if task_payload and isinstance(task_payload, dict):
        override = task_payload.get("timeout_seconds") or task_payload.get("timeout")
        if override is not None:
            try:
                val = int(override)
                if val > 0:
                    return val
            except (ValueError, TypeError):
                pass

    from app.worker.handlers import get_handler_metadata
    meta = get_handler_metadata(task_type)
    if meta and "timeout_seconds" in meta:
        return int(meta["timeout_seconds"])

    setting_name = _TIMEOUT_MAP.get(task_type, "task_webhook_timeout_seconds")
    return getattr(_SETTINGS, setting_name, 30)


def run_handler_in_sandbox(handler, payload, ctx=None) -> object:
    """Run a handler in a child process with resource limits (POSIX only).

    On Windows, resource.setrlimit is unavailable — runs the handler directly
    and relies on the asyncio timeout wrapper instead.
    """
    args = (payload, ctx) if ctx is not None else (payload,)

    if sys.platform == "win32" or not _SETTINGS.sandbox_enabled:
        if inspect.iscoroutinefunction(handler):
            return asyncio.run(handler(*args))
        res = handler(*args)
        if inspect.isawaitable(res):
            return asyncio.run(res)
        return res

    import multiprocessing

    def _worker(handler_fn, payload_data, ctx_data, result_queue):
        import resource

        limit_bytes = _SETTINGS.sandbox_memory_limit_mb * 1024 * 1024
        try:
            resource.setrlimit(resource.RLIMIT_AS, (limit_bytes, limit_bytes))
        except (OSError, resource.error):
            logger.warning("Failed to set memory limit — continuing without RSS cap.")
        try:
            resource.setrlimit(
                resource.RLIMIT_CPU,
                (int(_SETTINGS.sandbox_cpu_limit_seconds), int(_SETTINGS.sandbox_cpu_limit_seconds)),
            )
        except (OSError, resource.error):
            logger.warning("Failed to set CPU limit — continuing without CPU cap.")
        try:
            call_args = (payload_data, ctx_data) if ctx_data is not None else (payload_data,)
            if inspect.iscoroutinefunction(handler_fn):
                result = asyncio.run(handler_fn(*call_args))
            else:
                result = handler_fn(*call_args)
                if inspect.isawaitable(result):
                    result = asyncio.run(result)
            result_queue.put(("ok", result))
        except Exception as exc:
            result_queue.put(("error", exc))

    result_queue: multiprocessing.Queue = multiprocessing.Queue()
    process = multiprocessing.Process(
        target=_worker,
        args=(handler, payload, ctx, result_queue),
        daemon=True,
    )
    process.start()
    process.join(timeout=int(_SETTINGS.sandbox_cpu_limit_seconds) + 5)

    if process.is_alive():
        process.terminate()
        process.join(timeout=2)
        raise asyncio.TimeoutError(
            f"Handler exceeded sandbox CPU limit of {_SETTINGS.sandbox_cpu_limit_seconds}s"
        )

    status, result = result_queue.get()
    if status == "error":
        raise result
    return result
