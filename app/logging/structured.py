from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any


class StructuredFormatter(logging.Formatter):
    """JSON structured log formatter."""

    def format(self, record: logging.LogRecord) -> str:
        log_data: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if record.exc_info and record.exc_info[0]:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
            }

        extra_fields = {
            k: v
            for k, v in record.__dict__.items()
            if k not in logging.LogRecord("", 0, "", 0, "", (), None).__dict__
            and k not in ("message", "msg", "args", "exc_info", "exc_text", "stack_info",
                          "name", "levelname", "levelno", "pathname", "filename",
                          "module", "funcName", "lineno", "asctime", "msecs",
                          "relativeCreated", "thread", "threadName", "processName",
                          "process", "created")
        }
        if extra_fields:
            log_data["extra"] = extra_fields

        return json.dumps(log_data, ensure_ascii=False, default=str)


def setup_structured_logging(level: str = "INFO") -> None:
    """Configure structured JSON logging."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredFormatter())

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        logging.getLogger(name).handlers.clear()
        logging.getLogger(name).addHandler(handler)

    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance."""
    return logging.getLogger(name)
