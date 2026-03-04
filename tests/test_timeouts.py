"""Tests for src/utils/timeouts.py — centralized timeout constants."""

from src.utils.timeouts import (
    HEALTH_CHECK_INTERVAL,
    SUBPROCESS_QUICK,
    SUBPROCESS_DEFAULT,
    TCP_CONNECT,
    TCP_PREFLIGHT,
    CIRCUIT_RECOVERY,
    CIRCUIT_FAILURE_THRESHOLD,
    RECONNECT_INITIAL_DELAY,
    RECONNECT_MAX_DELAY,
    RECONNECT_MULTIPLIER,
    RECONNECT_JITTER,
    RECONNECT_MAX_ATTEMPTS,
    SLOW_START_DURATION,
    THREAD_JOIN,
    THREAD_JOIN_LONG,
    TX_QUEUE_MAXSIZE,
    TX_QUEUE_POLL,
    DASHBOARD_REFRESH,
)


class TestTimeoutConstants:
    """Verify all timeout constants exist and have sane values."""

    def test_health_check_interval_positive(self):
        assert HEALTH_CHECK_INTERVAL > 0

    def test_subprocess_quick_positive(self):
        assert SUBPROCESS_QUICK > 0

    def test_subprocess_default_gt_quick(self):
        assert SUBPROCESS_DEFAULT > SUBPROCESS_QUICK

    def test_tcp_connect_positive(self):
        assert TCP_CONNECT > 0

    def test_tcp_preflight_positive(self):
        assert TCP_PREFLIGHT > 0

    def test_circuit_recovery_positive(self):
        assert CIRCUIT_RECOVERY > 0

    def test_circuit_failure_threshold_positive(self):
        assert CIRCUIT_FAILURE_THRESHOLD > 0

    def test_reconnect_initial_delay_positive(self):
        assert RECONNECT_INITIAL_DELAY > 0

    def test_reconnect_max_delay_gt_initial(self):
        assert RECONNECT_MAX_DELAY > RECONNECT_INITIAL_DELAY

    def test_reconnect_multiplier_gt_one(self):
        assert RECONNECT_MULTIPLIER > 1.0

    def test_reconnect_jitter_bounded(self):
        assert 0 < RECONNECT_JITTER < 1.0

    def test_reconnect_max_attempts_positive(self):
        assert RECONNECT_MAX_ATTEMPTS > 0

    def test_slow_start_duration_positive(self):
        assert SLOW_START_DURATION > 0

    def test_thread_join_positive(self):
        assert THREAD_JOIN > 0

    def test_thread_join_long_gt_short(self):
        assert THREAD_JOIN_LONG > THREAD_JOIN

    def test_tx_queue_maxsize_positive(self):
        assert TX_QUEUE_MAXSIZE > 0

    def test_tx_queue_poll_positive(self):
        assert TX_QUEUE_POLL > 0

    def test_dashboard_refresh_positive(self):
        assert DASHBOARD_REFRESH > 0

    def test_all_are_numeric(self):
        """All constants should be int or float."""
        for val in [
            HEALTH_CHECK_INTERVAL, SUBPROCESS_QUICK, SUBPROCESS_DEFAULT,
            TCP_CONNECT, TCP_PREFLIGHT, CIRCUIT_RECOVERY,
            CIRCUIT_FAILURE_THRESHOLD, RECONNECT_INITIAL_DELAY,
            RECONNECT_MAX_DELAY, RECONNECT_MULTIPLIER, RECONNECT_JITTER,
            RECONNECT_MAX_ATTEMPTS, SLOW_START_DURATION, THREAD_JOIN,
            THREAD_JOIN_LONG, TX_QUEUE_MAXSIZE, TX_QUEUE_POLL,
            DASHBOARD_REFRESH,
        ]:
            assert isinstance(val, (int, float)), f"{val!r} is not numeric"
