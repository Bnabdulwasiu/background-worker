# Background Job Scheduler

A production-grade background job scheduler with a priority queue, DAG workflows, automatic retries, and a live dashboard UI.

## Features

- **Job Management**: Create, queue, process, and track jobs with different priorities
- **Priority Queue**: Heap-based scheduling ordered by priority, scheduled time, and creation time
- **DAG Workflows**: Jobs can depend on other jobs (e.g., Report → Upload → Email)
- **Automatic Retries**: Failed jobs retry up to 3 times with exponential backoff and jitter
- **Dead-Letter Queue**: Jobs that exhaust retries are quarantined for inspection and manual retry
- **Recurring Jobs**: Jobs can repeat at intervals (every 1 min, 5 min, 1 hour)
- **Starvation Prevention**: Low-priority jobs get priority boosts over time
- **Live Dashboard**: Real-time UI updates via Server-Sent Events (SSE)
- **Structured Logging**: JSON-formatted logs for every job lifecycle event
- **Alternative Scheduler**: Timing wheel implementation with benchmarks

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API | Python / FastAPI |
| Database | PostgreSQL |
| ORM | SQLAlchemy (async) + Alembic |
| Frontend | React + Vite |
| Live Updates | Server-Sent Events (SSE) |

## Project Structure

```
background-worker/
├── backend/           # FastAPI API + Worker processes
│   ├── app/
│   │   ├── api/       # HTTP endpoints
│   │   ├── models/    # Database models
│   │   ├── schemas/   # Request/response schemas
│   │   ├── scheduler/ # Heap + Timing Wheel algorithms
│   │   ├── services/  # Business logic
│   │   └── worker/    # Background job processing
│   └── alembic/       # Database migrations
├── frontend/          # React dashboard UI
└── docs/              # Architecture documentation
```

## Getting Started

### Prerequisites

- Python 3.10+
- PostgreSQL 16
- Node.js 18+ (for frontend)

### Backend Setup

```bash
cd backend
python -m venv venv
venv\Scripts\activate      # Windows
pip install -r requirements.txt
alembic upgrade head        # Run database migrations
uvicorn app.main:app --reload  # Start API server
python run_worker.py        # Start worker (separate terminal)
```

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

## API Documentation

Swagger UI available at: `http://localhost:8000/docs`

## Architecture

See [docs/architecture.md](docs/architecture.md) for detailed system design.

## License

MIT
