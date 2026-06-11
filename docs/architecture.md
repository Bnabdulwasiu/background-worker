# Background Job Scheduler — System Architecture

A production-grade background job scheduler with worker processes, exponential backoff retries, Dead Letter Queue (DLQ) management, DAG workflows, starvation prevention, and a live monitoring dashboard.

---

## 1. System Overview

The system consists of three independently running components:

1. **FastAPI Web Server** — Exposes REST API endpoints for job submission, workflow creation, status management, and streams live updates to the UI via Server-Sent Events (SSE).
2. **PostgreSQL Database** — Serves as the persistent job store and queue coordinator. Row-level locking guarantees safe concurrent operations across multiple workers.
3. **Background Worker(s)** — Separate processes that independently poll the database, prioritize jobs using a heap scheduler, and execute them without involving the main application at all.

```
┌─────────────────────────────────────────────────────────────────┐
│                        Client / Web UI                           │
│          (React SPA – Dashboard, Jobs, DLQ, Workflows)           │
└──────────────────────────┬──────────────────────────────────────┘
                           │ REST API + SSE (live updates)
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                      FastAPI Server                              │
│               (uvicorn – async, non-blocking)                    │
└──────────────────────────┬──────────────────────────────────────┘
                           │ Read / Write
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                     PostgreSQL Database                           │
│             (jobs, job_dependencies, job_logs)                    │
└──────────┬──────────────────────────────────┬───────────────────┘
           │ Poll (FOR UPDATE SKIP LOCKED)    │ Poll (SKIP LOCKED)
           ▼                                  ▼
┌──────────────────────┐          ┌──────────────────────┐
│    Worker Process 1  │          │    Worker Process 2  │
│  (Heap Scheduler)    │          │  (Heap Scheduler)    │
│  (Rate Limiter)      │          │  (Rate Limiter)      │
└──────────────────────┘          └──────────────────────┘
```

The main application **never waits** for a job to complete. Workers run as separate OS processes managed by systemd (`scheduler-worker.service`).

---

## 2. Database Schema

### `jobs` Table
Tracks configuration and execution state of every job.

| Column | Type | Description |
|---|---|---|
| `id` | UUID (PK) | Unique job identifier |
| `type` | String | Handler type (`send_email`, `generate_report`, `upload_file`) |
| `payload` | JSON | Parameters for the handler |
| `priority` | Integer | Base priority: 1=High, 2=Medium, 3=Low |
| `effective_priority` | Float | Dynamically adjusted for starvation prevention |
| `status` | Enum | `pending` → `processing` → `completed` / `failed` / `cancelled` |
| `retry_count` | Integer | Execution attempts completed so far |
| `max_retries` | Integer | Maximum allowed retries (default: 3) |
| `error_message` | Text | Error detail from the last failure |
| `scheduled_at` | DateTime (UTC) | Future time — job will not run before this |
| `interval` | String | Recurring schedule (`every_1_minute`, `every_5_minutes`, `every_1_hour`) |
| `is_in_dlq` | Boolean | True when job has exhausted all retries |
| `worker_id` | String | ID of the worker process currently handling this job |
| `started_at` | DateTime (UTC) | When execution began |
| `completed_at` | DateTime (UTC) | When execution finished |
| `next_retry_at` | DateTime (UTC) | Earliest time for next retry attempt (backoff watermark) |

### `job_dependencies` Table
Represents directed edges in the DAG (which job must complete before another can start).

| Column | Type | Description |
|---|---|---|
| `id` | UUID (PK) | Unique relationship identifier |
| `job_id` | UUID (FK) | The downstream job (blocked) |
| `depends_on_job_id` | UUID (FK) | The upstream job that must complete first |

### `job_logs` Table
Immutable audit trail — every significant event appended here.

| Column | Type | Description |
|---|---|---|
| `id` | UUID (PK) | Unique log entry |
| `job_id` | UUID (FK) | The job this event belongs to |
| `event` | String | Event type (see §7 Logging) |
| `message` | Text | Human-readable description |
| `details` | JSON | Extensible metadata (errors, durations, worker_id, etc.) |

---

## 3. Job Status Flow

Every job moves through exactly this lifecycle — no exceptions:

