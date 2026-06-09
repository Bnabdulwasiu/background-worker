"""
Application configuration.

All settings are loaded from environment variables with sensible defaults.
This uses pydantic-settings which automatically reads from a .env file.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Central configuration for the entire application."""

    # Database connection string
    # Format: postgresql+asyncpg://user:password@host:port/dbname
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/scheduler_db"

    # Dead-Letter Queue: alert when this many jobs are in the DLQ
    DLQ_THRESHOLD: int = 10

    # Starvation prevention: boost priority by 1 level every N seconds
    STARVATION_BOOST_INTERVAL: int = 60

    # Maximum retry attempts before a job goes to DLQ
    MAX_RETRIES: int = 3

    # How often (seconds) the worker checks for new jobs
    WORKER_POLL_INTERVAL: float = 2.0

    # How often (seconds) the SSE endpoint checks for updates
    SSE_POLL_INTERVAL: float = 1.0

    # Email handler: probability of simulated failure (0.0 to 1.0)
    # Set to 0.2 = 20% failure rate for testing retries
    FAILURE_RATE: float = 0.2

    # CORS: frontend URL
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # App metadata
    APP_NAME: str = "Background Job Scheduler"
    APP_VERSION: str = "1.0.0"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Single instance used throughout the app
settings = Settings()
