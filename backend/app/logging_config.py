"""
Standard human-readable logging configuration.
"""

import logging
import sys


def setup_logging(level: str = "INFO") -> None:
    """Configure standard human-readable logging for the entire application.
    
    Call this once at startup (in main.py and run_worker.py).
    """
    # Standard format: 2026-06-10 14:43:16 - INFO - app.main - Message
    formatter = logging.Formatter(
        fmt="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Set up the handler (stdout)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    # Configure the root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))
    # Remove any existing handlers to avoid duplicate logs
    root_logger.handlers.clear()
    root_logger.addHandler(handler)

    # Configure uvicorn and sqlalchemy levels
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the given name."""
    return logging.getLogger(name)