```
            ┌─────────┐
     create │ PENDING │ ◄────────────────────────────┐
            └────┬────┘                              │ retry scheduled
                 │ worker picks up                   │
                 ▼                                   │
         ┌────────────┐        failure (retry left)  │
         │ PROCESSING │ ──────────────────────────────┘
         └─────┬──────┘
               │
       ┌───────┼───────────────────┐
       │       │                   │
       ▼       ▼                   ▼
  COMPLETED  FAILED           CANCELLED
             (→ DLQ after     (graceful —
             max retries)      see §6)
```

---

## 4. Scheduler Algorithms

### Primary: Min-Heap (Priority Queue)

The production scheduler uses a min-heap ordered by three keys:

1. **`effective_priority`** (ascending) — lower number = higher urgency
2. **`scheduled_at`** (ascending) — earlier scheduled time runs first
3. **`created_at`** (ascending) — oldest job wins on tie

The worker fetches a batch of up to 10 ready jobs from the database (using `FOR UPDATE SKIP LOCKED` — see §5), loads them into the heap, applies starvation boosts, then pops the most urgent one to execute.

**Why a heap?** The heap gives O(log n) insert and O(1) peek for the most urgent job. More importantly, it enforces **strict priority ordering** — a Priority 1 (High) job is always selected over a Priority 3 (Low) job in the same batch.

### Alternative: Timing Wheel

A cyclic bucket array covering a configurable time horizon. Each slot (bucket) holds all jobs scheduled within a specific time tick. Jobs are placed into the bucket corresponding to their scheduled delay, and the wheel advances by one tick per poll cycle.

**Time complexity:** O(1) insert and O(1) extract per tick — outperforms the heap for pure scheduling throughput.

### Benchmark Results

Both schedulers were benchmarked across insertion, extraction, and mixed workloads:

| Operation | Jobs | Heap | Timing Wheel | Winner |
|---|---|---|---|---|
| Insert | 1,000 | 14.91 ms | 11.76 ms | Wheel |
| Extract | 1,000 | 10.94 ms | 5.15 ms | Wheel |
| Mixed | 1,000 | 20.58 ms | 8.94 ms | Wheel |
| Insert | 10,000 | 85.11 ms | 43.88 ms | Wheel |
| Extract | 10,000 | 93.76 ms | 28.78 ms | Wheel |
| Mixed | 10,000 | 155.08 ms | 56.84 ms | Wheel |
| Insert | 100,000 | 1.460 s | 1.263 s | Wheel |
| Extract | 100,000 | 3.001 s | 536.06 ms | Wheel |
| Mixed | 100,000 | 2.343 s | 714.88 ms | Wheel |

### Why Heap is Chosen for Production

The Timing Wheel wins on raw throughput but **cannot enforce strict priority ordering** — all jobs in the same tick are treated equally. Because priority ordering is a core product requirement (a Priority 1 job must always run before a Priority 3 job), the Heap is used in production. The Timing Wheel is available as an alternative scheduler implementation and may be preferred in future workloads where time-based fairness matters more than priority.

---

## 5. Duplicate Protection

A single job cannot be picked up by two workers simultaneously. This is guaranteed at the database level — no application-level locks or coordination required:

```sql
SELECT * FROM jobs
WHERE status = 'pending'
  AND (scheduled_at IS NULL OR scheduled_at <= NOW())
  AND (next_retry_at IS NULL OR next_retry_at <= NOW())
ORDER BY effective_priority ASC, scheduled_at ASC, created_at ASC
LIMIT 10
FOR UPDATE SKIP LOCKED;
```

- **`FOR UPDATE`** — Locks each fetched row for the duration of the transaction.
- **`SKIP LOCKED`** — If another worker already holds the lock on a row, skip it immediately (no waiting). This guarantees that even with N workers running at the same time, each job is processed by exactly one worker.

---

## 6. Cancellation Policy

**Decision:** Cancellation is cooperative. The worker does not forcefully terminate a running handler mid-execution.

**Behaviour:**

| When cancellation is requested | What happens |
|---|---|
| Job is `pending` | Status immediately set to `cancelled`. It will never be picked up. |
| Job is `processing` | The cancel request is written to the database. The worker **lets the current handler finish**, then re-reads the status from the DB. If `cancelled`, it discards the result, writes a `cancelled` log event, and does not mark the job as `completed`. |

**Rationale:** Forcefully killing an async handler mid-flight (e.g. halfway through an SMTP connection) risks leaving external systems in inconsistent states. The cooperative approach is safer — the handler runs to completion, but the result is ignored and not committed as a success.

A `cancelled` log event is always written to the audit trail with the message: *"Job was cancelled while being processed — result discarded."*

---

## 7. Retries & Exponential Backoff

