"""Tests for src.utils.bridge_health – BridgeHealthMonitor, DeliveryTracker, and error classification."""
import time
import pytest
from src.utils.bridge_health import (
    BridgeHealthMonitor,
    BridgeStatus,
    SubsystemState,
    DeliveryTracker,
    classify_error,
)


# ── classify_error ───────────────────────────────────────────
class TestClassifyError:
    def test_transient_timeout(self):
        assert classify_error(TimeoutError("timed out")) == "transient"

    def test_transient_connection_reset(self):
        assert classify_error(ConnectionResetError("connection reset")) == "transient"

    def test_transient_broken_pipe(self):
        assert classify_error(BrokenPipeError("broken pipe")) == "transient"

    def test_transient_connection_refused(self):
        assert classify_error(ConnectionRefusedError("connection refused")) == "transient"

    def test_permanent_permission_denied(self):
        assert classify_error(PermissionError("permission denied")) == "permanent"

    def test_permanent_no_such_device(self):
        assert classify_error(OSError("no such device")) == "permanent"

    def test_permanent_module_not_found(self):
        assert classify_error(ImportError("module not found")) == "permanent"

    def test_unknown_generic(self):
        assert classify_error(ValueError("something weird")) == "unknown"

    def test_oserror_fallback_transient(self):
        # OSError without a known pattern still gets classified as transient
        # by isinstance check
        assert classify_error(OSError("unrecognised")) == "transient"


# ── BridgeHealthMonitor ─────────────────────────────────────
class TestBridgeHealthMonitor:
    def test_initial_state_offline(self):
        h = BridgeHealthMonitor()
        assert h.get_bridge_status() == BridgeStatus.OFFLINE
        assert not h.is_healthy()

    def test_single_connect_degraded(self):
        h = BridgeHealthMonitor()
        h.record_connection_event("meshtastic", "connected")
        assert h.get_bridge_status() == BridgeStatus.DEGRADED

    def test_both_connected_healthy(self):
        h = BridgeHealthMonitor()
        h.record_connection_event("meshtastic", "connected")
        h.record_connection_event("rns", "connected")
        assert h.get_bridge_status() == BridgeStatus.HEALTHY
        assert h.is_healthy()

    def test_disconnect_degrades(self):
        h = BridgeHealthMonitor()
        h.record_connection_event("meshtastic", "connected")
        h.record_connection_event("rns", "connected")
        h.record_connection_event("rns", "disconnected")
        assert h.get_bridge_status() == BridgeStatus.DEGRADED

    def test_both_disconnected_offline(self):
        h = BridgeHealthMonitor()
        h.record_connection_event("meshtastic", "connected")
        h.record_connection_event("meshtastic", "disconnected")
        assert h.get_bridge_status() == BridgeStatus.OFFLINE

    def test_message_counting(self):
        h = BridgeHealthMonitor()
        h.record_message_sent("mesh_to_rns")
        h.record_message_sent("mesh_to_rns")
        h.record_message_sent("rns_to_mesh")
        h.record_message_failed("mesh_to_rns", requeued=True)

        s = h.get_summary()
        assert s["messages"]["mesh_to_rns"] == 2
        assert s["messages"]["rns_to_mesh"] == 1
        assert s["messages"]["failed_mesh_to_rns"] == 1
        assert s["messages"]["requeued"] == 1

    def test_record_error_classifies(self):
        h = BridgeHealthMonitor()
        cat = h.record_error("meshtastic", TimeoutError("timed out"))
        assert cat == "transient"

        rates = h.get_error_rate(window_seconds=60)
        assert rates["transient"] == 1

    def test_message_rate(self):
        h = BridgeHealthMonitor()
        for _ in range(10):
            h.record_message_sent("mesh_to_rns")
        rate = h.get_message_rate(window_seconds=60)
        assert rate == pytest.approx(10.0, rel=0.1)

    def test_uptime_percent(self):
        h = BridgeHealthMonitor()
        h.record_connection_event("meshtastic", "connected")
        time.sleep(0.1)
        pct = h.get_uptime_percent("meshtastic")
        assert pct > 0

    def test_degraded_reason(self):
        h = BridgeHealthMonitor()
        reason = h.get_degraded_reason()
        assert "Meshtastic disconnected" in reason
        assert "RNS disconnected" in reason

    def test_should_pause_when_offline(self):
        h = BridgeHealthMonitor()
        assert h.should_pause_bridging()

    def test_should_not_pause_when_connected(self):
        h = BridgeHealthMonitor()
        h.record_connection_event("meshtastic", "connected")
        h.record_connection_event("rns", "connected")
        assert not h.should_pause_bridging()

    def test_summary_structure(self):
        h = BridgeHealthMonitor()
        s = h.get_summary()
        assert "uptime_seconds" in s
        assert "connections" in s
        assert "messages" in s
        assert "errors" in s
        assert "bridge_status" in s

    def test_reconnect_count(self):
        h = BridgeHealthMonitor()
        h.record_connection_event("meshtastic", "connected")
        h.record_connection_event("meshtastic", "disconnected")
        h.record_connection_event("meshtastic", "connected")
        s = h.get_summary()
        assert s["connections"]["meshtastic"]["reconnect_count"] == 2


