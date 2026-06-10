"""
Worker CLI entry point.

This starts one or more worker processes that poll the database
for pending jobs and process them independently.

The worker runs in an infinite loop until you press Ctrl+C.
"""

import asyncio
import signal
import sys

from app.logging_config import setup_logging, get_logger
from app.worker.worker import Worker

# Set up logging before anything else
setup_logging()
logger = get_logger(__name__)


async def run_single_worker():
    """Run a single worker instance."""
    worker = Worker()
    
    # Handle graceful shutdown on Ctrl+C
    def handle_shutdown(signum, frame):
        logger.info("Shutdown signal received")
        worker.stop()
    
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)
    
    try:
        await worker.start()
    except KeyboardInterrupt:
        worker.stop()
        logger.info("Worker shut down by keyboard interrupt")


if __name__ == "__main__":
    print("=" * 50)
    print("  Background Job Worker")
    print("  Press Ctrl+C to stop")
    print("=" * 50)
    
    asyncio.run(run_single_worker())
