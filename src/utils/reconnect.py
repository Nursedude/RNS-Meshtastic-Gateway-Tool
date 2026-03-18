"""
Reconnect strategy with exponential backoff, jitter, and slow-start recovery.

Extracted from launcher.py inline logic, inspired by MeshForge's
gateway/reconnect.py dataclass pattern. Provides reusable, testable
reconnection logic for any subsystem (Meshtastic, RNS, MQTT, etc.).

Slow-start recovery (MeshForge pattern): after a reconnect succeeds,
throughput ramps from 10% to 100% over a configurable duration to
prevent flooding a recovering connection.

SlowStartRecovery (MeshForge PR series): a standalone class for
managing the slow-start ramp independently, with factory methods
tuned for different connection types.
"""
import logging
import random
import threading
import time
from dataclasses import dataclass, field

log = logging.getLogger("reconnect")


@dataclass
class ReconnectStrategy:
    """Manages reconnection attempts with exponential backoff + jitter.

    Usage:
        strategy = ReconnectStrategy.for_meshtastic()
        stop_event = threading.Event()

        while strategy.should_retry():
            strategy.wait(stop_event)
            if try_connect():
                strategy.record_success()
                break
            strategy.record_failure()
    """
    initial_delay: float = 2.0
    max_delay: float = 60.0
    multiplier: float = 2.0
    jitter: float = 0.15
    max_attempts: int = 10
    slow_start_duration: float = 30.0

    # Mutable state (not part of __init__ comparison)
    _attempts: int = field(default=0, repr=False, compare=False)
    _recovery_start: float = field(default=0.0, repr=False, compare=False)

    def get_delay(self, attempt: int = -1) -> float:
        """Calculate delay for the given attempt with exponential backoff + jitter.

        Args:
            attempt: Attempt number (0-based). Defaults to current internal count.

        Returns:
            Delay in seconds with jitter applied.
        """
        if attempt < 0:
            attempt = self._attempts
        base = min(self.initial_delay * (self.multiplier ** attempt), self.max_delay)
        jitter_range = base * self.jitter
        return base + random.uniform(-jitter_range, jitter_range)

    def should_retry(self) -> bool:
        """Check whether more retry attempts are available."""
        return self._attempts < self.max_attempts

    def record_failure(self) -> None:
        """Record a failed connection attempt."""
        self._attempts += 1

    def record_success(self) -> None:
        """Reset attempt counter and begin slow-start recovery window."""
        if self._attempts > 0:
            # Only start slow-start if we were actually recovering
            self._recovery_start = time.monotonic()
        self._attempts = 0

    @property
    def attempts(self) -> int:
        """Current attempt count."""
        return self._attempts

    def wait(self, stop_event: threading.Event, timeout: float = -1) -> bool:
        """Sleep for the backoff delay, interruptible via stop_event.

        Args:
            stop_event: Threading event; if set, wait returns immediately.
            timeout: Override delay (seconds). Negative uses get_delay().

        Returns:
            True if the wait completed normally, False if interrupted.
        """
        delay = timeout if timeout >= 0 else self.get_delay()
        return not stop_event.wait(delay)

    def throughput_factor(self) -> float:
        """Return current throughput factor (0.1 → 1.0) during slow-start.

        After a reconnect, throughput ramps linearly from 10% to 100%
        over ``slow_start_duration`` seconds.  Returns 1.0 when no
        slow-start is active.
        """
        if self._recovery_start <= 0 or self.slow_start_duration <= 0:
            return 1.0
        elapsed = time.monotonic() - self._recovery_start
        if elapsed >= self.slow_start_duration:
            self._recovery_start = 0.0
            return 1.0
        # Linear ramp from 0.1 to 1.0
        return 0.1 + 0.9 * (elapsed / self.slow_start_duration)

    def inter_packet_delay(self) -> float:
        """Delay in seconds to insert between packets during slow-start.

        Returns 0.0 when at full throughput.  Maximum delay at start
        of recovery is ~0.9s, ramping down to 0.
        """
        factor = self.throughput_factor()
        if factor >= 1.0:
            return 0.0
        # Inverse: low factor → high delay
        return max(0.0, (1.0 - factor) * 1.0)

    def execute_with_retry(self, fn, stop_event=None, on_success=None, on_failure=None):
        """Execute *fn* with retry using this strategy's backoff.

        Args:
            fn:         Callable to attempt.  Must raise on failure.
            stop_event: Optional ``threading.Event``; if set, abort early.
            on_success: Optional ``callback(result)`` on first success.
            on_failure: Optional ``callback(exception)`` on each failure.

        Returns:
            The return value of *fn()* on success.

        Raises:
            The last exception if retries are exhausted, or
            ``ConnectionError`` if interrupted by *stop_event*.
        """
        _stop = stop_event or threading.Event()
        last_exc = None
        while self.should_retry():
            if _stop.is_set():
                break
            try:
                result = fn()
                self.record_success()
                if on_success:
                    on_success(result)
                return result
            except Exception as exc:
                last_exc = exc
                self.record_failure()
                if on_failure:
                    on_failure(exc)
                if self.should_retry():
                    self.wait(_stop)
        if last_exc:
            raise last_exc
        raise ConnectionError("Retry interrupted")

    def reset(self) -> None:
        """Explicitly reset the attempt counter and slow-start state."""
        self._attempts = 0
        self._recovery_start = 0.0

    @classmethod
    def for_meshtastic(cls) -> 'ReconnectStrategy':
        """Factory: tuned defaults for Meshtastic radio reconnection."""
        return cls(
            initial_delay=2.0,
            max_delay=60.0,
            multiplier=2.0,
            jitter=0.15,
            max_attempts=10,
        )

    @classmethod
    def for_rns(cls) -> 'ReconnectStrategy':
        """Factory: tuned defaults for RNS transport reconnection."""
        return cls(
            initial_delay=1.0,
            max_delay=30.0,
            multiplier=1.5,
            jitter=0.10,
            max_attempts=20,
        )

    @classmethod
    def for_mqtt(cls) -> 'ReconnectStrategy':
        """Factory: tuned defaults for MQTT broker reconnection."""
        return cls(
            initial_delay=2.0,
            max_delay=60.0,
            multiplier=2.0,
            jitter=0.20,
            max_attempts=15,
            slow_start_duration=15.0,
        )


