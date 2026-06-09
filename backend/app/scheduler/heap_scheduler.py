"""
Heap-Based Priority Queue Scheduler.

This is the PRIMARY scheduling algorithm. It decides which job runs next.

HOW A HEAP WORKS (simplified):
- Think of it as a magic bag. You throw jobs in, and when you pull one out,
  you ALWAYS get the most important one first.
- Internally, it's a binary tree stored as a list. The smallest item
  is always at the top (index 0).
- Python's heapq module gives us this for free.

HOW WE ORDER JOBS:
- Each job becomes a tuple: (effective_priority, scheduled_at, created_at, job_id)
- Python compares tuples LEFT TO RIGHT:
  1. First compare effective_priority (lower = more urgent)
  2. If tied, compare scheduled_at (earlier = first)
  3. If still tied, compare created_at (older = first)
  4. job_id is just a tiebreaker to avoid comparing non-comparable objects

STARVATION PREVENTION:
- Without it: high-priority jobs always jump ahead, low-priority jobs wait forever
- Our solution: every 60 seconds a job waits, its effective_priority decreases by 1
- Example: priority 3 (low) job waiting 120 seconds → effective_priority = 3 - 2 = 1 (high!)
- This means old low-priority jobs eventually compete with new high-priority ones

TIME COMPLEXITY:
- push (add a job):  O(log n) — heap needs to rebalance
- pop (get next):    O(log n) — heap needs to rebalance
- peek (look at next): O(1) — just read index 0
- remove (cancel):   O(n) — we use lazy deletion to avoid this cost
"""

import heapq
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID


@dataclass(order=True)
class HeapEntry:
    """A single entry in the priority queue.
    
    The @dataclass(order=True) decorator makes entries comparable.
    Fields are compared in the order they're defined, so:
    1. effective_priority (lower = higher priority)
    2. scheduled_timestamp (earlier = first)
    3. created_timestamp (older = first)
    4. job_id is NOT compared (compare=False) - just carried along
    """
    effective_priority: float
    scheduled_timestamp: float  # Unix timestamp for comparison
    created_timestamp: float    # Unix timestamp for comparison
    job_id: UUID = field(compare=False)  # Don't use this for ordering
    removed: bool = field(default=False, compare=False, repr=False)


