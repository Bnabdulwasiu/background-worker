"""
Pydantic schemas for request/response validation.

These define the SHAPE of data coming in (requests) and going out (responses).
FastAPI uses these to:
1. Validate incoming data (reject bad requests automatically)
2. Generate Swagger docs (the API documentation page)
3. Serialize responses (convert Python objects to JSON)

The naming convention:
- JobCreate = what the client sends to CREATE a job
- JobResponse = what the API sends BACK to the client
- JobUpdate = what the client can UPDATE on an existing job
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class JobCreate(BaseModel):
    """Schema for creating a new job.
    
    Example request body:
    {
        "type": "send_email",
        "priority": 1,
        "payload": {"to": "test@gmail.com", "subject": "Welcome"},
        "scheduled_at": "2026-06-10T10:00:00Z",
        "interval": "every_5_minutes",
        "depends_on": ["<uuid>"]
    }
    """
    type: str = Field(
        ...,  # ... means required
        min_length=1,
        max_length=100,
        description="Job type identifier (e.g., 'send_email')",
        examples=["send_email"],
    )
    priority: int = Field(
        default=2,
        ge=1,  # greater than or equal to 1
        le=3,  # less than or equal to 3
        description="Priority level: 1=High, 2=Medium, 3=Low",
    )
    payload: dict = Field(
        default_factory=dict,
        description="Job-specific data as JSON",
        examples=[{"to": "test@gmail.com", "subject": "Welcome"}],
    )
    scheduled_at: datetime | None = Field(
        default=None,
        description="When to run the job (ISO 8601). Omit for immediate.",
    )
    interval: str | None = Field(
        default=None,
        description="Recurring interval: every_1_minute, every_5_minutes, every_1_hour",
    )
    depends_on: list[uuid.UUID] = Field(
        default_factory=list,
        description="List of job IDs this job depends on (DAG workflow)",
    )

    @field_validator("interval")
    @classmethod
    def validate_interval(cls, v: str | None) -> str | None:
        """Only allow specific interval values."""
        if v is not None:
            allowed = {"every_1_minute", "every_5_minutes", "every_1_hour"}
            if v not in allowed:
                raise ValueError(f"interval must be one of: {', '.join(allowed)}")
        return v

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        """Only allow known job types."""
        allowed = {"send_email", "generate_report", "upload_file"}
        if v not in allowed:
            raise ValueError(f"type must be one of: {', '.join(allowed)}")
        return v


class JobRetry(BaseModel):
    """Schema for retrying a job with an optional new payload."""
    payload: dict | None = None


class JobResponse(BaseModel):
    """Schema for job data returned by the API.
    
    This maps directly to the Job database model but only exposes
    the fields we want the client to see.
    """
    id: uuid.UUID
    type: str
    payload: dict
    priority: int
    effective_priority: float
    status: str
    retry_count: int
    max_retries: int
    error_message: str | None = None
    scheduled_at: datetime | None = None
    interval: str | None = None
    is_in_dlq: bool
    worker_id: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        # This tells Pydantic to read data from SQLAlchemy model attributes
        from_attributes = True


class JobLogResponse(BaseModel):
    """Schema for job log entries."""
    id: uuid.UUID
    job_id: uuid.UUID
    event: str
    message: str
    details: dict | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class DashboardStats(BaseModel):
    """Dashboard statistics - counts of jobs by status."""
    pending: int = 0
    processing: int = 0
    completed: int = 0
    failed: int = 0
    cancelled: int = 0
    dlq_count: int = 0
    total: int = 0


class WorkflowJobCreate(BaseModel):
    """A single job within a workflow creation request."""
    type: str = Field(..., min_length=1, max_length=100)
    priority: int = Field(default=2, ge=1, le=3)
    payload: dict = Field(default_factory=dict)
    scheduled_at: datetime | None = None
    interval: str | None = None
    # Index-based dependency within the workflow array
    depends_on_index: list[int] = Field(
        default_factory=list,
        description="Indices of other jobs in this workflow that must complete first",
    )

    @field_validator("interval")
    @classmethod
    def validate_interval(cls, v: str | None) -> str | None:
        if v is not None:
            allowed = {"every_1_minute", "every_5_minutes", "every_1_hour"}
            if v not in allowed:
                raise ValueError(f"interval must be one of: {', '.join(allowed)}")
        return v

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        allowed = {"send_email", "generate_report", "upload_file"}
        if v not in allowed:
            raise ValueError(f"type must be one of: {', '.join(allowed)}")
        return v


class WorkflowCreate(BaseModel):
    """Schema for creating a DAG workflow (batch of jobs with dependencies).
    
    Example:
    {
        "jobs": [
            {"type": "generate_report", "priority": 2, "payload": {}},
            {"type": "upload_file", "priority": 2, "payload": {}, "depends_on_index": [0]},
            {"type": "send_email", "priority": 1, "payload": {"to": "a@b.com"}, "depends_on_index": [1]}
        ]
    }
    """
    jobs: list[WorkflowJobCreate] = Field(
        ...,
        min_length=1,
        description="List of jobs to create, with index-based dependencies",
    )


class WorkflowResponse(BaseModel):
    """Response after creating a workflow."""
    workflow_id: str
    jobs: list[JobResponse]
    message: str = "Workflow created successfully"
