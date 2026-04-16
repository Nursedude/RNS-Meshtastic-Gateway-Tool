"""Tests for the MQTT Bridge Handler (Session 3)."""

import base64
import json
import sys
import time
from unittest.mock import MagicMock, patch

import pytest


# ── Module-level RNS + paho mocks (active for all tests) ─────
# RNS fails with PanicException (BaseException) in this CI environment.
# We mock it at import time, same pattern as test_launcher.py.

_mock_rns = MagicMock()
_mock_rns_interface_mod = MagicMock()
_mock_rns_interface_mod.Interface = type(
    'Interface', (), {'MODE_ACCESS_POINT': 1},
)
_mock_rns.Interfaces.Interface = _mock_rns_interface_mod

_mock_mqtt_mod = MagicMock()
_mock_mqtt_client_instance = MagicMock()
_mock_mqtt_client_instance.is_connected.return_value = True
_mock_mqtt_mod.Client.return_value = _mock_mqtt_client_instance
_mock_mqtt_mod.CallbackAPIVersion.VERSION2 = 2

_SYS_MODULE_MOCKS = {
    'RNS': _mock_rns,
    'RNS.Interfaces': MagicMock(),
    'RNS.Interfaces.Interface': _mock_rns_interface_mod,
    'paho': MagicMock(),
    'paho.mqtt': MagicMock(),
    'paho.mqtt.client': _mock_mqtt_mod,
}

# Clear any cached import of src.mqtt_bridge so it re-imports with mocks
for _key in list(sys.modules):
    if _key == 'src.mqtt_bridge':
        del sys.modules[_key]

# Patch sys.modules BEFORE importing MqttBridge
_patcher = patch.dict('sys.modules', _SYS_MODULE_MOCKS)
_patcher.start()

from src.mqtt_bridge import MqttBridge  # noqa: E402

# Keep the patcher running for the duration of the test module.
# pytest will collect and run all tests before interpreter cleanup.


# ── Fixtures ──────────────────────────────────────────────────

@pytest.fixture
def mock_paho():
    """Return fresh mock paho client for per-test assertions."""
    mock_mqtt = MagicMock()
    mock_client = MagicMock()
    mock_client.is_connected.return_value = True
    mock_mqtt.Client.return_value = mock_client
    mock_mqtt.CallbackAPIVersion.VERSION2 = 2
    return mock_mqtt, mock_client


@pytest.fixture
def mock_owner():
    """Mock RNS owner (Reticulum instance)."""
    owner = MagicMock()
    owner.config = {}
    return owner


@pytest.fixture
def mqtt_config():
    """Basic MQTT bridge config."""
    return {
        "bridge_mode": "mqtt",
        "mqtt_host": "localhost",
        "mqtt_port": 1883,
        "mqtt_topic_root": "msh",
        "mqtt_region": "US",
        "http_api_port": 9443,
        "bitrate": 500,
        "features": {"circuit_breaker": True, "tx_queue": False, "message_queue": False},
    }


@pytest.fixture
def bridge(mock_paho, mock_owner, mqtt_config):
    """Create a MqttBridge instance with mocked paho and RNS."""
    mock_mqtt, mock_client = mock_paho
    with patch('src.mqtt_bridge.mqtt', mock_mqtt):
        b = MqttBridge(
            mock_owner, "Test MQTT Bridge",
            config=mqtt_config,
            bridge_health=MagicMock(),
        )
        # Simulate successful connect
        b.online = True
        b.OUT = True
        b._mqtt_client = mock_client
        return b


# ── Init Tests ────────────────────────────────────────────────

