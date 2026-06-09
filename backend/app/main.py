"""
FastAPI application entry point.

This is the "main" file of the backend. It:
1. Creates the FastAPI app
2. Sets up CORS (so the frontend can talk to the API)
3. Registers all API routes
4. Provides a health check endpoint
5. Initializes logging

To run: uvicorn app.main:app --reload
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.logging_config import setup_logging, get_logger

# Set up structured logging before anything else
setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs on app startup and shutdown.
    
    Startup: log that the app is ready
    Shutdown: clean up resources
    """
    logger.info("Application starting up", extra={
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION,
    })
    yield
    logger.info("Application shutting down")


# Create the FastAPI app with metadata (shows up in Swagger docs)
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="A background job scheduler with priority queue, DAG workflows, and live monitoring.",
    lifespan=lifespan,
)

# CORS middleware - allows the React frontend to make requests to this API
# Without this, the browser blocks requests from localhost:5173 to localhost:8000
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods
    allow_headers=["*"],  # Allow all headers
)


# ---- Health Check ----
@app.get("/api/health", tags=["System"])
async def health_check():
    """Health check endpoint.
    
    Returns 200 if the API is running. Used by monitoring tools
    and Nginx to verify the app is alive.
    """
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
    }
