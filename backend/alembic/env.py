"""
Alembic environment configuration.

This file tells Alembic:
1. How to connect to the database (using our app's settings)
2. Which models to track (so it can auto-detect schema changes)
3. Whether to run migrations synchronously or asynchronously

You rarely need to touch this file after initial setup.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.config import settings
from app.database import Base

# Import all models so Alembic can see them
# Without this import, Alembic won't know about our tables
from app.models.job import Job, JobDependency, JobLog  # noqa: F401

# Alembic Config object - provides access to alembic.ini values
config = context.config

# Override the database URL from alembic.ini with our app settings
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# Set up Python logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# This is the metadata that contains all our table definitions
# Alembic compares this against the actual database to detect changes
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.
    
    Generates SQL scripts without connecting to the database.
    Useful for reviewing what changes will be made.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Actually run the migration scripts against the database."""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations using an async connection.
    
    Since we use asyncpg (async PostgreSQL driver), we need
    to run migrations asynchronously too.
    """
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (connected to database)."""
    asyncio.run(run_async_migrations())


# Decide which mode to run based on context
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
