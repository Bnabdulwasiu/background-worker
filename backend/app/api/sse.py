"""
Server-Sent Events (SSE) Router.

Streams live updates to the frontend for job status changes and dashboard metrics.
"""

import asyncio
import json
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Request
from sqlalchemy import select
from sse_starlette.sse import EventSourceResponse

from app.config import settings
from app.database import async_session
from app.models.job import Job
from app.services import job_service

router = APIRouter(prefix="/api", tags=["Live Updates"])


@router.get("/events")
async def sse_events(request: Request):
    """
    Stream live updates to the frontend using Server-Sent Events (SSE).
    
    Emits:
    1. 'job_update' - sent when jobs are updated.
    2. 'dashboard_stats' - sent periodically with status count summaries.
    """
    async def event_generator():
        # Start looking 5 seconds back to catch any very recent changes
        last_check = datetime.now(timezone.utc) - timedelta(seconds=5)
        
        while True:
            # Check if the client disconnected
            if await request.is_disconnected():
                break
                
            async with async_session() as session:
                # Query for jobs updated since last_check
                stmt = (
                    select(Job)
                    .where(Job.updated_at > last_check)
                    .order_by(Job.updated_at.asc())
                )
                result = await session.execute(stmt)
                updated_jobs = result.scalars().all()
                
                # Emit events for any updated jobs
                if updated_jobs:
                    # Update our check watermark to the latest update time
                    last_check = max(job.updated_at for job in updated_jobs)
                    
                    for job in updated_jobs:
                        yield {
                            "event": "job_update",
                            "data": json.dumps({
                                "id": str(job.id),
                                "type": job.type,
                                "status": job.status,
                                "priority": job.priority,
                                "retry_count": job.retry_count,
                                "error_message": job.error_message,
                                "is_in_dlq": job.is_in_dlq,
                                "updated_at": job.updated_at.isoformat(),
                            })
                        }
                
                # Emit dashboard stats
                stats = await job_service.get_dashboard_stats(session)
                yield {
                    "event": "dashboard_stats",
                    "data": json.dumps(stats)
                }
                
            await asyncio.sleep(settings.SSE_POLL_INTERVAL)
            
    return EventSourceResponse(event_generator())
