"""
Job service — business logic for creating and managing jobs.

This sits between the API endpoints and the database.
Endpoints call service functions, service functions talk to the DB.

Why a separate layer?
- Keeps endpoint code clean (just handle HTTP, delegate to service)
- Business logic is reusable (worker also uses some of these)
- Easier to test
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.logging_config import get_logger
from app.models.job import Job, JobDependency, JobLog, JobStatus

logger = get_logger(__name__)


async def create_job(
    session: AsyncSession,
    job_type: str,
    priority: int = 2,
    payload: dict | None = None,
    scheduled_at: datetime | None = None,
    interval: str | None = None,
    depends_on: list[uuid.UUID] | None = None,
) -> Job:
    """Create a new job and save it to the database.
    
    Also creates dependency records if depends_on is provided.
    """
    job = Job(
        type=job_type,
        priority=priority,
        effective_priority=float(priority),
        payload=payload or {},
        scheduled_at=scheduled_at,
        interval=interval,
    )
    
    session.add(job)
    await session.flush()  # Get the job.id without committing
    
    # Create dependency records (for DAG workflows)
    if depends_on:
        for dep_id in depends_on:
            # Verify the dependency job exists
            dep_job = await session.get(Job, dep_id)
            if dep_job is None:
                raise ValueError(f"Dependency job {dep_id} does not exist")
            
            dep = JobDependency(
                job_id=job.id,
                depends_on_job_id=dep_id,
            )
            session.add(dep)
    
    # Log the creation event
    log_entry = JobLog(
        job_id=job.id,
        event="created",
        message=f"Job '{job_type}' created with priority {priority}",
        details={
            "priority": priority,
            "scheduled_at": scheduled_at.isoformat() if scheduled_at else None,
            "interval": interval,
            "depends_on": [str(d) for d in (depends_on or [])],
        },
    )
    session.add(log_entry)
    
    await session.commit()
    await session.refresh(job)
    
    logger.info("Job created", extra={
        "job_id": str(job.id),
        "job_type": job_type,
        "priority": priority,
        "event": "job_created",
    })
    
    return job


async def get_job(session: AsyncSession, job_id: uuid.UUID) -> Job | None:
    """Get a single job by ID."""
    return await session.get(Job, job_id)


async def list_jobs(
    session: AsyncSession,
    status: str | None = None,
    job_type: str | None = None,
    priority: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Job], int]:
    """List jobs with optional filters and pagination.
    
    Returns (jobs, total_count).
    """
    # Build base query
    conditions = []
    if status:
        conditions.append(Job.status == status)
    if job_type:
        conditions.append(Job.type == job_type)
    if priority:
        conditions.append(Job.priority == priority)
    
    # Count query
    count_stmt = select(func.count()).select_from(Job)
    if conditions:
        count_stmt = count_stmt.where(and_(*conditions))
    count_result = await session.execute(count_stmt)
    total = count_result.scalar() or 0
    
    # Data query
    stmt = select(Job)
    if conditions:
        stmt = stmt.where(and_(*conditions))
    stmt = stmt.order_by(Job.created_at.desc()).limit(limit).offset(offset)
    
    result = await session.execute(stmt)
    jobs = result.scalars().all()
    
    return list(jobs), total


async def cancel_job(session: AsyncSession, job_id: uuid.UUID) -> Job | None:
    """Cancel a job.
    
    Only pending and processing jobs can be cancelled.
    For processing jobs: we set the status to cancelled. The worker
    checks this after finishing and discards the result (graceful cancellation).
    """
    job = await session.get(Job, job_id)
    if job is None:
        return None
    
    if job.status not in (JobStatus.PENDING, JobStatus.PROCESSING):
        raise ValueError(
            f"Cannot cancel job with status '{job.status}'. "
            f"Only 'pending' and 'processing' jobs can be cancelled."
        )
    
    prev_status = job.status
    job.status = JobStatus.CANCELLED
    job.updated_at = datetime.now(timezone.utc)
    
    log_entry = JobLog(
        job_id=job.id,
        event="cancelled",
        message=f"Job cancelled (was {prev_status})",
        details={"previous_status": str(prev_status)},
    )
    session.add(log_entry)
    
    await session.commit()
    await session.refresh(job)
    
    logger.info("Job cancelled", extra={
        "job_id": str(job.id),
        "event": "job_cancelled",
    })
    
    return job


async def get_job_logs(
    session: AsyncSession, job_id: uuid.UUID
) -> list[JobLog]:
    """Get all log entries for a specific job."""
    stmt = (
        select(JobLog)
        .where(JobLog.job_id == job_id)
        .order_by(JobLog.created_at.asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_dashboard_stats(session: AsyncSession) -> dict:
    """Get job counts grouped by status for the dashboard."""
    stmt = (
        select(Job.status, func.count())
        .group_by(Job.status)
    )
    result = await session.execute(stmt)
    counts = {row[0]: row[1] for row in result.all()}
    
    # DLQ count
    dlq_stmt = select(func.count()).select_from(Job).where(Job.is_in_dlq == True)
    dlq_result = await session.execute(dlq_stmt)
    dlq_count = dlq_result.scalar() or 0
    
    total = sum(counts.values())
    
    return {
        "pending": counts.get(JobStatus.PENDING, 0),
        "processing": counts.get(JobStatus.PROCESSING, 0),
        "completed": counts.get(JobStatus.COMPLETED, 0),
        "failed": counts.get(JobStatus.FAILED, 0),
        "cancelled": counts.get(JobStatus.CANCELLED, 0),
        "dlq_count": dlq_count,
        "total": total,
    }


async def get_dlq_jobs(session: AsyncSession) -> list[Job]:
    """Get all jobs in the Dead Letter Queue."""
    stmt = (
        select(Job)
        .where(Job.is_in_dlq == True)
        .order_by(Job.updated_at.desc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def retry_dlq_job(
    session: AsyncSession, job_id: uuid.UUID, new_payload: dict | None = None
) -> Job | None:
    """Manually retry a job from the DLQ.
    
    Resets the job to pending with retry_count=0 and removes it from DLQ.
    If it fails again, it goes back to the DLQ.
    """
    job = await session.get(Job, job_id)
    if job is None:
        return None
    
    if not job.is_in_dlq:
        raise ValueError("Job is not in the Dead Letter Queue")
    
    old_payload = job.payload
    has_payload_changed = new_payload is not None and new_payload != old_payload
    
    if has_payload_changed:
        job.payload = new_payload

    job.status = JobStatus.PENDING
    job.is_in_dlq = False
    job.retry_count = 0
    job.error_message = None
    job.worker_id = None
    job.started_at = None
    job.completed_at = None
    job.next_retry_at = None
    job.updated_at = datetime.now(timezone.utc)
    
    details = {"source": "dlq_manual_retry"}
    if has_payload_changed:
        details["old_payload"] = old_payload
        details["new_payload"] = new_payload
        message = "Manual retry from DLQ — payload updated and retry count reset to 0"
    else:
        message = "Manual retry from DLQ — retry count reset to 0"

    log_entry = JobLog(
        job_id=job.id,
        event="retry",
        message=message,
        details=details,
    )
    session.add(log_entry)
    
    await session.commit()
    await session.refresh(job)
    
    logger.info("DLQ job manually retried", extra={
        "job_id": str(job.id),
        "event": "dlq_retry",
        "payload_changed": has_payload_changed,
    })
    
    return job


async def create_workflow(
    session: AsyncSession,
    jobs_data: list[dict],
) -> list[Job]:
    """Create a DAG workflow — multiple jobs with dependencies.
    
    jobs_data is a list of dicts, each with:
    - type, priority, payload, scheduled_at, interval
    - depends_on_index: list of indices into this same array
    
    Example:
    [
        {"type": "generate_report", ...},
        {"type": "upload_file", ..., "depends_on_index": [0]},
        {"type": "send_email", ..., "depends_on_index": [1]},
    ]
    """
    created_jobs: list[Job] = []
    
    # First pass: create all jobs
    for job_data in jobs_data:
        job = Job(
            type=job_data["type"],
            priority=job_data.get("priority", 2),
            effective_priority=float(job_data.get("priority", 2)),
            payload=job_data.get("payload", {}),
            scheduled_at=job_data.get("scheduled_at"),
            interval=job_data.get("interval"),
        )
        session.add(job)
        await session.flush()
        created_jobs.append(job)
    
    # Second pass: create dependencies based on indices
    for i, job_data in enumerate(jobs_data):
        dep_indices = job_data.get("depends_on_index", [])
        for dep_idx in dep_indices:
            if dep_idx < 0 or dep_idx >= len(created_jobs):
                raise ValueError(f"Invalid dependency index {dep_idx} for job at index {i}")
            if dep_idx >= i:
                raise ValueError(
                    f"Job at index {i} depends on job at index {dep_idx} "
                    f"which comes after it — this creates a cycle"
                )
            
            dep = JobDependency(
                job_id=created_jobs[i].id,
                depends_on_job_id=created_jobs[dep_idx].id,
            )
            session.add(dep)
    
    # Create log entries
    for job in created_jobs:
        log_entry = JobLog(
            job_id=job.id,
            event="created",
            message=f"Job '{job.type}' created as part of workflow",
            details={"workflow": True},
        )
        session.add(log_entry)
    
    await session.commit()
    
    # Refresh all jobs
    for job in created_jobs:
        await session.refresh(job)
    
    logger.info("Workflow created", extra={
        "job_count": len(created_jobs),
        "job_ids": [str(j.id) for j in created_jobs],
        "event": "workflow_created",
    })
    
    return created_jobs
