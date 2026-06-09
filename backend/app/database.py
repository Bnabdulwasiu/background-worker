"""
Database connection setup.

This creates the async engine (the connection to PostgreSQL) and the
session factory (how we create individual database "conversations").

Key concepts:
- Engine: manages the actual connection pool to the database
- Session: a single unit of work (open, do queries, commit/rollback, close)
- get_db(): a FastAPI dependency that gives each request its own session
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# Create the async engine
# - echo=False: don't print every SQL query (set True for debugging)
# - pool_size=20: keep 20 connections ready
# - max_overflow=10: allow up to 10 extra connections under heavy load
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_size=20,
    max_overflow=10,
)

# Session factory - creates new database sessions
# - expire_on_commit=False: objects stay usable after commit
#   (without this, accessing an attribute after commit would fail)
async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Base class for all database models.
    
    Every model (Job, JobDependency, JobLog) inherits from this.
    SQLAlchemy uses this to know which tables to create.
    """
    pass


async def get_db():
    """FastAPI dependency that provides a database session.
    
    Usage in an endpoint:
        @app.get("/jobs")
        async def list_jobs(db: AsyncSession = Depends(get_db)):
            ...
    
    The session is automatically closed when the request finishes,
    even if an error occurs (that's what the finally block does).
    """
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()
