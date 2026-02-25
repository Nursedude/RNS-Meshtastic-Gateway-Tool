"""Tests for src/utils/reconnect.py — ReconnectStrategy."""
import threading
import time

import pytest

from src.utils.reconnect import ReconnectStrategy


class TestGetDelay:
    def test_first_attempt_near_initial_delay(self):
        """Attempt 0 should produce a delay near the initial_delay."""
        strategy = ReconnectStrategy(initial_delay=2.0, jitter=0.0)
        assert strategy.get_delay(0) == 2.0

    def test_exponential_growth(self):
        """Delay should grow exponentially with attempt number."""
        strategy = ReconnectStrategy(initial_delay=1.0, multiplier=2.0, jitter=0.0)
        assert strategy.get_delay(0) == 1.0
        assert strategy.get_delay(1) == 2.0
        assert strategy.get_delay(2) == 4.0
        assert strategy.get_delay(3) == 8.0

    def test_max_delay_cap(self):
        """Delay should never exceed max_delay."""
        strategy = ReconnectStrategy(initial_delay=1.0, multiplier=2.0, max_delay=10.0, jitter=0.0)
        assert strategy.get_delay(100) == 10.0

    def test_jitter_varies_delay(self):
        """With jitter > 0, repeated calls should produce varying delays."""
        strategy = ReconnectStrategy(initial_delay=10.0, jitter=0.5)
        delays = [strategy.get_delay(0) for _ in range(50)]
        # With 50% jitter on 10s, delays range from 5 to 15
        assert min(delays) < 10.0
        assert max(delays) > 10.0

    def test_default_uses_internal_counter(self):
        """get_delay() with no arg should use the internal attempt counter."""
        strategy = ReconnectStrategy(initial_delay=1.0, multiplier=2.0, jitter=0.0)
        assert strategy.get_delay() == 1.0  # attempt 0
        strategy.record_failure()
        assert strategy.get_delay() == 2.0  # attempt 1


class TestShouldRetry:
    def test_within_limit(self):
        strategy = ReconnectStrategy(max_attempts=3)
        assert strategy.should_retry() is True

    def test_at_limit(self):
        strategy = ReconnectStrategy(max_attempts=2)
        strategy.record_failure()
        strategy.record_failure()
        assert strategy.should_retry() is False

    def test_reset_allows_retry(self):
        strategy = ReconnectStrategy(max_attempts=1)
        strategy.record_failure()
        assert strategy.should_retry() is False
        strategy.reset()
        assert strategy.should_retry() is True


class TestRecordSuccessFailure:
    def test_failure_increments(self):
        strategy = ReconnectStrategy()
        assert strategy.attempts == 0
        strategy.record_failure()
        assert strategy.attempts == 1
        strategy.record_failure()
        assert strategy.attempts == 2

    def test_success_resets(self):
        strategy = ReconnectStrategy()
        strategy.record_failure()
        strategy.record_failure()
        assert strategy.attempts == 2
        strategy.record_success()
        assert strategy.attempts == 0


class TestWait:
    def test_wait_returns_true_when_not_interrupted(self):
        """wait() should return True when timeout expires normally."""
        event = threading.Event()
        strategy = ReconnectStrategy(initial_delay=0.01, jitter=0.0)
        result = strategy.wait(event, timeout=0.01)
        assert result is True

    def test_wait_returns_false_when_interrupted(self):
        """wait() should return False when stop_event is already set."""
        event = threading.Event()
        event.set()
        strategy = ReconnectStrategy()
        result = strategy.wait(event, timeout=5.0)
        assert result is False

    def test_wait_uses_get_delay_by_default(self):
        """wait() with negative timeout should use get_delay()."""
        event = threading.Event()
        strategy = ReconnectStrategy(initial_delay=0.01, jitter=0.0)
        start = time.monotonic()
        strategy.wait(event)
        elapsed = time.monotonic() - start
        assert elapsed < 1.0  # Should be ~0.01s, not the default 2s


class TestFactoryMethods:
    def test_for_meshtastic(self):
        strategy = ReconnectStrategy.for_meshtastic()
        assert strategy.initial_delay == 2.0
        assert strategy.max_attempts == 10
        assert strategy.multiplier == 2.0

    def test_for_rns(self):
        strategy = ReconnectStrategy.for_rns()
        assert strategy.initial_delay == 1.0
        assert strategy.max_attempts == 20
        assert strategy.multiplier == 1.5

    def test_factories_return_independent_instances(self):
        a = ReconnectStrategy.for_meshtastic()
        b = ReconnectStrategy.for_meshtastic()
        a.record_failure()
        assert a.attempts == 1
        assert b.attempts == 0


class TestSlowStart:
    def test_throughput_factor_starts_low_after_recovery(self):
        """After reconnect, throughput factor should start near 0.1."""
        strategy = ReconnectStrategy(slow_start_duration=1.0)
        strategy.record_failure()
        strategy.record_success()  # Triggers slow-start
        factor = strategy.throughput_factor()
        assert 0.0 < factor < 0.5  # Should be near 0.1

    def test_throughput_factor_reaches_1_after_duration(self):
        """After slow_start_duration elapses, factor should be 1.0."""
        strategy = ReconnectStrategy(slow_start_duration=0.05)
        strategy.record_failure()
        strategy.record_success()
        time.sleep(0.06)
        assert strategy.throughput_factor() == 1.0

    def test_throughput_factor_1_when_no_recovery(self):
        """Without prior failure, throughput should be 1.0."""
        strategy = ReconnectStrategy()
        assert strategy.throughput_factor() == 1.0

    def test_inter_packet_delay_during_slow_start(self):
        """inter_packet_delay should be positive during slow-start."""
        strategy = ReconnectStrategy(slow_start_duration=1.0)
        strategy.record_failure()
        strategy.record_success()
        delay = strategy.inter_packet_delay()
        assert delay > 0.0

    def test_inter_packet_delay_zero_at_full_throughput(self):
        """inter_packet_delay should be 0 when not in slow-start."""
        strategy = ReconnectStrategy()
        assert strategy.inter_packet_delay() == 0.0

    def test_reset_clears_slow_start(self):
        """reset() should clear slow-start state."""
        strategy = ReconnectStrategy(slow_start_duration=60.0)
        strategy.record_failure()
        strategy.record_success()
        assert strategy.throughput_factor() < 1.0
        strategy.reset()
        assert strategy.throughput_factor() == 1.0
