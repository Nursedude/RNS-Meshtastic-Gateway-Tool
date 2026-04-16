"""Tests for src.utils.health_probe – ActiveHealthProbe hysteresis and lifecycle."""
import threading
import time
import pytest
from src.utils.health_probe import (
    ActiveHealthProbe,
    HealthResult,
    HealthState,
    get_health_probe,
)
import src.utils.health_probe as _hp_mod


def _healthy_check():
    return HealthResult(healthy=True, reason="ok")


def _unhealthy_check():
    return HealthResult(healthy=False, reason="down")


def _boom_check():
    raise RuntimeError("boom")


class TestHysteresis:
    """Verify that hysteresis prevents false positives."""

    def test_stays_unknown_until_enough_passes(self):
        probe = ActiveHealthProbe(fails=3, passes=2)
        probe.register_check("svc", _healthy_check)

        # First pass → still UNKNOWN (need 2)
        probe.check_now("svc")
        assert not probe.is_healthy("svc")

        # Second pass → transitions to HEALTHY
        probe.check_now("svc")
        assert probe.is_healthy("svc")

    def test_stays_healthy_on_single_failure(self):
        probe = ActiveHealthProbe(fails=3, passes=2)
        probe.register_check("svc", _healthy_check)
        probe.check_now("svc")
        probe.check_now("svc")
        assert probe.is_healthy("svc")

        # One failure should NOT flip to unhealthy (need 3)
        probe._checks["svc"] = _unhealthy_check
        probe.check_now("svc")
        # Still healthy — only 1 fail, need 3
        assert probe.is_healthy("svc")

    def test_unhealthy_after_threshold_failures(self):
        probe = ActiveHealthProbe(fails=3, passes=2)
        probe.register_check("svc", _healthy_check)
        probe.check_now("svc")
        probe.check_now("svc")
        assert probe.is_healthy("svc")

        # Three consecutive failures → UNHEALTHY
        probe._checks["svc"] = _unhealthy_check
        probe.check_now("svc")
        probe.check_now("svc")
        probe.check_now("svc")
        assert not probe.is_healthy("svc")
        status = probe.get_status("svc")
        assert status["state"] == "unhealthy"

    def test_recovering_then_healthy(self):
        probe = ActiveHealthProbe(fails=2, passes=2)
        probe.register_check("svc", _unhealthy_check)

        # Drive to UNHEALTHY
        probe.check_now("svc")
        probe.check_now("svc")
        assert not probe.is_healthy("svc")

        # First pass → RECOVERING
        probe._checks["svc"] = _healthy_check
        probe.check_now("svc")
        status = probe.get_status("svc")
        assert status["state"] == "recovering"

        # Second pass → HEALTHY
        probe.check_now("svc")
        assert probe.is_healthy("svc")

    def test_recovery_interrupted_by_failure(self):
        probe = ActiveHealthProbe(fails=2, passes=3)
        probe.register_check("svc", _unhealthy_check)

        # Drive to UNHEALTHY
        probe.check_now("svc")
        probe.check_now("svc")

        # Start recovering
        probe._checks["svc"] = _healthy_check
        probe.check_now("svc")
        status = probe.get_status("svc")
        assert status["state"] == "recovering"

        # Fail during recovery → back to UNHEALTHY
        probe._checks["svc"] = _unhealthy_check
        probe.check_now("svc")
        status = probe.get_status("svc")
        assert status["state"] == "unhealthy"


class TestCallbacks:
    def test_state_change_callback_fires(self):
        events = []
        probe = ActiveHealthProbe(fails=1, passes=1)
        probe.register_check("svc", _healthy_check)
        probe.register_callback("on_state_change",
                                lambda name, state: events.append((name, state)))
        probe.check_now("svc")
        assert len(events) == 1
        assert events[0] == ("svc", HealthState.HEALTHY)

    def test_unhealthy_callback_fires(self):
        events = []
        probe = ActiveHealthProbe(fails=1, passes=1)
        probe.register_check("svc", _unhealthy_check)
        probe.register_callback("on_unhealthy",
                                lambda name, state: events.append(name))
        probe.check_now("svc")
        assert "svc" in events


