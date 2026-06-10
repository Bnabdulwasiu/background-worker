"""
Job API Router.

Defines HTTP endpoints for creating, listing, retrieving, and cancelling jobs,
as well as fetching job logs and creating DAG workflows.
"""

import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.job import (
    JobCreate,
    JobResponse,
    JobLogResponse,
    WorkflowCreate,
    WorkflowResponse,
)
from app.services import job_service

router = APIRouter(prefix="/api", tags=["Jobs"])


@router.post("/jobs", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def create_job(
    job_in: JobCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new job and enqueue/schedule it."""
    try:
        job = await job_service.create_job(
            session=db,
            job_type=job_in.type,
            priority=job_in.priority,
            payload=job_in.payload,
            scheduled_at=job_in.scheduled_at,
            interval=job_in.interval,
            depends_on=job_in.depends_on,
        )
        return job
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/jobs")
async def list_jobs(
    status: str | None = Query(None, description="Filter by job status"),
    job_type: str | None = Query(None, alias="type", description="Filter by job type"),
    priority: int | None = Query(None, ge=1, le=3, description="Filter by priority"),
    limit: int = Query(50, ge=1, le=100, description="Pagination limit"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db: AsyncSession = Depends(get_db),
):
    """List all jobs with optional filters and pagination."""
    jobs, total = await job_service.list_jobs(
        session=db,
        status=status,
        job_type=job_type,
        priority=priority,
        limit=limit,
        offset=offset,
    )
    return {
        "jobs": [JobResponse.model_validate(j) for j in jobs],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Retrieve detailed information about a specific job."""
    job = await job_service.get_job(db, job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )
    return job


@router.patch("/jobs/{job_id}/cancel", response_model=JobResponse)
async def cancel_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Cancel a job (only pending or processing jobs can be cancelled)."""
    try:
        job = await job_service.cancel_job(db, job_id)
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job {job_id} not found",
            )
        return job
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/jobs/{job_id}/logs", response_model=list[JobLogResponse])
async def get_job_logs(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Retrieve execution/history logs for a specific job."""
    job = await job_service.get_job(db, job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )
    logs = await job_service.get_job_logs(db, job_id)
    return logs


@router.post("/workflows", response_model=WorkflowResponse, status_code=status.HTTP_201_CREATED)
async def create_workflow(
    workflow_in: WorkflowCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a DAG workflow consisting of multiple jobs with dependencies.
    
    Validates against cycles during construction.
    """
    try:
        # Convert Pydantic schemas to list of dicts for the service
        jobs_data = []
        for job_data in workflow_in.jobs:
            jobs_data.append({
                "type": job_data.type,
                "priority": job_data.priority,
                "payload": job_data.payload,
                "scheduled_at": job_data.scheduled_at,
                "interval": job_data.interval,
                "depends_on_index": job_data.depends_on_index,
            })
            
        created_jobs = await job_service.create_workflow(db, jobs_data)
        
        # We can generate a workflow ID using the first job's ID or a random UUID
        workflow_id = f"wf-{uuid.uuid4().hex[:8]}"
        
        return WorkflowResponse(
            workflow_id=workflow_id,
            jobs=[JobResponse.model_validate(j) for j in created_jobs],
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
