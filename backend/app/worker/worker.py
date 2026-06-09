"""
Background Worker Process.

This runs INDEPENDENTLY from the FastAPI API server.
It polls the database for pending jobs, processes them, and updates statuses.

The worker loop:
1. Query DB for ready jobs (pending, scheduled time passed, dependencies met)
2. Lock the job row (SELECT ... FOR UPDATE SKIP LOCKED) to prevent duplicates
3. Load the job into the heap scheduler
4. Pop the most urgent job from the heap
5. Execute the handler (e.g., send_email)
6. On success: mark completed, handle recurring jobs
7. On failure: increment retry, apply backoff, or send to DLQ
8. Log every event
9. Repeat

DUPLICATE PROTECTION:
  SELECT ... FOR UPDATE SKIP LOCKED
  - FOR UPDATE: locks the selected rows so no other worker can grab them
  - SKIP LOCKED: if a row is already locked, skip it instead of waiting
  This guarantees one job is never processed by two workers simultaneously.

GRACEFUL CANCELLATION:
  If a job is cancelled while processing, we let it finish, then mark
  it as cancelled instead of completed. We check the status AFTER processing.
"""

import asyncio
import random
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session
from app.logging_config import get_logger
from app.models.job import Job, JobDependency, JobLog, JobStatus
from app.scheduler.heap_scheduler import HeapScheduler
from app.worker.handlers import execute_handler, JobProcessingError

logger = get_logger(__name__)


