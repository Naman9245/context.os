"""Keep requests under a free tier's requests-per-minute quota."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable


class RateLimiter:
    """Spaces calls evenly: at most `requests_per_minute`, never in bursts.

    Even spacing (rather than a burst-then-wait bucket) is what free tiers
    tolerate best - they tend to count short windows. 0 disables limiting.
    """

    def __init__(
        self,
        requests_per_minute: int,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.interval = 60.0 / requests_per_minute if requests_per_minute > 0 else 0.0
        self._clock = clock
        self._sleep = sleep
        self._next_free = 0.0
        self._lock = threading.Lock()

    def acquire(self) -> None:
        if self.interval == 0:
            return
        with self._lock:
            now = self._clock()
            start = max(now, self._next_free)
            self._next_free = start + self.interval
        wait = start - now
        if wait > 0:
            self._sleep(wait)