class TestMqttBridgeInit:
    def test_rns_attributes_set(self, bridge):
        assert bridge.name == "Test MQTT Bridge"
        assert bridge.IN is True
        assert bridge.rxb == 0
        assert bridge.txb == 0
        assert bridge.tx_packets == 0
        assert bridge.rx_packets == 0
        assert bridge.tx_errors == 0
        assert bridge.detached is False

    def test_mqtt_config_parsed(self, bridge):
        assert bridge._mqtt_host == "localhost"
        assert bridge._mqtt_port == 1883
        assert bridge._topic_root == "msh"
        assert bridge._region == "US"
        assert "9443" in bridge._http_api_url

    def test_subscribe_topic_format(self, bridge):
        assert bridge._subscribe_topic == "msh/US/2/json/#"

    def test_circuit_breaker_created(self, bridge):
        assert bridge._circuit_breaker is not None

    def test_default_config_values(self, mock_paho, mock_owner):
        """Test defaults when no MQTT fields provided."""
        mock_mqtt, _ = mock_paho
        with patch('src.mqtt_bridge.mqtt', mock_mqtt):
            b = MqttBridge(mock_owner, "Default Bridge", config={})
            assert b._mqtt_host == "localhost"
            assert b._mqtt_port == 1883
            assert b._topic_root == "msh"
            assert b._region == "US"


# ── RX Path Tests ─────────────────────────────────────────────

class TestMqttRxPath:
    def test_on_message_parses_json(self, bridge, mock_owner):
        """Valid JSON message should be parsed and passed to owner.inbound."""
        payload = base64.b64encode(b"hello from mesh")
        msg = MagicMock()
        msg.payload = json.dumps({
            "id": 12345,
            "from": "!abc123",
            "payload": payload.decode(),
        }).encode()

        bridge._on_message(None, None, msg)

        mock_owner.inbound.assert_called_once()
        args = mock_owner.inbound.call_args[0]
        assert args[0] == b"hello from mesh"
        assert bridge.rx_packets == 1
        assert bridge.rxb == len(b"hello from mesh")

    def test_on_message_records_bridge_health(self, bridge):
        payload = base64.b64encode(b"test")
        msg = MagicMock()
        msg.payload = json.dumps({"id": 1, "payload": payload.decode()}).encode()

        bridge._on_message(None, None, msg)

        bridge._bridge_health.record_message_sent.assert_called_with("mesh_to_rns")

    def test_malformed_json_does_not_crash(self, bridge, mock_owner):
        msg = MagicMock()
        msg.payload = b"not valid json{{"

        bridge._on_message(None, None, msg)

        mock_owner.inbound.assert_not_called()
        assert bridge.rx_packets == 0

    def test_missing_payload_skipped(self, bridge, mock_owner):
        msg = MagicMock()
        msg.payload = json.dumps({"id": 1}).encode()

        bridge._on_message(None, None, msg)

        mock_owner.inbound.assert_not_called()

    def test_duplicate_message_skipped(self, bridge, mock_owner):
        payload = base64.b64encode(b"dup")
        msg1 = MagicMock()
        msg1.payload = json.dumps({"id": 99, "payload": payload.decode()}).encode()
        msg2 = MagicMock()
        msg2.payload = json.dumps({"id": 99, "payload": payload.decode()}).encode()

        bridge._on_message(None, None, msg1)
        bridge._on_message(None, None, msg2)

        assert mock_owner.inbound.call_count == 1
        assert bridge.rx_packets == 1


# ── TX Path Tests ─────────────────────────────────────────────

