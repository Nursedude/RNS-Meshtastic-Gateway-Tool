"""Tests for src.utils.bridge_health – BridgeHealthMonitor and error classification."""
import time
import pytest
from src.utils.bridge_health import (
    BridgeHealthMonitor,
    BridgeStatus,
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
