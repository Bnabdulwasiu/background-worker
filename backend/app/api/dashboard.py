"""
Dashboard API Router.

Defines HTTP endpoints for fetching high-level stats of the job scheduler system.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.job import DashboardStats
from app.services import job_service

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db),
):
    """Retrieve aggregate counts of jobs by status and DLQ metrics."""
    stats = await job_service.get_dashboard_stats(db)
    return stats
