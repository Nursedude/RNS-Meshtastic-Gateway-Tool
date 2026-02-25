"""Tests for src/utils/circuit_breaker.py — circuit breaker state machine."""
import threading
import time

import pytest

from src.utils.circuit_breaker import CircuitBreaker, State


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
