"""Retry policies and circuit breaker for LLM calls.

Provides configurable retry with exponential backoff and jitter,
plus circuit breaker to prevent cascade failures.
"""

import asyncio
import threading
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from enum import Enum
from typing import Any, TypeVar

import structlog

logger = structlog.get_logger(__name__)

T = TypeVar("T")


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject calls
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class RetryPolicy:
    """Configuration for retry behavior."""

    max_attempts: int = 3
    base_delay: float = 1.0  # seconds
    max_delay: float = 60.0  # seconds
    exponential_base: float = 2.0
    jitter: float = 0.1  # Jitter factor (0-1)
    retryable_exceptions: tuple[type[Exception], ...] = (ConnectionError, TimeoutError, IOError)

    def get_delay(self, attempt: int) -> float:
        """Calculate delay for attempt with exponential backoff and jitter."""
        import random

        delay = min(self.base_delay * (self.exponential_base**attempt), self.max_delay)
        jitter_amount = delay * self.jitter * random.random()
        return delay + jitter_amount


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open."""

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class CircuitBreaker:
    """Circuit breaker to prevent cascade failures.

    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Too many failures, requests rejected immediately
    - HALF_OPEN: Testing recovery, limited requests allowed
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        success_threshold: int = 2,
        recovery_timeout: float = 60.0,
        expected_exception: type[Exception] = Exception,
    ):
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float | None = None
        self._lock = threading.RLock()

    @property
    def state(self) -> CircuitState:
        """Get current circuit state, transitioning if needed."""
        with self._lock:
            if (
                self._state == CircuitState.OPEN
                and self._last_failure_time
                and (time.time() - self._last_failure_time >= self.recovery_timeout)
            ):
                self._state = CircuitState.HALF_OPEN
                self._success_count = 0
                logger.info("Circuit breaker entering HALF_OPEN state")
            return self._state

    def can_execute(self) -> bool:
        """Check if request can be executed."""
        return self.state != CircuitState.OPEN

    def record_success(self) -> None:
        """Record successful call."""
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.success_threshold:
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    logger.info("Circuit breaker CLOSED after successful recovery")
            elif self._state == CircuitState.CLOSED:
                self._failure_count = 0  # Reset failure count on success

    def record_failure(self) -> None:
        """Record failed call."""
        with self._lock:
            self._last_failure_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                # Any failure in half-open reopens the circuit
                self._state = CircuitState.OPEN
                self._failure_count = 0
                logger.warning("Circuit breaker OPEN after HALF_OPEN failure")
            elif self._state == CircuitState.CLOSED:
                self._failure_count += 1
                if self._failure_count >= self.failure_threshold:
                    self._state = CircuitState.OPEN
                    logger.warning(
                        "Circuit breaker OPEN after threshold reached",
                        failures=self._failure_count,
                        threshold=self.failure_threshold,
                    )

    def get_stats(self) -> dict:
        """Get circuit breaker statistics."""
        with self._lock:
            return {
                "state": self._state.value,
                "failure_count": self._failure_count,
                "success_count": self._success_count,
                "failure_threshold": self.failure_threshold,
                "success_threshold": self.success_threshold,
                "recovery_timeout": self.recovery_timeout,
            }

    def reset(self) -> None:
        """Manually reset circuit breaker to closed state."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._last_failure_time = None


async def retry_with_policy[T](func: Callable[..., Coroutine[Any, Any, T]], policy: RetryPolicy, *args, **kwargs) -> T:
    """Execute function with retry policy.

    Args:
        func: Async function to execute
        policy: Retry policy configuration
        *args: Positional arguments to pass to func
        **kwargs: Keyword arguments to pass to func

    Returns:
        Result of func

    Raises:
        Last exception if all retries exhausted

    """
    last_exception: BaseException | None = None

    for attempt in range(policy.max_attempts):
        try:
            return await func(*args, **kwargs)
        except policy.retryable_exceptions as e:
            last_exception = e
            if attempt < policy.max_attempts - 1:
                delay = policy.get_delay(attempt)
                logger.warning(
                    "Retry attempt failed, retrying",
                    attempt=attempt + 1,
                    max_attempts=policy.max_attempts,
                    delay=delay,
                    error=str(e),
                )
                await asyncio.sleep(delay)
            else:
                logger.exception("All retry attempts exhausted", attempts=policy.max_attempts, error=str(e))

    if last_exception is None:
        msg = "Retry policy exhausted with no exception"
        raise RuntimeError(msg)
    raise last_exception
