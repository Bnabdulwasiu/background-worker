"""
Timing Wheel Scheduler (Alternative Algorithm).

This is the ALTERNATIVE scheduling algorithm, required for benchmarking
against the heap. You will be asked to explain the tradeoffs.

HOW A TIMING WHEEL WORKS (simplified):
- Imagine a clock with 60 slots (one per second).
- Each slot holds a bucket (list) of jobs scheduled for that time.
- A cursor (like the second hand) moves forward one slot per tick.
- When the cursor reaches a slot, all jobs in that bucket are "due".

Example with 10 slots, 1 second per slot:
    Slot:  [0] [1] [2] [3] [4] [5] [6] [7] [8] [9]
    Jobs:  [ ] [A] [ ] [B,C] [ ] [ ] [ ] [ ] [ ] [ ]
    Cursor: ^
    
    After 1 tick: cursor moves to slot 1, job A is due
    After 3 ticks: cursor moves to slot 3, jobs B and C are due

MULTI-LEVEL (HIERARCHICAL) TIMING WHEEL:
- What if a job is 5 minutes away? That's 300 seconds — more than 60 slots.
- Solution: use multiple wheels, like a real clock:
  - Level 0: 60 slots × 1 second  = handles 0-59 seconds
  - Level 1: 60 slots × 1 minute  = handles 1-60 minutes
  - Level 2: 24 slots × 1 hour    = handles 1-24 hours
- When Level 1's cursor ticks, it "cascades" jobs down to Level 0
  with their remaining time.

TRADEOFFS vs HEAP:
| Operation    | Heap      | Timing Wheel |
|-------------|-----------|-------------|
| Insert      | O(log n)  | O(1)        | ← Wheel is faster
| Get next    | O(log n)  | O(1) amortized | ← Wheel is faster
| Cancel      | O(n) lazy | O(1) with index | ← Wheel is faster
| Precision   | Exact     | Rounded to slot | ← Heap is better
| Memory      | Compact   | Fixed slots | ← Heap is better
| Priority    | Natural   | Needs sorting | ← Heap is better

KEY INSIGHT FOR PRESENTATION:
"The heap is better when you need precise ordering by priority.
The timing wheel is better when you have many jobs with time-based
scheduling and don't need exact priority ordering."
"""

import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID


@dataclass
class WheelEntry:
    """A job entry in the timing wheel."""
    job_id: UUID
    priority: int
    scheduled_timestamp: float
    created_timestamp: float
    removed: bool = False


