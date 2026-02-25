"""
Reconnect strategy with exponential backoff, jitter, and slow-start recovery.

Extracted from launcher.py inline logic, inspired by MeshForge's
gateway/reconnect.py dataclass pattern. Provides reusable, testable
reconnection logic for any subsystem (Meshtastic, RNS, MQTT, etc.).

Slow-start recovery (MeshForge pattern): after a reconnect succeeds,
throughput ramps from 10% to 100% over a configurable duration to
prevent flooding a recovering connection.
"""
import random
import threading
import time
from dataclasses import dataclass, field


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
