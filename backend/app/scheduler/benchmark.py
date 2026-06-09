"""
Benchmark: Heap vs Timing Wheel.

This script compares both scheduling algorithms and produces a results table.
Run it with: python -m app.scheduler.benchmark

The output goes into the architecture doc for submission.
"""

import random
import time
import uuid
from datetime import datetime, timezone, timedelta

from app.scheduler.heap_scheduler import HeapScheduler
from app.scheduler.timing_wheel import TimingWheel


def generate_test_jobs(count: int) -> list[dict]:
    """Generate random test jobs for benchmarking."""
    jobs = []
    now = datetime.now(timezone.utc)
    
    for i in range(count):
        job = {
            "job_id": uuid.uuid4(),
            "priority": random.choice([1, 2, 3]),
            "delay_seconds": random.uniform(0, 300),  # 0 to 5 minutes
            "created_at": now - timedelta(seconds=random.uniform(0, 600)),
        }
        jobs.append(job)
    
    return jobs


def benchmark_heap_insert(jobs: list[dict]) -> float:
    """Benchmark heap insertion time."""
    scheduler = HeapScheduler()
    now = datetime.now(timezone.utc)
    
    start = time.perf_counter()
    for job in jobs:
        scheduler.push(
            job_id=job["job_id"],
            priority=job["priority"],
            scheduled_at=now + timedelta(seconds=job["delay_seconds"]),
            created_at=job["created_at"],
        )
    elapsed = time.perf_counter() - start
    return elapsed


def benchmark_wheel_insert(jobs: list[dict]) -> float:
    """Benchmark timing wheel insertion time."""
    wheel = TimingWheel()
    
    start = time.perf_counter()
    for job in jobs:
        wheel.add(
            job_id=job["job_id"],
            delay_seconds=job["delay_seconds"],
            priority=job["priority"],
            created_at=job["created_at"],
        )
    elapsed = time.perf_counter() - start
    return elapsed


def benchmark_heap_extract(jobs: list[dict]) -> float:
    """Benchmark heap extraction (pop all jobs)."""
    scheduler = HeapScheduler()
    now = datetime.now(timezone.utc)
    
    for job in jobs:
        scheduler.push(
            job_id=job["job_id"],
            priority=job["priority"],
            scheduled_at=now + timedelta(seconds=job["delay_seconds"]),
            created_at=job["created_at"],
        )
    
    start = time.perf_counter()
    while not scheduler.is_empty():
        scheduler.pop()
    elapsed = time.perf_counter() - start
    return elapsed


def benchmark_wheel_extract(jobs: list[dict]) -> float:
    """Benchmark timing wheel extraction (tick through all jobs)."""
    wheel = TimingWheel()
    
    for job in jobs:
        wheel.add(
            job_id=job["job_id"],
            delay_seconds=0,  # All due immediately for fair comparison
            priority=job["priority"],
            created_at=job["created_at"],
        )
    
    start = time.perf_counter()
    # Single tick to collect all immediately-due jobs
    wheel.tick()
    due = wheel.get_due_jobs()
    elapsed = time.perf_counter() - start
    return elapsed


def benchmark_heap_mixed(jobs: list[dict]) -> float:
    """Benchmark mixed insert/extract workload on heap."""
    scheduler = HeapScheduler()
    now = datetime.now(timezone.utc)
    
    start = time.perf_counter()
    for i, job in enumerate(jobs):
        scheduler.push(
            job_id=job["job_id"],
            priority=job["priority"],
            scheduled_at=now + timedelta(seconds=job["delay_seconds"]),
            created_at=job["created_at"],
        )
        # Pop every 3rd insertion
        if i % 3 == 0 and not scheduler.is_empty():
            scheduler.pop()
    elapsed = time.perf_counter() - start
    return elapsed


