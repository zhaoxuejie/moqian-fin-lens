from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

from core.context import current_request_id


class JsonFormatter(logging.Formatter):
    """单行 JSON 日志：便于采集，且天然带 request_id。"""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "request_id": current_request_id(),
            "event": record.getMessage(),
        }
        extra = getattr(record, "extra_fields", None)
        if isinstance(extra, dict):
            payload.update(extra)
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(level: str = "info") -> logging.Logger:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass

    logger = logging.getLogger("finance_agent")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.propagate = False

    # uvicorn 自带的 access / error 日志也统一成单行 JSON，避免混入非结构化文本
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        third_party = logging.getLogger(name)
        third_party.handlers.clear()
        third_party.addHandler(handler)
        third_party.propagate = False
        third_party.setLevel(getattr(logging, level.upper(), logging.INFO))

    return logger


def get_logger(name: str = "finance_agent") -> logging.Logger:
    return logging.getLogger(name)


def log_event(logger: logging.Logger, level: int, event: str, **fields: Any) -> None:
    logger.log(level, event, extra={"extra_fields": fields})
