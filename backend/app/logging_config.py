"""
Structured JSON logging configuration.

Instead of: print("job done")
We get:     {"timestamp": "2026-06-09T10:00:00Z", "level": "INFO", "event": "job_completed", ...}

This satisfies the task requirement:
"Structured format only. console.log('done') is not logging."

Uses Python's built-in logging module with a JSON formatter.
"""

import logging
import sys
from datetime import datetime, timezone

from pythonjsonlogger import json as json_logger


def setup_logging(level: str = "INFO") -> None:
    """Configure structured JSON logging for the entire application.
    
    Call this once at startup (in main.py and run_worker.py).
    After this, any code doing:
        logger = logging.getLogger(__name__)
        logger.info("something happened", extra={"job_id": "abc"})
    
    Will output:
        {"timestamp": "...", "level": "INFO", "message": "something happened", "job_id": "abc"}
    """

    class CustomJsonFormatter(json_logger.JsonFormatter):
        """Custom formatter that adds timestamp and level to every log."""

        def add_fields(self, log_record, record, message_dict):
            super().add_fields(log_record, record, message_dict)
            # Add ISO format timestamp
            log_record["timestamp"] = datetime.now(timezone.utc).isoformat()
            # Add log level
            log_record["level"] = record.levelname
            # Add the module/file that produced this log
            log_record["logger"] = record.name

    # Create the formatter
    formatter = CustomJsonFormatter(
        fmt="%(timestamp)s %(level)s %(name)s %(message)s"
    )

    # Set up the handler (where logs go - stdout in our case)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    # Configure the root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))
    # Remove any existing handlers to avoid duplicate logs
    root_logger.handlers.clear()
    root_logger.addHandler(handler)

    # Quiet down noisy libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the given name.
    
    Usage:
        from app.logging_config import get_logger
        logger = get_logger(__name__)
        
        logger.info("Job created", extra={"job_id": str(job.id), "job_type": job.type})
    """
    return logging.getLogger(name)
