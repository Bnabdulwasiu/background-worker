"""

Each job type has its own handler. Right now we have one: send_email.
The handler receives the job's payload and executes the actual logic.

So we:
- Validate the payload (is there a 'to' and 'subject'?)
- Simulate network delay (1-3 seconds)
- Randomly fail ~20% of the time (to test retries)
- Log structured events throughout
- Return a real result object on success
"""

import asyncio
import random
import time
from datetime import datetime, timezone

from app.logging_config import get_logger

logger = get_logger(__name__)


class JobProcessingError(Exception):
    """Raised when a job handler fails.
    
    This is caught by the worker, which decides whether to retry or send to DLQ.
    """
    pass


async def handle_send_email(job_id: str, payload: dict, failure_rate: float = 0.2) -> dict:
    """Simulate sending an email.
    
    This is a REAL handler that executes actual logic:
    1. Validates payload fields
    2. Simulates SMTP connection with realistic delay
    3. Randomly fails to test retry logic
    4. Returns structured result
    
    Args:
        job_id: The job's UUID (for logging)
        payload: Must contain 'to' and 'subject' fields
        failure_rate: Probability of simulated failure (0.0 to 1.0)
    
    Returns:
        dict with send result details
    
    Raises:
        JobProcessingError: When validation fails or simulated SMTP error
    """
    # Step 1: Validate payload
    to_address = payload.get("to")
    subject = payload.get("subject")
    body = payload.get("body", "")
    
    if not to_address:
        raise JobProcessingError("Missing required field 'to' in payload")
    
    if not subject:
        raise JobProcessingError("Missing required field 'subject' in payload")
    
    # Basic email format validation
    if "@" not in to_address or "." not in to_address:
        raise JobProcessingError(f"Invalid email address: {to_address}")
    
    logger.info("Preparing to send email", extra={
        "job_id": job_id,
        "to": to_address,
        "subject": subject,
        "event": "email_preparing",
    })
    
    # Step 2: Simulate SMTP connection delay (1-3 seconds)
    delay = random.uniform(1.0, 3.0)
    logger.info("Connecting to SMTP server", extra={
        "job_id": job_id,
        "simulated_delay_seconds": round(delay, 2),
        "event": "smtp_connecting",
    })
    await asyncio.sleep(delay)
    
    # Step 3: Simulate random failure
    if random.random() < failure_rate:
        # Pick a realistic error
        errors = [
            "SMTP connection timed out after 30 seconds",
            "SMTP server returned 550: Mailbox not found",
            "SMTP authentication failed: invalid credentials",
            "SMTP connection refused by remote server",
            "DNS lookup failed for mail server",
        ]
        error_msg = random.choice(errors)
        
        logger.warning("Email send failed", extra={
            "job_id": job_id,
            "to": to_address,
            "error": error_msg,
            "event": "email_failed",
        })
        raise JobProcessingError(f"Failed to send email to {to_address}: {error_msg}")
    
    # Step 4: Success!
    sent_at = datetime.now(timezone.utc).isoformat()
    result = {
        "status": "sent",
        "to": to_address,
        "subject": subject,
        "body_length": len(body),
        "sent_at": sent_at,
        "smtp_response": "250 OK: Message accepted for delivery",
        "message_id": f"<{job_id}@scheduler.local>",
    }
    
    logger.info("Email sent successfully", extra={
        "job_id": job_id,
        "to": to_address,
        "subject": subject,
        "event": "email_sent",
    })
    
    return result


async def handle_generate_report(job_id: str, payload: dict, failure_rate: float = 0.2) -> dict:
    """Simulate generating a report.
    
    Used in DAG workflows: Generate Report → Upload File → Send Email
    """
    report_type = payload.get("report_type", "summary")
    
    logger.info("Generating report", extra={
        "job_id": job_id,
        "report_type": report_type,
        "event": "report_generating",
    })
    
    # Simulate processing time
    delay = random.uniform(2.0, 5.0)
    await asyncio.sleep(delay)
    
    if random.random() < failure_rate:
        raise JobProcessingError(f"Report generation failed: database query timed out")
    
    result = {
        "status": "generated",
        "report_type": report_type,
        "file_path": f"/tmp/reports/{job_id}.csv",
        "rows": random.randint(100, 10000),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    
    logger.info("Report generated successfully", extra={
        "job_id": job_id,
        "report_type": report_type,
        "rows": result["rows"],
        "event": "report_generated",
    })
    
    return result


async def handle_upload_file(job_id: str, payload: dict, failure_rate: float = 0.2) -> dict:
    """Simulate uploading a file.
    
    Used in DAG workflows: Generate Report → Upload File → Send Email
    """
    file_path = payload.get("file_path", "/tmp/unknown")
    destination = payload.get("destination", "s3://bucket/uploads/")
    
    logger.info("Uploading file", extra={
        "job_id": job_id,
        "file_path": file_path,
        "destination": destination,
        "event": "file_uploading",
    })
    
    delay = random.uniform(1.0, 4.0)
    await asyncio.sleep(delay)
    
    if random.random() < failure_rate:
        raise JobProcessingError(f"Upload failed: connection to storage server timed out")
    
    result = {
        "status": "uploaded",
        "file_path": file_path,
        "destination": f"{destination}{job_id}.csv",
        "size_bytes": random.randint(1024, 1048576),
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }
    
    logger.info("File uploaded successfully", extra={
        "job_id": job_id,
        "destination": result["destination"],
        "event": "file_uploaded",
    })
    
    return result


# Registry: maps job type strings to their handler functions
# The worker looks up the handler by job.type
HANDLERS = {
    "send_email": handle_send_email,
    "generate_report": handle_generate_report,
    "upload_file": handle_upload_file,
}


async def execute_handler(job_type: str, job_id: str, payload: dict, failure_rate: float = 0.2) -> dict:
    """Execute the appropriate handler for a job type.
    
    This is the main entry point called by the worker.
    
    Args:
        job_type: The type of job (e.g., "send_email")
        job_id: The job's UUID string
        payload: Job-specific data
        failure_rate: Simulated failure probability
    
    Returns:
        Result dict from the handler
    
    Raises:
        JobProcessingError: If the handler fails or type is unknown
    """
    handler = HANDLERS.get(job_type)
    
    if handler is None:
        raise JobProcessingError(f"Unknown job type: {job_type}. Known types: {list(HANDLERS.keys())}")
    
    return await handler(job_id, payload, failure_rate)