class TestMqttTxPath:
    @patch('src.mqtt_bridge.urllib.request.urlopen')
    def test_do_send_posts_http(self, mock_urlopen, bridge):
        bridge._do_send(b"test data")

        mock_urlopen.assert_called_once()
        req = mock_urlopen.call_args[0][0]
        assert req.data == b"test data"
        assert req.get_header("Content-type") == "application/x-protobuf"
        assert bridge.tx_packets == 1
        assert bridge.txb == len(b"test data")

    @patch('src.mqtt_bridge.urllib.request.urlopen')
    def test_do_send_records_bridge_health_on_success(self, mock_urlopen, bridge):
        bridge._do_send(b"ok")
        bridge._bridge_health.record_message_sent.assert_called_with("rns_to_mesh")

    @patch('src.mqtt_bridge.urllib.request.urlopen', side_effect=OSError("connection refused"))
    def test_do_send_records_failure(self, mock_urlopen, bridge):
        bridge._do_send(b"fail")
        assert bridge.tx_errors == 1
        bridge._bridge_health.record_message_failed.assert_called_with("rns_to_mesh")

    @patch('src.mqtt_bridge.urllib.request.urlopen')
    def test_process_incoming_sends_when_online(self, mock_urlopen, bridge):
        bridge.process_incoming(b"data")
        mock_urlopen.assert_called_once()

    def test_process_incoming_blocked_when_offline(self, bridge):
        bridge.online = False
        bridge._do_send = MagicMock()
        bridge.process_incoming(b"data")
        bridge._do_send.assert_not_called()

    def test_process_incoming_blocked_by_circuit_breaker(self, bridge):
        bridge._circuit_breaker.allow_request = MagicMock(return_value=False)
        bridge._do_send = MagicMock()
        bridge.process_incoming(b"data")
        bridge._do_send.assert_not_called()

    def test_process_outgoing_delegates(self, bridge):
        bridge.process_incoming = MagicMock()
        bridge.process_outgoing(b"data")
        bridge.process_incoming.assert_called_once_with(b"data")


# ── Event-bus resilience ─────────────────────────────────────

class TestEventBusResilience:
    """Event bus failures must never break the TX/RX or connection path.

    Regression guard for the PR #29 narrowing (`except (ImportError,
    AttributeError)`) that would let a `RuntimeError` from a saturated
    ThreadPool / QueueFull propagate and drop packets.
    """

    @patch('src.mqtt_bridge.urllib.request.urlopen')
    @patch('src.utils.event_bus.emit_message',
           side_effect=RuntimeError("event bus busy"))
    def test_tx_survives_event_bus_runtime_error(
        self, mock_emit, mock_urlopen, bridge,
    ):
        bridge._do_send(b"payload")
        assert bridge.tx_packets == 1
        assert bridge.tx_errors == 0
        assert mock_emit.called
        mock_urlopen.assert_called_once()

    @patch('src.utils.event_bus.emit_message',
           side_effect=RuntimeError("event bus busy"))
    def test_rx_survives_event_bus_runtime_error(
        self, mock_emit, bridge, mock_owner,
    ):
        payload = base64.b64encode(b"data")
        msg = MagicMock()
        msg.payload = json.dumps({
            "id": 42,
            "from": "!node1",
            "payload": payload.decode(),
        }).encode()
        # Should not raise despite event-bus failing
        bridge._on_message(None, None, msg)
        assert mock_owner.inbound.call_count == 1
        assert bridge.rx_packets == 1

    @patch('src.utils.event_bus.emit_service_status',
           side_effect=RuntimeError("event bus busy"))
    def test_on_connect_survives_event_bus_runtime_error(
        self, mock_emit, bridge,
    ):
        mock_client = MagicMock()
        bridge._on_connect(mock_client, None, None, 0)
        assert bridge.online is True

    @patch('src.utils.event_bus.emit_service_status',
           side_effect=RuntimeError("event bus busy"))
    def test_on_disconnect_survives_event_bus_runtime_error(
        self, mock_emit, bridge,
    ):
        # Should not raise
        bridge._on_disconnect(MagicMock(), None, None, 0)
        assert bridge.online is False


# ── Dedup Tests ───────────────────────────────────────────────