When a job handler raises an exception, the worker applies this retry policy:

**Formula:**
```
delay = 5^(attempt - 1) + uniform(0, 0.5 × 5^(attempt - 1))
```

| Attempt | Base Delay | Max Jitter | Approximate Range |
|---|---|---|---|
| 1 | 1s | +0.5s | ~1.0 – 1.5s |
| 2 | 5s | +2.5s | ~5.0 – 7.5s |
| 3 | 25s | +12.5s | ~25.0 – 37.5s |

Jitter prevents a "thundering herd" — if many jobs fail simultaneously, they don't all retry at the exact same moment and overload the handler.

After 3 failed attempts, the job is marked `failed` and `is_in_dlq = true` and sent to the Dead Letter Queue.

---

## 8. Dead Letter Queue (DLQ)

### What it is
The DLQ holds jobs that have exhausted all retry attempts. They are preserved for engineering inspection — no data is lost.

### DLQ Alert Threshold
**Threshold: 10 jobs**

Configurable via the `DLQ_THRESHOLD` environment variable (default: 10). Every time a new job enters the DLQ, the worker counts the total DLQ size. If the count is ≥ 10, a `CRITICAL`-level structured log event is emitted:

```json
{
  "level": "CRITICAL",
  "event": "dlq_alert",
  "dlq_count": 12,
  "threshold": 10,
  "alert_action": "Simulated email alert sent to engineering team"
}
```

In production, this log event would be consumed by an alerting pipeline (e.g. Datadog, PagerDuty, or a log-based alerting rule) to trigger a real notification. The system is structured so the alert emission is decoupled from the delivery mechanism.

### Manual Retry from DLQ
Engineers can inspect error details in the DLQ view and manually trigger a retry:
1. Optionally **edit the job payload** to fix the underlying data issue
2. Click **Retry** — this resets `retry_count = 0`, clears `is_in_dlq`, and returns the job to `pending` for a fresh execution cycle
3. If it fails again after 3 more attempts, it returns to the DLQ

---

## 9. Scheduled Jobs

Jobs with a `scheduled_at` timestamp in the future are created with `status = pending` but will not be picked up until `scheduled_at <= now()`. The worker query filters on this field directly, so no separate scheduling loop is needed.

**Example:**
```json
{
  "type": "send_email",
  "scheduled_at": "2026-06-10T10:00:00Z",
  "payload": { "to": "user@example.com", "subject": "Scheduled Report" }
}
```

---

## 10. Recurring Jobs

When a recurring job completes successfully, the worker immediately creates a **new** job with the same type, payload, priority, and interval, with `scheduled_at = now() + interval_duration`.

Supported intervals:

| Interval | Next run |
|---|---|
| `every_1_minute` | +1 minute |
| `every_5_minutes` | +5 minutes |
| `every_1_hour` | +1 hour |

The original job is marked `completed`. The new job gets a fresh UUID and starts from `retry_count = 0`. This continues indefinitely until the job is manually cancelled.

---

## 11. Starvation Prevention

### Problem
Without intervention, a continuous stream of Priority 1 (High) jobs blocks Priority 3 (Low) jobs from ever running.

### Solution: Dynamic Priority Boosting

The longer a job waits, the lower its `effective_priority` value becomes (remember: lower = more urgent):

```
effective_priority = base_priority − (waiting_time_seconds / STARVATION_BOOST_INTERVAL)
```

**Threshold: `STARVATION_BOOST_INTERVAL = 60 seconds`** (configurable via environment variable)

**Example:**
- A Priority 3 job waits 120 seconds → boost = 120 / 60 = 2 → `effective_priority = 3 − 2 = 1.0`
- It is now equal to a freshly-created Priority 1 job and will compete on equal footing

The boost is applied inside the `HeapScheduler.refresh_priorities()` method every time a batch is loaded for processing.

---

## 12. DAG Workflow Engine

Jobs can form Directed Acyclic Graphs (DAGs) by declaring dependencies.

**Example workflow:**
```
Generate Report  (job A)
      ↓ (depends on A completing)
Upload File      (job B)
      ↓ (depends on B completing)
Send Email       (job C)
```

### How it works
1. All jobs in the workflow are created simultaneously with `status = pending`
2. Before dispatching a job, the worker checks: *"Have all of this job's dependencies reached `completed`?"*
3. If any dependency is still `pending`, `processing`, `failed`, or `cancelled`, the downstream job is skipped on this poll cycle
4. Once all upstream jobs complete, the downstream job becomes eligible for pickup on the next poll

