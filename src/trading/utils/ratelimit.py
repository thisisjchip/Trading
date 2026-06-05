"""Rate limiting and retry-with-backoff helpers.

Kraken returns HTTP 429 with a ``Retry-After`` header when you exceed limits,
and futures uses a token-bucket "cost" model. We keep this lightweight and
dependency-free so adapters can wrap any callable.
"""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Callable, Optional, Type, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class TokenBucket:
    """Simple thread-safe token bucket for client-side throttling.

    ``rate`` tokens are added per second up to ``capacity``. Each call consumes
    one (or more) tokens, blocking until enough are available.
    """

    rate: float
    capacity: float
    _tokens: float = field(init=False)
    _last: float = field(init=False)
    _lock: Lock = field(init=False, default_factory=Lock)

    def __post_init__(self) -> None:
        self._tokens = self.capacity
        self._last = time.monotonic()

    def acquire(self, tokens: float = 1.0) -> None:
        with self._lock:
            while True:
                now = time.monotonic()
                elapsed = now - self._last
                self._last = now
                self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return
                deficit = tokens - self._tokens
                sleep_for = deficit / self.rate
                time.sleep(sleep_for)


class RateLimitError(Exception):
    """Raised by adapters when the exchange signals a 429 / rate limit.

    Carry ``retry_after`` (seconds) when the server provides it.
    """

    def __init__(self, message: str, retry_after: Optional[float] = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


def retry_with_backoff(
    func: Callable[[], T],
    *,
    max_attempts: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    retry_on: tuple[Type[BaseException], ...] = (RateLimitError,),
    jitter: bool = True,
) -> T:
    """Call ``func`` retrying on the given exceptions with exponential backoff.

    Honours :class:`RateLimitError.retry_after` when present.
    """
    attempt = 0
    while True:
        attempt += 1
        try:
            return func()
        except retry_on as exc:  # type: ignore[misc]
            if attempt >= max_attempts:
                logger.error("Giving up after %d attempts: %s", attempt, exc)
                raise
            delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
            retry_after = getattr(exc, "retry_after", None)
            if retry_after is not None:
                delay = max(delay, float(retry_after))
            if jitter:
                delay += random.uniform(0, base_delay)
            logger.warning(
                "Attempt %d/%d failed (%s); backing off %.2fs",
                attempt, max_attempts, exc, delay,
            )
            time.sleep(delay)