# ── SubsystemState ──────────────────────────────────────────
class TestSubsystemState:
    def test_disconnected_when_not_connected(self):
        h = BridgeHealthMonitor()
        assert h.get_subsystem_state("meshtastic") == SubsystemState.DISCONNECTED

    def test_healthy_when_connected(self):
        h = BridgeHealthMonitor()
        h.record_connection_event("meshtastic", "connected")
        assert h.get_subsystem_state("meshtastic") == SubsystemState.HEALTHY

    def test_degraded_on_high_errors(self):
        h = BridgeHealthMonitor()
        h.record_connection_event("meshtastic", "connected")
        for _ in range(5):
            h.record_error("meshtastic", TimeoutError("timed out"))
        assert h.get_subsystem_state("meshtastic") == SubsystemState.DEGRADED

    def test_summary_includes_subsystem_state(self):
        h = BridgeHealthMonitor()
        h.record_connection_event("meshtastic", "connected")
        s = h.get_summary()
        assert s["connections"]["meshtastic"]["subsystem_state"] == "healthy"


# ── Zero-Traffic Detection ──────────────────────────────────
class TestZeroTraffic:
    def test_no_zero_traffic_when_disconnected(self):
        h = BridgeHealthMonitor()
        assert h.check_zero_traffic(min_uptime=0) == []

    def test_no_zero_traffic_when_messages_flowing(self):
        h = BridgeHealthMonitor()
        h.record_connection_event("meshtastic", "connected")
        h.record_message_sent("mesh_to_rns")
        assert h.check_zero_traffic(min_uptime=0) == []

    def test_detects_zero_traffic(self):
        h = BridgeHealthMonitor()
        h.record_connection_event("meshtastic", "connected")
        # Fake the connection time to be old enough
        h._last_connected["meshtastic"] = time.time() - 300
        result = h.check_zero_traffic(min_uptime=120)
        assert "meshtastic" in result

    def test_respects_min_uptime(self):
        h = BridgeHealthMonitor()
        h.record_connection_event("meshtastic", "connected")
        # Just connected — should not flag
        assert h.check_zero_traffic(min_uptime=120) == []

    def test_summary_includes_zero_traffic(self):
        h = BridgeHealthMonitor()
        s = h.get_summary()
        assert "zero_traffic_services" in s

    def test_one_service_traffic_does_not_mask_another_service_silent(self):
        """PR #32 follow-up: rns traffic should not hide a dead meshtastic.

        Regression for the global-counter bug: the old code flagged
        zero-traffic only when NO messages had flowed anywhere, so a
        chatty rns side masked a dead meshtastic radio.
        """
        h = BridgeHealthMonitor()
        h.record_connection_event("meshtastic", "connected")
        h.record_connection_event("rns", "connected")
        # Make both connections old enough to qualify
        h._last_connected["meshtastic"] = time.time() - 300
        h._last_connected["rns"] = time.time() - 300
        # rns is bridging traffic, meshtastic is not
        h.record_message_sent("rns_to_mesh")

        result = h.check_zero_traffic(min_uptime=120)
        assert "meshtastic" in result, "dead radio should still be flagged"
        assert "rns" not in result, "chatty rns should not be flagged"

    def test_unknown_service_is_skipped(self):
        """Services without a direction mapping should not crash or be flagged."""
        h = BridgeHealthMonitor()
        h._connected["mystery"] = True
        h._last_connected["mystery"] = time.time() - 300
        result = h.check_zero_traffic(min_uptime=120)
        assert "mystery" not in result

    def test_warning_logs_are_emitted_after_lock_released(self, caplog):
        """Warning about zero traffic must not be emitted inside the lock."""
        import logging as _logging
        h = BridgeHealthMonitor()
        h.record_connection_event("meshtastic", "connected")
        h._last_connected["meshtastic"] = time.time() - 300
        with caplog.at_level(_logging.WARNING, logger="bridge_health"):
            result = h.check_zero_traffic(min_uptime=120)
        assert "meshtastic" in result
        assert any(
            "Zero-traffic detected" in rec.getMessage()
            for rec in caplog.records
        )


# ── DeliveryTracker ─────────────────────────────────────────
class TestDeliveryTracker:
    def test_register_returns_id(self):
        t = DeliveryTracker()
        did = t.register("rns_to_mesh")
        assert isinstance(did, str)
        assert len(did) == 12

    def test_confirm(self):
        t = DeliveryTracker()
        did = t.register()
        assert t.confirm(did) is True
        stats = t.get_stats()
        assert stats["confirmed"] == 1
        assert stats["pending"] == 0

    def test_confirm_unknown_returns_false(self):
        t = DeliveryTracker()
        assert t.confirm("nonexistent") is False

    def test_fail(self):
        t = DeliveryTracker()
        did = t.register()
        assert t.fail(did, "radio timeout") is True
        stats = t.get_stats()
        assert stats["failed"] == 1

    def test_timeout_sweep(self):
        t = DeliveryTracker(timeout=0.01)
        t.register()
        time.sleep(0.02)
        swept = t.sweep_timeouts()
        assert swept == 1
        stats = t.get_stats()
        assert stats["timed_out"] == 1
        assert stats["pending"] == 0

    def test_confirmation_rate(self):
        t = DeliveryTracker()
        for _ in range(3):
            did = t.register()
            t.confirm(did)
        did = t.register()
        t.fail(did)
        stats = t.get_stats()
        assert stats["confirmation_rate"] == 75.0

    def test_get_recent(self):
        t = DeliveryTracker()
        did = t.register()
        t.confirm(did)
        recent = t.get_recent(5)
        assert len(recent) == 1
        assert recent[0]["status"] == "confirmed"

    def test_bounded_history(self):
        t = DeliveryTracker(max_history=5)
        for _ in range(10):
            did = t.register()
            t.confirm(did)
        recent = t.get_recent(100)
        assert len(recent) == 5