def benchmark_wheel_mixed(jobs: list[dict]) -> float:
    """Benchmark mixed insert/tick workload on timing wheel."""
    wheel = TimingWheel()
    
    start = time.perf_counter()
    for i, job in enumerate(jobs):
        wheel.add(
            job_id=job["job_id"],
            delay_seconds=0,
            priority=job["priority"],
            created_at=job["created_at"],
        )
        # Tick every 3rd insertion
        if i % 3 == 0:
            wheel.tick()
    elapsed = time.perf_counter() - start
    return elapsed


def format_time(seconds: float) -> str:
    """Format elapsed time in a human-readable way."""
    if seconds < 0.001:
        return f"{seconds * 1_000_000:.1f} µs"
    elif seconds < 1:
        return f"{seconds * 1_000:.2f} ms"
    else:
        return f"{seconds:.3f} s"


def run_benchmarks():
    """Run all benchmarks and print results."""
    sizes = [1_000, 10_000, 100_000]
    
    print("=" * 75)
    print("  BENCHMARK: Heap-Based Priority Queue vs Timing Wheel")
    print("=" * 75)
    print()
    
    # Results storage for markdown output
    results = []
    
    for size in sizes:
        print(f"\n--- {size:,} jobs ---")
        jobs = generate_test_jobs(size)
        
        # Insertion benchmark
        heap_insert = benchmark_heap_insert(jobs)
        wheel_insert = benchmark_wheel_insert(jobs)
        
        print(f"  Insert  | Heap: {format_time(heap_insert):>12} | Wheel: {format_time(wheel_insert):>12} | "
              f"Winner: {'Wheel' if wheel_insert < heap_insert else 'Heap'}")
        
        # Extraction benchmark
        heap_extract = benchmark_heap_extract(jobs)
        wheel_extract = benchmark_wheel_extract(jobs)
        
        print(f"  Extract | Heap: {format_time(heap_extract):>12} | Wheel: {format_time(wheel_extract):>12} | "
              f"Winner: {'Wheel' if wheel_extract < heap_extract else 'Heap'}")
        
        # Mixed workload
        heap_mixed = benchmark_heap_mixed(jobs)
        wheel_mixed = benchmark_wheel_mixed(jobs)
        
        print(f"  Mixed   | Heap: {format_time(heap_mixed):>12} | Wheel: {format_time(wheel_mixed):>12} | "
              f"Winner: {'Wheel' if wheel_mixed < heap_mixed else 'Heap'}")
        
        results.append({
            "size": size,
            "heap_insert": heap_insert,
            "wheel_insert": wheel_insert,
            "heap_extract": heap_extract,
            "wheel_extract": wheel_extract,
            "heap_mixed": heap_mixed,
            "wheel_mixed": wheel_mixed,
        })
    
    # Print markdown table for architecture doc
    print("\n\n" + "=" * 75)
    print("  MARKDOWN TABLE (copy to architecture doc)")
    print("=" * 75)
    print()
    print("| Operation | Jobs | Heap | Timing Wheel | Winner |")
    print("|-----------|------|------|-------------|--------|")
    
    for r in results:
        size = f"{r['size']:,}"
        
        print(f"| Insert | {size} | {format_time(r['heap_insert'])} | "
              f"{format_time(r['wheel_insert'])} | "
              f"{'Wheel' if r['wheel_insert'] < r['heap_insert'] else 'Heap'} |")
        
        print(f"| Extract | {size} | {format_time(r['heap_extract'])} | "
              f"{format_time(r['wheel_extract'])} | "
              f"{'Wheel' if r['wheel_extract'] < r['heap_extract'] else 'Heap'} |")
        
        print(f"| Mixed | {size} | {format_time(r['heap_mixed'])} | "
              f"{format_time(r['wheel_mixed'])} | "
              f"{'Wheel' if r['wheel_mixed'] < r['heap_mixed'] else 'Heap'} |")
    
    print()
    print("Tradeoff Summary:")
    print("- Heap: Better for priority-ordered extraction, precise ordering")
    print("- Timing Wheel: Better for high-throughput insertion, time-based scheduling")
    print("- For our job scheduler, the HEAP is the better choice because")
    print("  priority ordering is critical for job execution order.")


if __name__ == "__main__":
    run_benchmarks()
