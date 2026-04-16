"""
Lightweight circuit breaker for the gateway transmit path.

Inspired by MeshForge's gateway/circuit_breaker.py.  Prevents hammering
a dead connection by tracking consecutive failures and temporarily
halting requests.

States:
    CLOSED    → Normal operation; requests flow through.
    OPEN      → Too many failures; requests are rejected.
    HALF_OPEN → Recovery probe; one request allowed to test.

Includes a ``@circuit_protected`` decorator (MeshForge pattern) for
wrapping functions with automatic circuit protection and a statistics
snapshot for monitoring dashboards.
"""
import enum
import functools
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

from src.utils.timeouts import CIRCUIT_RECOVERY, CIRCUIT_FAILURE_THRESHOLD

log = logging.getLogger("circuit_breaker")


class State(enum.Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    """Thread-safe circuit breaker with configurable thresholds and statistics.

    Statistics tracking (MeshForge pattern): records total successes,
    failures, and trips for monitoring dashboards.
    """

    failure_threshold: int = CIRCUIT_FAILURE_THRESHOLD
    recovery_timeout: float = CIRCUIT_RECOVERY
    name: str = ""

    _state: State = field(default=State.CLOSED, repr=False, compare=False)
    _failures: int = field(default=0, repr=False, compare=False)
    _opened_at: float = field(default=0.0, repr=False, compare=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    # Statistics (MeshForge pattern)
    _total_successes: int = field(default=0, repr=False, compare=False)
    _total_failures: int = field(default=0, repr=False, compare=False)
    _total_trips: int = field(default=0, repr=False, compare=False)
    _last_failure_time: float = field(default=0.0, repr=False, compare=False)
    _last_trip_time: float = field(default=0.0, repr=False, compare=False)
    _half_open_successes: int = field(default=0, repr=False, compare=False)

    @property
    def state(self) -> State:
        with self._lock:
            if self._state is State.OPEN:
                if time.monotonic() - self._opened_at >= self.recovery_timeout:
                    self._state = State.HALF_OPEN
            return self._state

    def allow_request(self) -> bool:
        """Check if a request should be allowed through."""
        current = self.state
        return current in (State.CLOSED, State.HALF_OPEN)

    def record_success(self) -> None:
        """Record a successful operation — close the breaker."""
        with self._lock:
            was_half_open = self._state is State.HALF_OPEN
            self._failures = 0
            self._state = State.CLOSED
            self._total_successes += 1
            if was_half_open:
                self._half_open_successes += 1

    def record_failure(self) -> None:
        """Record a failed operation — may trip the breaker open."""
        with self._lock:
            self._failures += 1
            self._total_failures += 1
            # Wall-clock time for dashboard consumers; monotonic for
            # interval math (see _opened_at).
            wall_now = time.time()
            mono_now = time.monotonic()
            self._last_failure_time = wall_now
            if self._state is State.HALF_OPEN:
                # Probe failed — reopen immediately
                self._state = State.OPEN
                self._opened_at = mono_now
                self._total_trips += 1
                self._last_trip_time = wall_now
            elif self._failures >= self.failure_threshold:
                self._state = State.OPEN
                self._opened_at = mono_now
                self._total_trips += 1
                self._last_trip_time = wall_now

    def reset(self) -> None:
        """Force-reset to CLOSED (e.g. after manual reconnect)."""
        with self._lock:
            self._failures = 0
            self._state = State.CLOSED
            self._opened_at = 0.0

    @property
    def failures(self) -> int:
        with self._lock:
            return self._failures

    def get_stats(self) -> Dict[str, Any]:
        """Return a statistics snapshot for dashboards (MeshForge pattern)."""
        with self._lock:
            return {
                "name": self.name,
                "state": self._state.value,
                "consecutive_failures": self._failures,
                "failure_threshold": self.failure_threshold,
                "recovery_timeout": self.recovery_timeout,
                "total_successes": self._total_successes,
                "total_failures": self._total_failures,
                "total_trips": self._total_trips,
                "half_open_successes": self._half_open_successes,
                "last_failure_time": self._last_failure_time,
                "last_trip_time": self._last_trip_time,
            }


def circuit_protected(
    breaker: CircuitBreaker,
    fallback: Optional[Callable] = None,
) -> Callable:
    """Decorator that wraps a function with circuit breaker protection.

    MeshForge pattern: simplifies adoption by automatically checking
    the breaker before calls and recording success/failure.

    Args:
        breaker:  The CircuitBreaker instance to use.
        fallback: Optional callable invoked when the breaker is OPEN.
                  Receives the same args as the wrapped function.

    Usage::

        cb = CircuitBreaker(name="radio")

        @circuit_protected(cb)
        def send_packet(data):
            radio.send(data)
    """
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            if not breaker.allow_request():
                log.warning("Circuit breaker %s OPEN — blocking %s",
                            breaker.name or "unnamed", fn.__name__)
                if fallback:
                    return fallback(*args, **kwargs)
                return None
            try:
                result = fn(*args, **kwargs)
                breaker.record_success()
                return result
            except Exception:
                breaker.record_failure()
                raise
        return wrapper
    return decorator
