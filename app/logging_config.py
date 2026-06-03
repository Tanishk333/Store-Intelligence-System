import json
import logging
import time
from collections.abc import Callable
from uuid import uuid4

from fastapi import Request, Response


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
        }
        for key in ("trace_id", "store_id", "endpoint", "latency_ms", "status_code"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        return json.dumps(payload, default=str)


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)


logger = logging.getLogger("store_intelligence")


async def request_logging_middleware(request: Request, call_next: Callable) -> Response:
    start = time.perf_counter()
    trace_id = request.headers.get("x-trace-id", str(uuid4()))
    store_id = request.path_params.get("id") or request.query_params.get("store_id")
    try:
        response = await call_next(request)
    except Exception:
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.exception(
            "request_failed",
            extra={
                "trace_id": trace_id,
                "store_id": store_id,
                "endpoint": request.url.path,
                "latency_ms": latency_ms,
                "status_code": 500,
            },
        )
        raise
    latency_ms = round((time.perf_counter() - start) * 1000, 2)
    response.headers["x-trace-id"] = trace_id
    logger.info(
        "request_complete",
        extra={
            "trace_id": trace_id,
            "store_id": store_id,
            "endpoint": request.url.path,
            "latency_ms": latency_ms,
            "status_code": response.status_code,
        },
    )
    return response
