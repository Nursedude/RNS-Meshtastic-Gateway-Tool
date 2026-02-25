"""
Lightweight circuit breaker for the gateway transmit path.

Inspired by MeshForge's gateway/circuit_breaker.py but simplified
for a single-radio gateway.  Prevents hammering a dead connection
by tracking consecutive failures and temporarily halting requests.

States:
    CLOSED    → Normal operation; requests flow through.
    OPEN      → Too many failures; requests are rejected.
    HALF_OPEN → Recovery probe; one request allowed to test.
"""
import enum
import threading
import time
from dataclasses import dataclass, field


class State(enum.Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    """Thread-safe circuit breaker with configurable thresholds."""

    failure_threshold: int = 5
    recovery_timeout: float = 30.0

    _state: State = field(default=State.CLOSED, repr=False, compare=False)
    _failures: int = field(default=0, repr=False, compare=False)
    _opened_at: float = field(default=0.0, repr=False, compare=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

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
            self._failures = 0
            self._state = State.CLOSED

    def record_failure(self) -> None:
        """Record a failed operation — may trip the breaker open."""
        with self._lock:
            self._failures += 1
            if self._state is State.HALF_OPEN:
                # Probe failed — reopen immediately
                self._state = State.OPEN
                self._opened_at = time.monotonic()
            elif self._failures >= self.failure_threshold:
                self._state = State.OPEN
                self._opened_at = time.monotonic()

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