class TimingWheel:
    """Hierarchical Timing Wheel scheduler.
    
    Uses a multi-level wheel structure:
    - Level 0 (seconds): 60 slots, 1 second resolution
    - Level 1 (minutes): 60 slots, 1 minute resolution  
    - Level 2 (hours):   24 slots, 1 hour resolution
    
    Total range: up to 24 hours into the future.
    
    Usage:
        wheel = TimingWheel()
        wheel.add(job_id, delay_seconds=30, priority=1)
        wheel.tick()  # Call this every second
        due_jobs = wheel.get_due_jobs()
    """

    def __init__(self, tick_duration_ms: int = 1000):
        """
        Args:
            tick_duration_ms: How many milliseconds per tick (default 1000 = 1 second)
        """
        self._tick_duration_ms = tick_duration_ms
        self._tick_duration_s = tick_duration_ms / 1000.0
        
        # Level 0: 60 slots × 1 second = 60 seconds
        self._wheel_0: list[list[WheelEntry]] = [[] for _ in range(60)]
        self._cursor_0: int = 0
        
        # Level 1: 60 slots × 60 seconds = 60 minutes
        self._wheel_1: list[list[WheelEntry]] = [[] for _ in range(60)]
        self._cursor_1: int = 0
        
        # Level 2: 24 slots × 3600 seconds = 24 hours
        self._wheel_2: list[list[WheelEntry]] = [[] for _ in range(24)]
        self._cursor_2: int = 0
        
        # Jobs that are immediately ready (due now)
        self._ready_queue: list[WheelEntry] = []
        
        # Lookup map for O(1) removal
        self._entry_map: dict[UUID, WheelEntry] = {}
        
        # Track the start time for computing slots
        self._start_time = time.monotonic()
        self._tick_count = 0
        
        # Stats for benchmarking
        self._add_count = 0
        self._tick_total_count = 0

    def add(
        self,
        job_id: UUID,
        delay_seconds: float = 0,
        priority: int = 2,
        created_at: Optional[datetime] = None,
    ) -> None:
        """Add a job to the timing wheel.
        
        Args:
            job_id: Unique job identifier
            delay_seconds: How many seconds from now until this job should run
            priority: Job priority (1=High, 2=Medium, 3=Low) — used for
                     sorting within the same time slot
            created_at: When the job was originally created
        
        Time complexity: O(1) — just calculate the slot and append
        """
        now = datetime.now(timezone.utc)
        created_ts = (created_at or now).timestamp()
        scheduled_ts = now.timestamp() + delay_seconds
        
        # Remove old entry if this job already exists
        if job_id in self._entry_map:
            self.remove(job_id)
        
        entry = WheelEntry(
            job_id=job_id,
            priority=priority,
            scheduled_timestamp=scheduled_ts,
            created_timestamp=created_ts,
        )
        
        self._entry_map[job_id] = entry
        self._add_count += 1
        
        if delay_seconds <= 0:
            # Due immediately
            self._ready_queue.append(entry)
            return
        
        # Calculate which wheel and slot this job goes into
        ticks = int(delay_seconds / self._tick_duration_s)
        
        if ticks < 60:
            # Level 0: within the next 60 seconds
            slot = (self._cursor_0 + ticks) % 60
            self._wheel_0[slot].append(entry)
        elif ticks < 3600:
            # Level 1: within the next 60 minutes
            minutes = ticks // 60
            slot = (self._cursor_1 + minutes) % 60
            self._wheel_1[slot].append(entry)
        elif ticks < 86400:
            # Level 2: within the next 24 hours
            hours = ticks // 3600
            slot = (self._cursor_2 + hours) % 24
            self._wheel_2[slot].append(entry)
        else:
            # Beyond 24 hours — put in the last slot of level 2
            # (will be rescheduled on cascade)
            slot = (self._cursor_2 + 23) % 24
            self._wheel_2[slot].append(entry)

    def tick(self) -> list[UUID]:
        """Advance the wheel by one tick (1 second by default).
        
        Returns a list of job IDs that are now due.
        
        This is called once per tick interval (e.g., every second).
        It advances the Level 0 cursor, and when Level 0 wraps around,
        it cascades from Level 1 to Level 0, and so on.
        """
        self._tick_count += 1
        self._tick_total_count += 1
        
        # Advance Level 0 cursor
        self._cursor_0 = (self._cursor_0 + 1) % 60
        
        # Collect due jobs from the current Level 0 slot
        due_entries = self._wheel_0[self._cursor_0]
        self._wheel_0[self._cursor_0] = []  # Clear the slot
        
        # Add non-removed entries to the ready queue
        for entry in due_entries:
            if not entry.removed:
                self._ready_queue.append(entry)
        
        # Cascade: when Level 0 wraps around (every 60 ticks)
        if self._cursor_0 == 0:
            self._cascade_level_1()
        
        # Return due job IDs, sorted by priority within this tick
        return self.get_due_jobs()

    def get_due_jobs(self) -> list[UUID]:
        """Get all jobs that are currently due, sorted by priority.
        
        Returns job IDs sorted by priority (1 first, then 2, then 3).
        Clears the ready queue after returning.
        """
        # Filter out removed entries
        active = [e for e in self._ready_queue if not e.removed]
        
        # Sort by priority (lower number = higher priority)
        active.sort(key=lambda e: (e.priority, e.created_timestamp))
        
        # Extract job IDs
        result = []
        for entry in active:
            if entry.job_id in self._entry_map:
                result.append(entry.job_id)
                self._entry_map.pop(entry.job_id, None)
        
        # Clear the ready queue
        self._ready_queue.clear()
        
        return result

    def remove(self, job_id: UUID) -> bool:
        """Remove a job from the wheel.
        
        Uses lazy deletion — marks the entry as removed.
        Time complexity: O(1)
        
        Returns True if the job was found and removed.
        """
        entry = self._entry_map.pop(job_id, None)
        if entry is not None:
            entry.removed = True
            return True
        return False

    def size(self) -> int:
        """Number of active jobs in the wheel."""
        return len(self._entry_map)

    def is_empty(self) -> bool:
        """Check if no active jobs remain."""
        return len(self._entry_map) == 0

    def clear(self) -> None:
        """Remove all jobs."""
        for wheel in [self._wheel_0, self._wheel_1, self._wheel_2]:
            for slot in wheel:
                slot.clear()
        self._ready_queue.clear()
        self._entry_map.clear()

    def get_stats(self) -> dict:
        """Get statistics for benchmarking."""
        total_in_wheel = sum(
            len(slot) 
            for wheel in [self._wheel_0, self._wheel_1, self._wheel_2]
            for slot in wheel
        )
        return {
            "size": self.size(),
            "total_adds": self._add_count,
            "total_ticks": self._tick_total_count,
            "ready_queue_size": len(self._ready_queue),
            "entries_in_wheel": total_in_wheel,
        }

    def _cascade_level_1(self) -> None:
        """Cascade jobs from Level 1 to Level 0.
        
        Called when Level 0 cursor wraps around (every 60 seconds).
        Takes all jobs in the current Level 1 slot and redistributes
        them into Level 0 slots based on their remaining time.
        """
        self._cursor_1 = (self._cursor_1 + 1) % 60
        
        entries = self._wheel_1[self._cursor_1]
        self._wheel_1[self._cursor_1] = []
        
        now_ts = time.monotonic()
        
        for entry in entries:
            if entry.removed:
                continue
            
            # Calculate remaining delay
            remaining = entry.scheduled_timestamp - datetime.now(timezone.utc).timestamp()
            
            if remaining <= 0:
                # Due now
                self._ready_queue.append(entry)
            elif remaining < 60:
                # Fits in Level 0
                ticks = int(remaining / self._tick_duration_s)
                slot = (self._cursor_0 + ticks) % 60
                self._wheel_0[slot].append(entry)
            else:
                # Still too far out, put back
                minutes = int(remaining / 60)
                slot = (self._cursor_1 + minutes) % 60
                self._wheel_1[slot].append(entry)
        
        # Cascade Level 2 → Level 1 when Level 1 wraps
        if self._cursor_1 == 0:
            self._cascade_level_2()

    def _cascade_level_2(self) -> None:
        """Cascade jobs from Level 2 to Level 1.
        
        Called when Level 1 cursor wraps around (every 60 minutes).
        """
        self._cursor_2 = (self._cursor_2 + 1) % 24
        
        entries = self._wheel_2[self._cursor_2]
        self._wheel_2[self._cursor_2] = []
        
        for entry in entries:
            if entry.removed:
                continue
            
            remaining = entry.scheduled_timestamp - datetime.now(timezone.utc).timestamp()
            
            if remaining <= 0:
                self._ready_queue.append(entry)
            elif remaining < 60:
                ticks = int(remaining / self._tick_duration_s)
                slot = (self._cursor_0 + ticks) % 60
                self._wheel_0[slot].append(entry)
            elif remaining < 3600:
                minutes = int(remaining / 60)
                slot = (self._cursor_1 + minutes) % 60
                self._wheel_1[slot].append(entry)
            else:
                hours = int(remaining / 3600)
                slot = (self._cursor_2 + hours) % 24
                self._wheel_2[slot].append(entry)

    def __len__(self) -> int:
        return self.size()

    def __repr__(self) -> str:
        return f"TimingWheel(size={self.size()}, ticks={self._tick_total_count})"
