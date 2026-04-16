"""Tests for src/utils/circuit_breaker.py — circuit breaker state machine."""
import threading
import time

import pytest

from src.utils.circuit_breaker import CircuitBreaker, State, circuit_protected


class TestInitialState:
    def test_starts_closed(self):
        cb = CircuitBreaker()
        assert cb.state is State.CLOSED

    def test_starts_with_zero_failures(self):
        cb = CircuitBreaker()
        assert cb.failures == 0


class TestAllowRequest:
    def test_allows_when_closed(self):
        cb = CircuitBreaker()
        assert cb.allow_request() is True

    def test_blocks_when_open(self):
        cb = CircuitBreaker(failure_threshold=2)
        cb.record_failure()
        cb.record_failure()
        assert cb.state is State.OPEN
        assert cb.allow_request() is False

    def test_allows_when_half_open(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.01)
        cb.record_failure()
        assert cb.state is State.OPEN
        time.sleep(0.02)
        assert cb.state is State.HALF_OPEN
        assert cb.allow_request() is True


class TestStateTransitions:
    def test_closed_to_open_on_threshold(self):
        cb = CircuitBreaker(failure_threshold=3)
        for _ in range(3):
            cb.record_failure()
        assert cb.state is State.OPEN

    def test_below_threshold_stays_closed(self):
        cb = CircuitBreaker(failure_threshold=5)
        cb.record_failure()
        cb.record_failure()
        assert cb.state is State.CLOSED

    def test_open_to_half_open_after_timeout(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.01)
        cb.record_failure()
        assert cb.state is State.OPEN
        time.sleep(0.02)
        assert cb.state is State.HALF_OPEN

    def test_half_open_to_closed_on_success(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.01)
        cb.record_failure()
        time.sleep(0.02)
        assert cb.state is State.HALF_OPEN
        cb.record_success()
        assert cb.state is State.CLOSED

    def test_half_open_to_open_on_failure(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.01)
        cb.record_failure()
        time.sleep(0.02)
        assert cb.state is State.HALF_OPEN
        cb.record_failure()
        assert cb.state is State.OPEN

    def test_success_resets_failure_count(self):
        cb = CircuitBreaker(failure_threshold=5)
        cb.record_failure()
        cb.record_failure()
        assert cb.failures == 2
        cb.record_success()
        assert cb.failures == 0


class TestReset:
    def test_reset_from_open(self):
        cb = CircuitBreaker(failure_threshold=1)
        cb.record_failure()
        assert cb.state is State.OPEN
        cb.reset()
        assert cb.state is State.CLOSED
        assert cb.failures == 0

    def test_reset_from_half_open(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.01)
        cb.record_failure()
        time.sleep(0.02)
        assert cb.state is State.HALF_OPEN
        cb.reset()
        assert cb.state is State.CLOSED


class TestStatistics:
    """Verify statistics tracking (MeshForge pattern)."""

    def test_initial_stats(self):
        cb = CircuitBreaker(name="test")
        stats = cb.get_stats()
        assert stats["name"] == "test"
        assert stats["total_successes"] == 0
        assert stats["total_failures"] == 0
        assert stats["total_trips"] == 0

    def test_stats_track_successes(self):
        cb = CircuitBreaker()
        cb.record_success()
        cb.record_success()
        stats = cb.get_stats()
        assert stats["total_successes"] == 2

    def test_stats_track_failures(self):
        cb = CircuitBreaker(failure_threshold=10)
        cb.record_failure()
        cb.record_failure()
        stats = cb.get_stats()
        assert stats["total_failures"] == 2
        assert stats["consecutive_failures"] == 2

    def test_stats_track_trips(self):
        cb = CircuitBreaker(failure_threshold=2)
        cb.record_failure()
        cb.record_failure()
        stats = cb.get_stats()
        assert stats["total_trips"] == 1

    def test_half_open_success_tracked(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.01)
        cb.record_failure()
        time.sleep(0.02)
        assert cb.state is State.HALF_OPEN
        cb.record_success()
        stats = cb.get_stats()
        assert stats["half_open_successes"] == 1

    def test_stats_timestamps_are_wall_clock(self):
        """Exposed timestamps should be Unix epoch, not time.monotonic()."""
        cb = CircuitBreaker(failure_threshold=1)
        before = time.time()
        cb.record_failure()
        after = time.time()
        stats = cb.get_stats()
        # last_failure_time and last_trip_time should fall within [before, after]
        assert before <= stats["last_failure_time"] <= after
        assert before <= stats["last_trip_time"] <= after


class TestCircuitProtectedDecorator:
    """Verify the @circuit_protected decorator."""

    def test_allows_when_closed(self):
        cb = CircuitBreaker()
        calls = []

        @circuit_protected(cb)
        def do_work():
            calls.append(1)
            return "ok"

        assert do_work() == "ok"
        assert len(calls) == 1
        assert cb.get_stats()["total_successes"] == 1

    def test_blocks_when_open(self):
        cb = CircuitBreaker(failure_threshold=1)
        cb.record_failure()
        assert cb.state is State.OPEN

        @circuit_protected(cb)
        def do_work():
            return "ok"

        assert do_work() is None

    def test_fallback_when_open(self):
        cb = CircuitBreaker(failure_threshold=1)
        cb.record_failure()

        @circuit_protected(cb, fallback=lambda: "fallback")
        def do_work():
            return "ok"

        assert do_work() == "fallback"

    def test_records_failure_on_exception(self):
        cb = CircuitBreaker(failure_threshold=10)

        @circuit_protected(cb)
        def do_work():
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            do_work()

        assert cb.get_stats()["total_failures"] == 1


class TestThreadSafety:
    def test_concurrent_failures(self):
        """Multiple threads recording failures should not corrupt state."""
        cb = CircuitBreaker(failure_threshold=100)
        errors = []

        def fail_many():
            try:
                for _ in range(50):
                    cb.record_failure()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=fail_many) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert cb.failures == 200
        assert cb.state is State.OPEN
