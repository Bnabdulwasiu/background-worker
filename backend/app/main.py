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
from app.database import engine
from app.logging_config import setup_logging, get_logger
from app.api import jobs, dlq, dashboard, sse

# Set up logging before anything else
setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("Starting %s", settings.APP_NAME)
    yield
    logger.info("Shutting down %s — disposing DB engine", settings.APP_NAME)
    await engine.dispose()


# Create the FastAPI app with metadata (shows up in Swagger docs)
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="A background job scheduler with priority queue, DAG workflows, and live monitoring.",
    lifespan=lifespan,
)

# Register routers
app.include_router(jobs.router)
app.include_router(dlq.router)
app.include_router(dashboard.router)
app.include_router(sse.router)

# CORS middleware - allows the React frontend to make requests to this API
# Without this, the browser blocks requests from localhost:5173 to localhost:8000
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods
    allow_headers=["*"],  # Allow all headers
)


# ---- Structured HTTP Request Logging Middleware ----
import time
from fastapi import Request

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.perf_counter()
    path = request.url.path
    method = request.method
    client_host = request.client.host if request.client else "unknown"
    
    # Process request
    response = await call_next(request)
    
    # Calculate duration
    process_time = time.perf_counter() - start_time
    
    # Skip logging for SSE streams and health check to prevent log spam
    if path not in ("/api/events", "/api/health"):
        logger.info(
            "HTTP %s %s - %d (%s ms)",
            method,
            path,
            response.status_code,
            f"{process_time * 1000:.2f}"
        )
    return response


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