class TestMqttDedup:
    def test_first_message_not_duplicate(self, bridge):
        assert bridge._is_duplicate("msg_001") is False

    def test_same_id_is_duplicate(self, bridge):
        bridge._is_duplicate("msg_002")
        assert bridge._is_duplicate("msg_002") is True

    def test_different_ids_not_duplicate(self, bridge):
        bridge._is_duplicate("msg_003")
        assert bridge._is_duplicate("msg_004") is False

    def test_cleanup_removes_expired(self, bridge):
        bridge._seen_ids["old_msg"] = time.monotonic() - 120
        bridge._last_dedup_cleanup = time.monotonic() - 120
        bridge._is_duplicate("trigger_cleanup")
        assert "old_msg" not in bridge._seen_ids

    def test_cleanup_keeps_fresh_entries(self, bridge):
        """Time-based purge must not evict still-valid IDs."""
        now = time.monotonic()
        bridge._seen_ids["fresh_msg"] = now - 1.0
        bridge._seen_ids["old_msg"] = now - 120
        bridge._last_dedup_cleanup = now - 120
        bridge._is_duplicate("trigger_cleanup")
        assert "fresh_msg" in bridge._seen_ids
        assert "old_msg" not in bridge._seen_ids

    def test_hard_cap_trims_when_exceeded(self, bridge):
        """If the dict balloons past MQTT_DEDUP_MAX_ENTRIES of *fresh* IDs
        (faster than the time window can clean), trim to half the cap."""
        from src.utils.timeouts import MQTT_DEDUP_MAX_ENTRIES
        now = time.monotonic()
        # Fill with fresh IDs that won't be purged by the time window.
        bridge._seen_ids = {
            f"id_{i}": now - 0.001 * i
            for i in range(MQTT_DEDUP_MAX_ENTRIES + 5)
        }
        bridge._last_dedup_cleanup = now  # block time-based path
        bridge._is_duplicate("trigger_cap")
        assert len(bridge._seen_ids) <= MQTT_DEDUP_MAX_ENTRIES
        # Newest entries (smallest i) should survive; oldest evicted.
        assert "id_0" in bridge._seen_ids
        assert f"id_{MQTT_DEDUP_MAX_ENTRIES + 4}" not in bridge._seen_ids


# ── Connection Tests ──────────────────────────────────────────

class TestMqttConnection:
    def test_on_connect_success(self, bridge, mock_paho):
        _, mock_client = mock_paho
        bridge.online = False
        bridge._on_connect(mock_client, None, None, 0)
        assert bridge.online is True
        assert bridge.OUT is True
        mock_client.subscribe.assert_called_with("msh/US/2/json/#")

    def test_on_connect_failure(self, bridge, mock_paho):
        _, mock_client = mock_paho
        bridge.online = True
        bridge._on_connect(mock_client, None, None, 5)
        assert bridge.online is False

    def test_on_disconnect(self, bridge, mock_paho):
        _, mock_client = mock_paho
        bridge._on_disconnect(mock_client, None, None, 1)
        assert bridge.online is False
        assert bridge.OUT is False


# ── Health Check Tests ────────────────────────────────────────

class TestMqttHealthCheck:
    def test_healthy_when_connected(self, bridge):
        assert bridge.health_check() is True

    def test_unhealthy_when_client_none(self, bridge):
        bridge._mqtt_client = None
        assert bridge.health_check() is False

    def test_unhealthy_when_disconnected(self, bridge):
        bridge._mqtt_client.is_connected.return_value = False
        assert bridge.health_check() is False


# ── RNS PanicException resilience ────────────────────────────

