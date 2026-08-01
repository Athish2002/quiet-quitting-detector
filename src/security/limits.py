# src/security/limits.py
# Rate limiting, body-size caps and idempotency keys (spec 7, blocker B7).
#
# These three are grouped because they defend the same thing from three angles:
# a caller who can make the server do unbounded work, hold unbounded memory, or
# corrupt a week of data by retrying.
#
# Rate limiting matters here more than in a typical CRUD service, because the
# expensive routes are the ones that call an LLM. An unauthenticated flood
# against `/api/run` in the old code would have burned the project's API quota
# and, past that, its owner's money. That is why the limits are per identity AND
# per IP: per-IP alone is defeated by a proxy, per-identity alone is defeated by
# never authenticating.
#
# In-process storage is a deliberate, stated limitation. With more than one
# worker each holds its own counters, so the effective limit multiplies by the
# worker count. Redis is the fix and it belongs with O1; what is here is
# honestly described in docs/LIMITATIONS.md rather than presented as complete.

from __future__ import annotations

import threading
import time
from collections import deque

#: Budget for state-changing requests, per identity and per IP.
DEFAULT_LIMIT = 30
DEFAULT_WINDOW_SECONDS = 60

#: Budget for reads. Much higher, and deliberately so.
#:
#: One 30-per-minute bucket for everything looked prudent and was wrong: the
#: dashboard makes three or four calls per page, and polls run progress while a
#: pipeline is going. A single operator clicking through four pages tripped a
#: 429 -- found by the Playwright suite, where a different test failed on each
#: run until the cause was traced here rather than dismissed as flake.
#:
#: Reads are cheap: a file read and some arithmetic, no model call. The limit
#: that protects the API quota and the owner's money is EXPENSIVE_LIMIT below,
#: and that one stays tight. A read limit low enough to break ordinary use does
#: not buy security, it buys a tool people work around.
READ_LIMIT = 300
READ_WINDOW_SECONDS = 60

#: Tighter budget for routes that call a model or run the pipeline.
EXPENSIVE_LIMIT = 6
EXPENSIVE_WINDOW_SECONDS = 60

#: Hard cap on any request body. Generous for a weekly metrics CSV, small enough
#: that a single request cannot exhaust memory.
MAX_BODY_BYTES = 5 * 1024 * 1024

#: How many idempotency keys to remember, and for how long.
IDEMPOTENCY_TTL_SECONDS = 24 * 3600
MAX_IDEMPOTENCY_KEYS = 10_000


class RateLimiter:
    """Sliding-window limiter, keyed by an arbitrary identity string.

    A sliding window rather than a fixed one because a fixed window lets a
    caller send a full budget at 11:59:59 and another at 12:00:00 -- double the
    intended rate, at the worst possible moment, against the routes that cost
    money.
    """

    def __init__(
        self, limit: int = DEFAULT_LIMIT, window: int = DEFAULT_WINDOW_SECONDS
    ) -> None:
        self.limit = limit
        self.window = window
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, identity: str, *, now: float | None = None) -> tuple[bool, int]:
        """Record an attempt. Returns (allowed, seconds until retry)."""
        moment = time.monotonic() if now is None else now

        with self._lock:
            hits = self._hits.setdefault(identity, deque())
            while hits and moment - hits[0] > self.window:
                hits.popleft()

            if len(hits) >= self.limit:
                retry_after = int(self.window - (moment - hits[0])) + 1
                return False, max(1, retry_after)

            hits.append(moment)
            return True, 0

    def reset(self, identity: str | None = None) -> None:
        with self._lock:
            if identity is None:
                self._hits.clear()
            else:
                self._hits.pop(identity, None)


class IdempotencyStore:
    """Remembers which idempotency keys have been seen, and what they returned.

    Without this, a webhook sender that times out and retries -- which is what
    every webhook sender does -- appends a second copy of a week's data. The
    result is not an error anybody sees: it is one employee's metrics silently
    doubled, which reads as a person whose output suddenly improved, or, in the
    other direction, as a week that never happened.
    """

    def __init__(self, ttl: int = IDEMPOTENCY_TTL_SECONDS) -> None:
        self.ttl = ttl
        self._seen: dict[str, tuple[float, dict]] = {}
        self._lock = threading.Lock()

    def _evict(self, now: float) -> None:
        expired = [k for k, (ts, _) in self._seen.items() if now - ts > self.ttl]
        for key in expired:
            del self._seen[key]

        # Bound memory even if nothing has expired: an attacker sending unique
        # keys must not be able to grow this without limit.
        if len(self._seen) > MAX_IDEMPOTENCY_KEYS:
            for key in sorted(self._seen, key=lambda k: self._seen[k][0])[
                : len(self._seen) - MAX_IDEMPOTENCY_KEYS
            ]:
                del self._seen[key]

    def seen(self, key: str) -> dict | None:
        """The stored response for this key, or None if it is new."""
        now = time.monotonic()
        with self._lock:
            self._evict(now)
            entry = self._seen.get(key)
            return entry[1] if entry else None

    def remember(self, key: str, response: dict) -> None:
        now = time.monotonic()
        with self._lock:
            # Insert first, then evict. Evicting beforehand leaves room for the
            # new entry to push the store one over its cap -- which is only one
            # entry, but "bounded" that is off by one is not bounded, and the
            # bound is the whole reason this store is safe to expose to callers
            # who choose their own keys.
            self._seen[key] = (now, response)
            self._evict(now)

    def reset(self) -> None:
        with self._lock:
            self._seen.clear()
