"""
Standard human-readable logging configuration.

Server logs use a simple format:
  2026-06-10 14:43:16 - INFO - app.main - Message

Worker/handler logs include structured extra fields:
  2026-06-10 14:43:16 - INFO - app.worker - Message | job_id=abc123 event=job_started
"""

import logging
import sys


# Reserved keys that the logging module uses internally — don't print these.
_RESERVED_ATTRS = {
    "name", "msg", "args", "created", "relativeCreated", "exc_info",
    "exc_text", "stack_info", "lineno", "funcName", "pathname", "filename",
    "module", "levelno", "levelname", "message", "msecs", "thread",
    "threadName", "process", "processName", "taskName",
}


class WorkerFormatter(logging.Formatter):
    """Formatter that appends extra={} fields to the log line.
    
    Output: 2026-06-10 14:43:16 - INFO - app.worker - Job started | job_id=abc event=job_started
    """

    def format(self, record):
        base = super().format(record)

        # Collect non-reserved extra fields
        extras = {
            k: v for k, v in record.__dict__.items()
            if k not in _RESERVED_ATTRS and not k.startswith("_")
        }

        if extras:
            parts = " ".join(f"{k}={v}" for k, v in extras.items())
            return f"{base} | {parts}"
        return base


def setup_logging(level: str = "INFO") -> None:
    """Configure standard human-readable logging for the entire application.
    
    Call this once at startup (in main.py and run_worker.py).
    """
    # Standard format for server logs
    server_formatter = logging.Formatter(
        fmt="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Worker formatter that includes extra fields
    worker_formatter = WorkerFormatter(
        fmt="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Stdout handler with standard formatting (default)
    server_handler = logging.StreamHandler(sys.stdout)
    server_handler.setFormatter(server_formatter)

    # Configure the root logger (covers server, uvicorn, sqlalchemy, etc.)
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))
    root_logger.handlers.clear()
    root_logger.addHandler(server_handler)

    # Worker and handler loggers get the extra-aware formatter
    worker_handler = logging.StreamHandler(sys.stdout)
    worker_handler.setFormatter(worker_formatter)

    for logger_name in ("app.worker.worker", "app.worker.handlers", "app.services.job_service"):
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.addHandler(worker_handler)
        logger.propagate = False  # Don't double-log via root

    # Configure uvicorn and sqlalchemy levels
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the given name."""
    return logging.getLogger(name)
