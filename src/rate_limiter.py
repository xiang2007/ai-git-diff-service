from collections import deque
from collections.abc import Callable
from math import ceil
from threading import Lock
from time import monotonic


class SlidingWindowRateLimiter:
    """Thread-safe fixed-capacity limiter over a rolling time window."""

    def __init__(self, limit: int, window_seconds: float, *, clock: Callable[[], float] = monotonic) -> None:
        if limit <= 0:
            raise ValueError("limit must be positive")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")

        self.limit = limit
        self.window_seconds = window_seconds
        self._clock = clock
        self._timestamps: deque[float] = deque()
        self._lock = Lock()

    def acquire(self) -> int | None:
        """Record an allowed request, or return Retry-After seconds if denied."""
        now = self._clock()
        cutoff = now - self.window_seconds

        with self._lock:
            while self._timestamps and self._timestamps[0] <= cutoff:
                self._timestamps.popleft()

            if len(self._timestamps) >= self.limit:
                retry_after = self._timestamps[0] + self.window_seconds - now
                return max(1, ceil(retry_after))

            self._timestamps.append(now)
            return None