### Cycle Prevention
The workflow creation API validates that dependency chains do not form cycles using topological sort. A workflow with circular dependencies is rejected at submission time with a 422 error.

---

## 13. Rate Limiting (Token Bucket)

Each job type has an independent Token Bucket rate limiter to prevent overloading external services:

| Job Type | Limit | Window | Burst |
|---|---|---|---|
| `send_email` | 10 jobs | 60 seconds | 10 |
| `upload_file` | 5 jobs | 30 seconds | 5 |
| `generate_report` | 10 jobs | 60 seconds | 10 |

**How the Token Bucket works:**
- Each bucket starts full (burst capacity)
- Tokens refill continuously at `max_jobs / window_seconds` per second
- Each job execution consumes 1 token
- If the bucket is empty, the job is **deferred** (not failed): `next_retry_at` is set to when the next token becomes available

This means rate-limited jobs requeue automatically — they do not consume retry budget.

Limits are configurable via `JOB_RATE_LIMITS` in `config.py`. Set to `{}` to disable rate limiting entirely.

---

## 14. Live Updates (Server-Sent Events)

The UI reflects status changes in real time without a page refresh using **Server-Sent Events (SSE)**.

- The server maintains a persistent HTTP connection per client on `GET /api/events`
- Every 1 second (configurable via `SSE_POLL_INTERVAL`), the server queries the database for the latest job states and broadcasts a `data:` event to all connected clients
- The React frontend listens for these events and updates the jobs table and dashboard counts in place
- SSE was chosen over WebSockets because it is simpler (one-directional — server-to-client), works transparently through Nginx without special buffering configuration, and needs no client-side reconnection library (browsers handle reconnect natively)

Nginx SSE configuration:
```nginx
location /api/events {
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 24h;
}
```

---

## 15. Structured Logging

All significant events are logged in a structured JSON format. Every log entry includes: timestamp, level, logger name, and event-specific fields.

| Event | Level | Trigger |
|---|---|---|
| `job_created` | INFO | A new job is submitted via the API |
| `job_started` | INFO | A worker picks up and begins processing a job |
| `job_completed` | INFO | The handler returns successfully |
| `job_retry` | WARNING | A job handler fails and a retry is scheduled |
| `job_failed` | ERROR | A job exhausts all retries and enters the DLQ |
| `job_cancelled` | INFO | A job is cancelled (pre-execution or during processing) |
| `job_rate_limited` | WARNING | A job is deferred due to the token bucket being empty |
| `dlq_alert` | CRITICAL | DLQ size reaches or exceeds the configured threshold |
| `recurring_scheduled` | INFO | A new recurring job run is scheduled after completion |

**Example log entry (job failure):**
```json
{
  "asctime": "2026-06-11 18:13:17",
  "levelname": "WARNING",
  "name": "app.worker.worker",
  "event": "job_retry",
  "job_id": "bd2ef911-9898-4c0f-b521-42a21b036bea",
  "job_type": "send_email",
  "retry_count": 1,
  "max_retries": 3,
  "delay_seconds": 1.2,
  "error": "SMTP connection timed out after 30 seconds"
}
```

---

## 16. Deployment

### Infrastructure
- **VPS**: Ubuntu server (manually provisioned — no managed platforms)
- **Process Manager**: systemd (two services: `scheduler-api.service`, `scheduler-worker.service`)
- **Reverse Proxy**: Nginx (serves the built React frontend as static files; proxies `/api/*` to the FastAPI backend on port 8000)
- **HTTPS**: Let's Encrypt via Certbot (`sudo certbot --nginx -d <domain>`)
- **DNS**: DuckDNS dynamic DNS subdomain

### One-Command Deployment
```bash
sudo bash deployment/setup.sh your-subdomain.duckdns.org
```
The script: installs all dependencies, sets up PostgreSQL, creates the venv, builds the React frontend, configures and starts both systemd services, and sets up Nginx.

### Service Architecture on the Server
```
Internet → Nginx (80/443)
              ├── /         → /var/www/scheduler/frontend/dist  (static)
              ├── /api/*    → uvicorn :8000 (FastAPI)
              ├── /docs     → uvicorn :8000 (Swagger UI)
              └── /api/events → uvicorn :8000 (SSE, buffering disabled)

systemd:
  scheduler-api.service    → uvicorn app.main:app (API server)
  scheduler-worker.service → python run_worker.py (background worker)
```
