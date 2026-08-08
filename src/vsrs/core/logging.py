"""Structured JSON logging with run IDs for traceability."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path


class JSONFormatter(logging.Formatter):
    """Format log records as structured JSON lines."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "run_id"):
            log_entry["run_id"] = record.run_id
        if hasattr(record, "task_id"):
            log_entry["task_id"] = record.task_id
        if hasattr(record, "attempt_no"):
            log_entry["attempt_no"] = record.attempt_no
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry)


def setup_logging(
    level: str = "INFO",
    log_dir: Path | None = None,
    run_id: str | None = None,
) -> logging.Logger:
    """Configure structured JSON logging.

    Args:
        level: Log level string (DEBUG, INFO, WARNING, ERROR).
        log_dir: Directory for log files. If None, logs to stderr only.
        run_id: Optional run ID to include in all log records.

    Returns:
        Configured root logger for vsrs.
    """
    logger = logging.getLogger("vsrs")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.handlers.clear()

    formatter = JSONFormatter()

    # Console handler (stderr)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{run_id}.log" if run_id else "vsrs.log"
        file_handler = logging.FileHandler(log_dir / filename)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def get_logger(name: str = "vsrs") -> logging.Logger:
    """Get a child logger under the vsrs namespace."""
    return logging.getLogger(f"vsrs.{name}")