# ── Standalone Slow-Start Recovery (MeshForge pattern) ──────
@dataclass
class SlowStartRecovery:
    """NGINX slow_start pattern: gradually increase message throughput
    after service recovery to prevent flooding a fragile connection.

    Separated from ReconnectStrategy for independent use (e.g. after
    config reload, manual reconnect, or failover recovery).

    Usage::

        recovery = SlowStartRecovery.for_meshtastic()
        recovery.start()
        while sending:
            factor = recovery.get_throughput_multiplier()
            delay = recovery.get_adjusted_delay(base_delay)
            ...
    """
    duration: float = 30.0
    min_factor: float = 0.1

    _start_time: float = field(default=0.0, repr=False, compare=False)
    _active: bool = field(default=False, repr=False, compare=False)

    def start(self) -> None:
        """Begin the slow-start ramp."""
        self._start_time = time.monotonic()
        self._active = True
        log.debug("Slow-start recovery started (duration=%.1fs)", self.duration)

    def stop(self) -> None:
        """Cancel slow-start (e.g. on disconnect)."""
        self._active = False
        self._start_time = 0.0

    @property
    def is_active(self) -> bool:
        """True if slow-start is in progress."""
        if not self._active:
            return False
        if self.duration <= 0:
            return False
        elapsed = time.monotonic() - self._start_time
        if elapsed >= self.duration:
            self._active = False
            return False
        return True

    def get_throughput_multiplier(self) -> float:
        """Return current throughput multiplier (min_factor → 1.0).

        Linear ramp from min_factor to 1.0 over ``duration`` seconds.
        Returns 1.0 when not active.
        """
        if not self.is_active:
            return 1.0
        elapsed = time.monotonic() - self._start_time
        progress = min(1.0, elapsed / self.duration)
        return self.min_factor + (1.0 - self.min_factor) * progress

    def get_adjusted_delay(self, base_delay: float = 0.0) -> float:
        """Return delay adjusted for slow-start.

        During ramp-up, adds extra delay inversely proportional to
        throughput multiplier.  Returns ``base_delay`` when not active.
        """
        factor = self.get_throughput_multiplier()
        if factor >= 1.0:
            return base_delay
        # Extra delay: high at start, tapering to 0
        return base_delay + max(0.0, (1.0 - factor) * 1.0)

    def reset(self) -> None:
        """Reset slow-start state."""
        self._active = False
        self._start_time = 0.0

    @classmethod
    def for_meshtastic(cls) -> 'SlowStartRecovery':
        """Factory: tuned for Meshtastic radio recovery (30s ramp)."""
        return cls(duration=30.0, min_factor=0.1)

    @classmethod
    def for_rns(cls) -> 'SlowStartRecovery':
        """Factory: tuned for RNS transport recovery (15s ramp)."""
        return cls(duration=15.0, min_factor=0.2)

    @classmethod
    def for_mqtt(cls) -> 'SlowStartRecovery':
        """Factory: tuned for MQTT broker recovery (10s ramp)."""
        return cls(duration=10.0, min_factor=0.3)
