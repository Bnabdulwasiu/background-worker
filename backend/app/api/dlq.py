"""
Dead Letter Queue (DLQ) API Router.

Defines HTTP endpoints for inspecting failed jobs in the DLQ and triggering manual retries.
"""

import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.job import JobResponse
from app.services import job_service

router = APIRouter(prefix="/api", tags=["DLQ"])


@router.get("/dlq", response_model=list[JobResponse])
async def list_dlq_jobs(
    db: AsyncSession = Depends(get_db),
):
    """Retrieve all jobs currently in the Dead Letter Queue (DLQ)."""
    jobs = await job_service.get_dlq_jobs(db)
    return jobs


@router.post("/dlq/{job_id}/retry", response_model=JobResponse)
async def retry_dlq_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger a retry for a job currently in the DLQ.
    
    Resets the job's retry count and returns it to PENDING status.
    """
    try:
        job = await job_service.retry_dlq_job(db, job_id)
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job {job_id} not found in DLQ",
            )
        return job
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