class TestCheckExceptionHandling:
    def test_exception_counts_as_failure(self):
        probe = ActiveHealthProbe(fails=1, passes=1)
        probe.register_check("svc", _boom_check)
        result = probe.check_now("svc")
        assert not result.healthy
        assert "boom" in result.reason


class TestStartStop:
    def test_start_stop_lifecycle(self):
        probe = ActiveHealthProbe(interval=1, fails=1, passes=1)
        probe.register_check("svc", _healthy_check)
        probe.start()
        time.sleep(0.2)
        probe.stop(timeout=2)
        # Should have run at least one check
        status = probe.get_status("svc")
        assert status["total_checks"] >= 1

    def test_double_start_is_safe(self):
        probe = ActiveHealthProbe(interval=60, fails=1, passes=1)
        probe.register_check("svc", _healthy_check)
        probe.start()
        probe.start()  # should not crash
        probe.stop(timeout=2)


class TestAnomalyDetection:
    """Tests for MeshForge PR #1143/#1144 anomaly detection."""

    def test_record_anomaly(self):
        probe = ActiveHealthProbe(fails=1, passes=1)
        probe.register_check("svc", _healthy_check)
        probe.record_anomaly("svc", "zero traffic")
        anomalies = probe.get_anomalies()
        assert "svc" in anomalies
        assert anomalies["svc"]["last_anomaly"] == "zero traffic"
        assert anomalies["svc"]["anomaly_count"] == 1

    def test_no_anomalies_initially(self):
        probe = ActiveHealthProbe(fails=1, passes=1)
        probe.register_check("svc", _healthy_check)
        assert probe.get_anomalies() == {}

    def test_interface_rx_only_anomaly(self):
        probe = ActiveHealthProbe()
        anomalies = probe.check_interface_anomalies({
            "online": True, "tx_packets": 0, "rx_packets": 10,
        })
        assert len(anomalies) == 1
        assert "RX-only" in anomalies[0]

    def test_interface_zero_traffic_anomaly(self):
        probe = ActiveHealthProbe()
        anomalies = probe.check_interface_anomalies({
            "online": True, "tx_packets": 0, "rx_packets": 0,
        })
        assert len(anomalies) == 1
        assert "Zero-traffic" in anomalies[0]

    def test_no_anomaly_when_offline(self):
        probe = ActiveHealthProbe()
        anomalies = probe.check_interface_anomalies({
            "online": False, "tx_packets": 0, "rx_packets": 0,
        })
        assert anomalies == []

    def test_no_anomaly_when_traffic_flowing(self):
        probe = ActiveHealthProbe()
        anomalies = probe.check_interface_anomalies({
            "online": True, "tx_packets": 5, "rx_packets": 10,
        })
        assert anomalies == []


class TestGetAllStatus:
    def test_returns_all_services(self):
        probe = ActiveHealthProbe(fails=1, passes=1)
        probe.register_check("a", _healthy_check)
        probe.register_check("b", _unhealthy_check)
        probe.check_now("a")
        probe.check_now("b")
        all_status = probe.get_all_status()
        assert "a" in all_status
        assert "b" in all_status

    def test_unregistered_service_returns_none(self):
        probe = ActiveHealthProbe(fails=1, passes=1)
        assert probe.get_status("nope") is None

    def test_unregistered_is_not_healthy(self):
        probe = ActiveHealthProbe(fails=1, passes=1)
        assert not probe.is_healthy("nope")


class TestHealthProbeSingleton:
    """Guard against the PR #28 regression where the launcher and dashboard
    held different ActiveHealthProbe instances and the dashboard saw no state.
    """

    def setup_method(self):
        # Reset the module-level singleton between tests
        _hp_mod._health_probe = None

    def teardown_method(self):
        _hp_mod._health_probe = None

    def test_get_health_probe_returns_same_instance(self):
        a = get_health_probe()
        b = get_health_probe()
        assert a is b

    def test_anomaly_recorded_on_singleton_is_visible_to_next_caller(self):
        probe = get_health_probe()
        probe.register_check("svc", _healthy_check)
        probe.record_anomaly("svc", "zero traffic")
        # A consumer (e.g. the dashboard) requesting the singleton sees it.
        assert "svc" in get_health_probe().get_anomalies()
