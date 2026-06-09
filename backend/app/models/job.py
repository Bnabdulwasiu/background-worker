"""
Database models for the job scheduler.

Three tables:
1. Job - the main jobs table (stores every job and its current state)
2. JobDependency - tracks which jobs depend on which (for DAG workflows)
3. JobLog - event log for every significant thing that happens to a job

These map directly to PostgreSQL tables. SQLAlchemy translates
Python classes into SQL CREATE TABLE statements.
"""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class JobStatus(str, enum.Enum):
    """The lifecycle states a job moves through.
    
    Flow: pending -> processing -> completed / failed / cancelled
    
    Using str + enum.Enum so it serializes nicely to JSON.
    """
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobPriority(int, enum.Enum):
    """Priority levels. Lower number = higher priority.
    
    1 = High (runs first)
    2 = Medium
    3 = Low (runs last, unless starvation prevention kicks in)
    """
    HIGH = 1
    MEDIUM = 2
    LOW = 3


class Job(Base):
    """Main jobs table.
    
    Each row represents one job. The worker reads from this table,
    picks up pending jobs, processes them, and updates the status.
    
    Key columns explained:
    - effective_priority: starts equal to priority, but decreases over time
      (starvation prevention). Lower = more urgent.
    - is_in_dlq: True when a job has failed all retries (Dead Letter Queue)
    - worker_id: which worker is currently processing this job
    - scheduled_at: if set, job won't run until this time passes
    - interval: if set, a new job is auto-created after this one completes
    """
    __tablename__ = "jobs"

    # Primary key - UUID is better than auto-increment for distributed systems
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # What kind of job (e.g., "send_email", "generate_report")
    type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # The actual data the handler needs (e.g., {"to": "user@mail.com"})
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # Base priority: 1=High, 2=Medium, 3=Low
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=2)

    # Effective priority (changes over time due to starvation prevention)
    # Stored as float because it can be fractional (e.g., 2.5)
    effective_priority: Mapped[float] = mapped_column(
        Float, nullable=False, default=2.0
    )

    # Current status in the lifecycle
    status: Mapped[str] = mapped_column(
        Enum(JobStatus, name="job_status", create_constraint=True),
        nullable=False,
        default=JobStatus.PENDING,
        index=True,
    )

    # Retry tracking
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Scheduling
    scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Recurring interval (e.g., "every_1_minute", "every_5_minutes")
    interval: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Dead Letter Queue flag
    is_in_dlq: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Which worker picked up this job (for tracking/debugging)
    worker_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Timestamps for tracking lifecycle
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # When the next retry should happen (backoff scheduling)
    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships - connects this job to its dependencies and logs
    dependencies = relationship(
        "JobDependency",
        foreign_keys="JobDependency.job_id",
        back_populates="job",
        cascade="all, delete-orphan",
    )
    dependents = relationship(
        "JobDependency",
        foreign_keys="JobDependency.depends_on_job_id",
        back_populates="depends_on_job",
    )
    logs = relationship("JobLog", back_populates="job", cascade="all, delete-orphan")

    # Database indexes for common queries
    # These make lookups faster - like an index in a textbook
    __table_args__ = (
        # Worker queries: "give me pending jobs ordered by priority"
        Index("ix_jobs_status_priority", "status", "effective_priority"),
        # Scheduled jobs: "which pending jobs are due now?"
        Index("ix_jobs_scheduled", "status", "scheduled_at"),
    )

    def __repr__(self) -> str:
        return f"<Job {self.id} type={self.type} status={self.status}>"


class JobDependency(Base):
    """Tracks job dependencies for DAG workflows.
    
    If job B depends on job A, there's a row here:
        job_id = B, depends_on_job_id = A
    
    This means B won't run until A has status='completed'.
    
    Example: Generate Report -> Upload File -> Send Email
    Two rows:
        (job_id=upload, depends_on=report)
        (job_id=email,  depends_on=upload)
    """
    __tablename__ = "job_dependencies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # The job that is waiting
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
    )

    # The job it's waiting for
    depends_on_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Relationships back to the Job model
    job = relationship("Job", foreign_keys=[job_id], back_populates="dependencies")
    depends_on_job = relationship(
        "Job", foreign_keys=[depends_on_job_id], back_populates="dependents"
    )

    __table_args__ = (
        # Prevent duplicate dependency entries
        Index("ix_job_deps_unique", "job_id", "depends_on_job_id", unique=True),
    )


class JobLog(Base):
    """Structured event log for jobs.
    
    Every significant event gets a row here:
    - created: job was created
    - started: worker picked it up
    - retry: job failed and will be retried
    - failed: job exhausted all retries
    - completed: job finished successfully
    - cancelled: job was cancelled
    
    This gives us a full audit trail for every job.
    """
    __tablename__ = "job_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Event type (created, started, retry, failed, completed, cancelled)
    event: Mapped[str] = mapped_column(String(50), nullable=False)

    # Human-readable description
    message: Mapped[str] = mapped_column(Text, nullable=False)

    # Extra context (e.g., error traceback, retry count)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationship back to Job
    job = relationship("Job", back_populates="logs")

    def __repr__(self) -> str:
        return f"<JobLog {self.event} for job {self.job_id}>"