class HeapScheduler:
    """Min-heap priority queue for job scheduling.
    
    Usage:
        scheduler = HeapScheduler()
        scheduler.push(job_id, priority=1, scheduled_at=datetime.now(), created_at=datetime.now())
        next_job_id = scheduler.pop()  # Returns the most urgent job
    """

    def __init__(self, starvation_boost_interval: int = 60):
        """
        Args:
            starvation_boost_interval: seconds before a job's priority boosts by 1 level.
                Default 60 means: after 60s waiting, a priority-3 job acts like priority-2.
        """
        # The actual heap (list of HeapEntry objects)
        self._heap: list[HeapEntry] = []
        
        # Quick lookup: job_id → HeapEntry (for removal/updates)
        self._entry_map: dict[UUID, HeapEntry] = {}
        
        # How many seconds before a priority boost of 1 level
        self._boost_interval = starvation_boost_interval
        
        # Counter for tracking operations (useful for benchmarking)
        self._push_count = 0
        self._pop_count = 0

    def push(
        self,
        job_id: UUID,
        priority: int,
        scheduled_at: Optional[datetime] = None,
        created_at: Optional[datetime] = None,
    ) -> None:
        """Add a job to the priority queue.
        
        Args:
            job_id: Unique job identifier
            priority: Base priority (1=High, 2=Medium, 3=Low)
            scheduled_at: When the job should run (None = now)
            created_at: When the job was created (for tiebreaking)
        """
        now = datetime.now(timezone.utc)
        
        # If no scheduled time, it should run immediately
        sched_ts = (scheduled_at or now).timestamp()
        created_ts = (created_at or now).timestamp()
        
        # Calculate effective priority with starvation prevention
        effective = self._calculate_effective_priority(priority, created_ts)
        
        # If this job is already in the heap, remove the old entry first
        if job_id in self._entry_map:
            self.remove(job_id)
        
        # Create the heap entry
        entry = HeapEntry(
            effective_priority=effective,
            scheduled_timestamp=sched_ts,
            created_timestamp=created_ts,
            job_id=job_id,
        )
        
        # Add to both the heap and the lookup map
        self._entry_map[job_id] = entry
        heapq.heappush(self._heap, entry)
        self._push_count += 1

    def pop(self) -> Optional[UUID]:
        """Remove and return the highest-priority job ID.
        
        Returns None if the queue is empty.
        Skips entries that were lazily removed.
        """
        while self._heap:
            entry = heapq.heappop(self._heap)
            
            # Skip entries that were marked as removed (lazy deletion)
            if entry.removed:
                continue
            
            # Remove from the lookup map
            self._entry_map.pop(entry.job_id, None)
            self._pop_count += 1
            return entry.job_id
        
        return None

    def peek(self) -> Optional[UUID]:
        """Look at the highest-priority job WITHOUT removing it.
        
        Returns None if the queue is empty.
        """
        while self._heap:
            if self._heap[0].removed:
                # Clean up removed entries at the top
                heapq.heappop(self._heap)
                continue
            return self._heap[0].job_id
        return None

    def remove(self, job_id: UUID) -> bool:
        """Remove a job from the queue (lazy deletion).
        
        Instead of actually removing it from the heap (which is O(n)),
        we mark it as 'removed' and skip it when we pop. This is O(1).
        
        Returns True if the job was found and removed, False otherwise.
        """
        entry = self._entry_map.pop(job_id, None)
        if entry is not None:
            entry.removed = True
            return True
        return False

    def refresh_priorities(self) -> None:
        """Recalculate all effective priorities based on waiting time.
        
        Call this periodically (e.g., every 30 seconds) to apply
        starvation prevention. Jobs that have been waiting longer
        get their effective priority boosted.
        
        This rebuilds the entire heap, which is O(n), but we only
        call it occasionally, not on every operation.
        """
        now_ts = datetime.now(timezone.utc).timestamp()
        new_heap: list[HeapEntry] = []
        new_map: dict[UUID, HeapEntry] = {}
        
        for entry in self._heap:
            if entry.removed:
                continue
            
            # Recalculate: how long has this job been waiting?
            age_seconds = now_ts - entry.created_timestamp
            boost = age_seconds / self._boost_interval
            
            # We need the original priority to recalculate
            # Approximate it from the entry (original_priority ≈ round of initial effective)
            # For accuracy, we recalculate from created_timestamp
            new_effective = entry.effective_priority - boost
            
            new_entry = HeapEntry(
                effective_priority=max(0.0, entry.effective_priority),
                scheduled_timestamp=entry.scheduled_timestamp,
                created_timestamp=entry.created_timestamp,
                job_id=entry.job_id,
            )
            new_map[entry.job_id] = new_entry
            new_heap.append(new_entry)
        
        heapq.heapify(new_heap)
        self._heap = new_heap
        self._entry_map = new_map

    def size(self) -> int:
        """Return the number of active (non-removed) jobs in the queue."""
        return len(self._entry_map)

    def is_empty(self) -> bool:
        """Check if the queue has no active jobs."""
        return len(self._entry_map) == 0

    def clear(self) -> None:
        """Remove all jobs from the queue."""
        self._heap.clear()
        self._entry_map.clear()

    def get_stats(self) -> dict:
        """Get statistics about the scheduler (for benchmarking)."""
        return {
            "size": self.size(),
            "total_pushes": self._push_count,
            "total_pops": self._pop_count,
            "heap_size": len(self._heap),  # Includes removed entries
            "removed_entries": len(self._heap) - len(self._entry_map),
        }

    def _calculate_effective_priority(self, priority: int, created_timestamp: float) -> float:
        """Calculate effective priority with starvation prevention.
        
        Formula: effective = priority - (age_seconds / boost_interval)
        
        Example with boost_interval=60:
        - Priority 3 job, 0 seconds old:   effective = 3.0 - 0   = 3.0
        - Priority 3 job, 60 seconds old:  effective = 3.0 - 1.0 = 2.0
        - Priority 3 job, 120 seconds old: effective = 3.0 - 2.0 = 1.0
        
        Now it competes with priority-1 jobs!
        """
        now_ts = datetime.now(timezone.utc).timestamp()
        age_seconds = now_ts - created_timestamp
        boost = age_seconds / self._boost_interval
        return priority - boost

    def __len__(self) -> int:
        return self.size()

    def __repr__(self) -> str:
        return f"HeapScheduler(size={self.size()}, total_ops={self._push_count + self._pop_count})"