class TestRnsPanicResilience:
    """Bridge construction must survive RNS's PanicException at import time.

    Some RNS versions raise PanicException (a BaseException subclass) during
    import / mode-detection. The bridge must downgrade to default mode rather
    than letting the panic bubble up and crash the gateway.
    """

    def test_panic_exception_does_not_crash_bridge(
        self, mock_paho, mock_owner, mqtt_config,
    ):
        class PanicException(BaseException):
            pass

        # Re-mock RNS so attribute access raises PanicException.
        rns_panicking = MagicMock()
        type(rns_panicking.Interfaces.Interface).MODE_ACCESS_POINT = property(
            lambda self: (_ for _ in ()).throw(PanicException("rns panicked"))
        )

        mock_mqtt, mock_client = mock_paho
        with patch.dict('sys.modules', {'RNS': rns_panicking}), \
             patch('src.mqtt_bridge.mqtt', mock_mqtt):
            b = MqttBridge(
                mock_owner, "Panic Bridge",
                config=mqtt_config,
                bridge_health=MagicMock(),
            )
        assert b.mode == 1  # fell through to default

    def test_keyboard_interrupt_still_propagates(
        self, mock_paho, mock_owner, mqtt_config,
    ):
        rns_kb = MagicMock()
        type(rns_kb.Interfaces.Interface).MODE_ACCESS_POINT = property(
            lambda self: (_ for _ in ()).throw(KeyboardInterrupt())
        )

        mock_mqtt, _ = mock_paho
        with patch.dict('sys.modules', {'RNS': rns_kb}), \
             patch('src.mqtt_bridge.mqtt', mock_mqtt):
            with pytest.raises(KeyboardInterrupt):
                MqttBridge(
                    mock_owner, "Kb Bridge",
                    config=mqtt_config,
                    bridge_health=MagicMock(),
                )


# ── SSRF / URL Validation Tests ──────────────────────────────

class TestHttpApiUrlSsrf:
    """`_validate_http_api_url` must reject cloud-metadata endpoints."""

    def _validate(self, url):
        return MqttBridge._validate_http_api_url(url, default_port=9443)

    def test_localhost_allowed(self):
        result = self._validate("http://localhost:9443/api/v1/toradio")
        assert result == "http://localhost:9443/api/v1/toradio"

    def test_aws_metadata_ip_blocked(self):
        result = self._validate("http://169.254.169.254/latest/meta-data/")
        assert "localhost" in result
        assert "169.254" not in result

    def test_alibaba_metadata_ip_blocked(self):
        result = self._validate("http://100.100.100.200/")
        assert "localhost" in result

    def test_aws_metadata_ipv6_blocked(self):
        result = self._validate("http://[fd00:ec2::254]/latest/meta-data/")
        assert "localhost" in result

    def test_link_local_v4_blocked(self):
        result = self._validate("http://169.254.42.1:8080/")
        assert "localhost" in result

    def test_link_local_v6_blocked(self):
        result = self._validate("http://[fe80::1]/")
        assert "localhost" in result

    def test_metadata_hostname_blocked(self):
        result = self._validate("http://metadata.google.internal/")
        assert "localhost" in result

    def test_metadata_hostname_case_insensitive(self):
        result = self._validate("http://Metadata.Google.Internal./")
        assert "localhost" in result

    def test_lan_ip_still_allowed(self):
        # Operator may legitimately point at a LAN-hosted meshtasticd.
        result = self._validate("http://192.168.1.50:9443/api/v1/toradio")
        assert "192.168.1.50" in result


# ── Detach Tests ──────────────────────────────────────────────

class TestMqttDetach:
    def test_detach_stops_client(self, bridge, mock_paho):
        _, mock_client = mock_paho
        bridge._mqtt_client = mock_client
        bridge.detach()
        mock_client.loop_stop.assert_called_once()
        mock_client.disconnect.assert_called_once()
        assert bridge.detached is True
        assert bridge.online is False

    def test_detach_stops_message_queue(self, bridge):
        bridge._message_queue = MagicMock()
        bridge.detach()
        bridge._message_queue.stop.assert_called_once()


# ── Metrics Tests ─────────────────────────────────────────────

class TestMqttMetrics:
    def test_metrics_includes_counters(self, bridge):
        bridge.tx_packets = 5
        bridge.rx_packets = 3
        m = bridge.metrics
        assert m["tx_packets"] == 5
        assert m["rx_packets"] == 3
        assert m["bridge_mode"] == "mqtt"

    def test_metrics_includes_circuit_breaker(self, bridge):
        m = bridge.metrics
        assert "circuit_breaker_state" in m
        assert "circuit_breaker_failures" in m

    def test_str_repr(self, bridge):
        s = str(bridge)
        assert "MQTT Bridge" in s
        r = repr(bridge)
        assert "MqttBridge" in r