class Worker:
    """Background job processing worker.
    
    Each worker instance has a unique ID and runs its own polling loop.
    Multiple workers can run simultaneously — duplicate protection is
    handled at the database level with row locking.
    """

    def __init__(self, worker_id: str | None = None):
        self.worker_id = worker_id or f"worker-{uuid.uuid4().hex[:8]}"
        self.scheduler = HeapScheduler(
            starvation_boost_interval=settings.STARVATION_BOOST_INTERVAL
        )
        self._running = False
        self._jobs_processed = 0
        self._jobs_failed = 0

    async def start(self) -> None:
        """Start the worker polling loop.
        
        This runs forever until stop() is called or the process is killed.
        """
        self._running = True
        logger.info("Worker starting", extra={
            "worker_id": self.worker_id,
            "poll_interval": settings.WORKER_POLL_INTERVAL,
            "event": "worker_started",
        })

        while self._running:
            try:
                # Poll for and process one batch of jobs
                processed = await self._poll_and_process()
                
                if not processed:
                    # No jobs found — wait before polling again
                    await asyncio.sleep(settings.WORKER_POLL_INTERVAL)
                    
            except Exception as e:
                # Don't crash the worker on unexpected errors
                logger.error("Worker encountered unexpected error", extra={
                    "worker_id": self.worker_id,
                    "error": str(e),
                    "event": "worker_error",
                })
                await asyncio.sleep(settings.WORKER_POLL_INTERVAL)

    def stop(self) -> None:
        """Signal the worker to stop after the current job finishes."""
        self._running = False
        logger.info("Worker stopping", extra={
            "worker_id": self.worker_id,
            "jobs_processed": self._jobs_processed,
            "jobs_failed": self._jobs_failed,
            "event": "worker_stopped",
        })

    async def _poll_and_process(self) -> bool:
        """Poll for ready jobs and process the most urgent one.
        
        Returns True if a job was processed, False if none were found.
        """
        async with async_session() as session:
            # Step 1: Find and lock a ready job
            job = await self._fetch_next_job(session)
            
            if job is None:
                return False
            
            # Step 2: Process the job
            await self._process_job(session, job)
            return True

    async def _fetch_next_job(self, session: AsyncSession) -> Job | None:
        """Fetch the next ready job from the database with row locking.
        
        A job is "ready" when ALL of these are true:
        1. status = 'pending'
        2. scheduled_at is NULL or <= now (time has come)
        3. next_retry_at is NULL or <= now (retry backoff has passed)
        4. All dependencies are completed (DAG check)
        
        The SELECT ... FOR UPDATE SKIP LOCKED ensures:
        - Only ONE worker can grab this job (FOR UPDATE = lock the row)
        - If another worker already locked it, skip it (SKIP LOCKED)
        """
        now = datetime.now(timezone.utc)
        
        # Query for pending jobs that are ready to run
        stmt = (
            select(Job)
            .where(
                and_(
                    Job.status == JobStatus.PENDING,
                    # Either no scheduled time, or the time has passed
                    (Job.scheduled_at.is_(None)) | (Job.scheduled_at <= now),
                    # Either no retry delay, or the delay has passed
                    (Job.next_retry_at.is_(None)) | (Job.next_retry_at <= now),
                )
            )
            .order_by(Job.effective_priority.asc(), Job.scheduled_at.asc(), Job.created_at.asc())
            .limit(10)  # Fetch a small batch to put into our heap
            .with_for_update(skip_locked=True)  # DUPLICATE PROTECTION
        )
        
        result = await session.execute(stmt)
        candidate_jobs = result.scalars().all()
        
        if not candidate_jobs:
            return None
        
        # Filter out jobs whose dependencies haven't completed
        ready_jobs = []
        for job in candidate_jobs:
            if await self._are_dependencies_met(session, job.id):
                ready_jobs.append(job)
        
        if not ready_jobs:
            return None
        
        # Load ready jobs into the heap scheduler for priority ordering
        self.scheduler.clear()
        for job in ready_jobs:
            self.scheduler.push(
                job_id=job.id,
                priority=job.priority,
                scheduled_at=job.scheduled_at,
                created_at=job.created_at,
            )
        
        # Refresh priorities (applies starvation boost)
        self.scheduler.refresh_priorities()
        
        # Pop the most urgent job
        best_job_id = self.scheduler.pop()
        if best_job_id is None:
            return None
        
        # Find the job object that matches
        for job in ready_jobs:
            if job.id == best_job_id:
                return job
        
        return None

    async def _are_dependencies_met(self, session: AsyncSession, job_id: uuid.UUID) -> bool:
        """Check if ALL dependencies of a job have completed.
        
        Returns True if the job has no dependencies or all are completed.
        Returns False if any dependency is not yet completed.
        """
        # Get all dependencies for this job
        stmt = (
            select(JobDependency)
            .where(JobDependency.job_id == job_id)
        )
        result = await session.execute(stmt)
        dependencies = result.scalars().all()
        
        if not dependencies:
            return True  # No dependencies = ready to go
        
        # Check each dependency
        for dep in dependencies:
            dep_stmt = select(Job.status).where(Job.id == dep.depends_on_job_id)
            dep_result = await session.execute(dep_stmt)
            dep_status = dep_result.scalar_one_or_none()
            
            if dep_status != JobStatus.COMPLETED:
                return False  # This dependency hasn't completed yet
        
        return True

    async def _process_job(self, session: AsyncSession, job: Job) -> None:
        """Process a single job through its full lifecycle.
        
        Flow:
        1. Mark as 'processing'
        2. Execute the handler
        3. Check for cancellation (graceful)
        4. On success: mark completed, schedule recurring
        5. On failure: retry or send to DLQ
        """
        job_id_str = str(job.id)
        
        # Step 1: Mark job as processing
        job.status = JobStatus.PROCESSING
        job.worker_id = self.worker_id
        job.started_at = datetime.now(timezone.utc)
        job.updated_at = datetime.now(timezone.utc)
        await session.commit()
        
        await self._log_event(session, job.id, "started",
            f"Job {job.type} picked up by worker {self.worker_id}",
            {"worker_id": self.worker_id, "priority": job.priority})
        
        logger.info("Job processing started", extra={
            "job_id": job_id_str,
            "job_type": job.type,
            "worker_id": self.worker_id,
            "priority": job.priority,
            "retry_count": job.retry_count,
            "event": "job_started",
        })
        
        try:
            # Step 2: Execute the handler
            result = await execute_handler(
                job_type=job.type,
                job_id=job_id_str,
                payload=job.payload,
                failure_rate=settings.FAILURE_RATE,
            )
            
            # Step 3: Check for graceful cancellation
            # Re-read the job status from DB to see if it was cancelled during processing
            await session.refresh(job)
            
            if job.status == JobStatus.CANCELLED:
                # Job was cancelled while we were processing it
                logger.info("Job was cancelled during processing", extra={
                    "job_id": job_id_str,
                    "event": "job_cancelled_during_processing",
                })
                await self._log_event(session, job.id, "cancelled",
                    "Job was cancelled while being processed — result discarded",
                    {"result": result})
                await session.commit()
                return
            
            # Step 4: Success!
            job.status = JobStatus.COMPLETED
            job.completed_at = datetime.now(timezone.utc)
            job.updated_at = datetime.now(timezone.utc)
            job.error_message = None
            await session.commit()
            
            self._jobs_processed += 1
            
            await self._log_event(session, job.id, "completed",
                f"Job {job.type} completed successfully",
                {"result": result})
            
            logger.info("Job completed successfully", extra={
                "job_id": job_id_str,
                "job_type": job.type,
                "event": "job_completed",
            })
            
            # Handle recurring jobs — schedule the next run
            if job.interval:
                await self._schedule_next_recurring(session, job)
            
        except (JobProcessingError, Exception) as e:
            # Step 5: Failure — retry or DLQ
            await self._handle_failure(session, job, str(e))

    async def _handle_failure(self, session: AsyncSession, job: Job, error_msg: str) -> None:
        """Handle a failed job — either retry or send to DLQ.
        
        Retry backoff with jitter (from the task brief):
        Attempt 1 → ~1s   (base = 5^0 = 1)
        Attempt 2 → ~5s   (base = 5^1 = 5)
        Attempt 3 → ~25s  (base = 5^2 = 25)
        
        Jitter adds randomness: delay = base + random(0, base * 0.5)
        """
        job_id_str = str(job.id)
        
        # Re-read to get fresh state
        await session.refresh(job)
        
        job.retry_count += 1
        job.error_message = error_msg
        job.updated_at = datetime.now(timezone.utc)
        
        if job.retry_count < job.max_retries:
            # Still have retries left — schedule a retry with backoff
            attempt = job.retry_count  # 1, 2, or 3
            base_delay = 5 ** (attempt - 1)  # 1s, 5s, 25s
            jitter = random.uniform(0, base_delay * 0.5)
            total_delay = base_delay + jitter
            
            job.status = JobStatus.PENDING
            job.next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=total_delay)
            job.worker_id = None
            job.started_at = None
            await session.commit()
            
            await self._log_event(session, job.id, "retry",
                f"Retry {job.retry_count}/{job.max_retries} scheduled in {total_delay:.1f}s",
                {"retry_count": job.retry_count, "delay_seconds": round(total_delay, 1),
                 "error": error_msg})
            
            logger.warning("Job failed, scheduling retry", extra={
                "job_id": job_id_str,
                "retry_count": job.retry_count,
                "max_retries": job.max_retries,
                "delay_seconds": round(total_delay, 1),
                "error": error_msg,
                "event": "job_retry",
            })
            
        else:
            # All retries exhausted — send to Dead Letter Queue
            job.status = JobStatus.FAILED
            job.is_in_dlq = True
            job.worker_id = None
            await session.commit()
            
            self._jobs_failed += 1
            
            await self._log_event(session, job.id, "failed",
                f"Job failed after {job.max_retries} retries — moved to DLQ",
                {"retry_count": job.retry_count, "error": error_msg})
            
            logger.error("Job exhausted all retries, moved to DLQ", extra={
                "job_id": job_id_str,
                "job_type": job.type,
                "retry_count": job.retry_count,
                "error": error_msg,
                "event": "job_failed",
            })
            
            # Check DLQ threshold for alerts
            await self._check_dlq_threshold(session)

    async def _schedule_next_recurring(self, session: AsyncSession, completed_job: Job) -> None:
        """Schedule the next run of a recurring job.
        
        When a recurring job completes, we create a NEW job with:
        - Same type, payload, priority, interval
        - New UUID
        - scheduled_at = now + interval duration
        """
        interval_map = {
            "every_1_minute": timedelta(minutes=1),
            "every_5_minutes": timedelta(minutes=5),
            "every_1_hour": timedelta(hours=1),
        }
        
        interval_delta = interval_map.get(completed_job.interval)
        if interval_delta is None:
            logger.warning("Unknown interval, skipping recurring schedule", extra={
                "job_id": str(completed_job.id),
                "interval": completed_job.interval,
            })
            return
        
        next_run = datetime.now(timezone.utc) + interval_delta
        
        next_job = Job(
            type=completed_job.type,
            payload=completed_job.payload,
            priority=completed_job.priority,
            effective_priority=float(completed_job.priority),
            interval=completed_job.interval,
            scheduled_at=next_run,
        )
        
        session.add(next_job)
        await session.commit()
        
        await self._log_event(session, next_job.id, "created",
            f"Recurring job scheduled for {next_run.isoformat()}",
            {"parent_job_id": str(completed_job.id), "interval": completed_job.interval})
        
        logger.info("Next recurring job scheduled", extra={
            "parent_job_id": str(completed_job.id),
            "new_job_id": str(next_job.id),
            "scheduled_at": next_run.isoformat(),
            "interval": completed_job.interval,
            "event": "recurring_scheduled",
        })

    async def _check_dlq_threshold(self, session: AsyncSession) -> None:
        """Check if DLQ count exceeds the alert threshold.
        
        If DLQ has >= 10 jobs (configurable), simulate sending an alert email.
        """
        stmt = select(func.count()).select_from(Job).where(Job.is_in_dlq == True)
        result = await session.execute(stmt)
        dlq_count = result.scalar() or 0
        
        if dlq_count >= settings.DLQ_THRESHOLD:
            logger.critical("DLQ ALERT: threshold exceeded", extra={
                "dlq_count": dlq_count,
                "threshold": settings.DLQ_THRESHOLD,
                "event": "dlq_alert",
                "alert_action": "Simulated email alert sent to engineering team",
            })

    async def _log_event(
        self,
        session: AsyncSession,
        job_id: uuid.UUID,
        event: str,
        message: str,
        details: dict | None = None,
    ) -> None:
        """Write a structured event to the job_logs table."""
        log_entry = JobLog(
            job_id=job_id,
            event=event,
            message=message,
            details=details or {},
        )
        session.add(log_entry)
        await session.commit()
