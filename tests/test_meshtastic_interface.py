"""Tests for src/Meshtastic_Interface.py — RNS interface driver."""
import sys
import time
from unittest.mock import patch, MagicMock

import pytest


def _build_mocks():
    """Build mock modules for RNS and meshtastic so the interface can import."""
    # RNS mocks
    mock_rns = MagicMock()
    mock_rns_interfaces = MagicMock()
    mock_rns_interface = MagicMock()
    mock_rns_interface.Interface = type('Interface', (), {
        'MODE_ACCESS_POINT': 1,
    })
    mock_rns.Interfaces = mock_rns_interfaces
    mock_rns.Interfaces.Interface = mock_rns_interface

    # Meshtastic mocks
    mock_mesh = MagicMock()
    mock_serial = MagicMock()
    mock_tcp = MagicMock()
    mock_pub = MagicMock()
    mock_mesh.serial_interface = mock_serial
    mock_mesh.tcp_interface = mock_tcp
    mock_mesh.pub = mock_pub

    return {
        'RNS': mock_rns,
        'RNS.Interfaces': mock_rns_interfaces,
        'RNS.Interfaces.Interface': mock_rns_interface,
        'meshtastic': mock_mesh,
        'meshtastic.serial_interface': mock_serial,
        'meshtastic.tcp_interface': mock_tcp,
        'meshtastic.pub': mock_pub,
    }


def _clear_cached_modules():
    """Remove cached interface module so reimport picks up new mocks."""
    for key in list(sys.modules):
        if 'Meshtastic_Interface' in key:
            del sys.modules[key]


def _no_features():
    """Config dict with reliability features disabled for isolated unit tests."""
    return {"features": {"circuit_breaker": False, "tx_queue": False}}


@pytest.fixture
def mock_owner():
    owner = MagicMock()
    owner.config = {}
    return owner


class TestMeshtasticInterfaceInit:
    def test_default_rns_attributes(self, mock_owner):
        """All required RNS attributes are set during init."""
        mocks = _build_mocks()
        mocks['meshtastic.serial_interface'].SerialInterface.side_effect = OSError("No device")

        with patch.dict('sys.modules', mocks):
            _clear_cached_modules()
            from src.Meshtastic_Interface import MeshtasticInterface
            iface = MeshtasticInterface(mock_owner, "TestRadio", config={})

            assert iface.name == "TestRadio"
            assert iface.IN is True
            assert iface.bitrate == 500
            assert iface.rxb == 0
            assert iface.txb == 0
            assert iface.ingress_control is False
            assert isinstance(iface.held_announces, list)
            assert hasattr(iface, 'ia_freq_deque')
            assert hasattr(iface, 'oa_freq_deque')

    def test_tcp_connection_type(self, mock_owner):
        """TCP init path is selected when config specifies it."""
        mocks = _build_mocks()

        with patch.dict('sys.modules', mocks):
            _clear_cached_modules()
            from src.Meshtastic_Interface import MeshtasticInterface
            config = {"connection_type": "tcp", "host": "192.168.1.100", "tcp_port": 4403}
            iface = MeshtasticInterface(mock_owner, "TCPRadio", config=config)

            assert iface.connection_type == "tcp"
            assert iface.host == "192.168.1.100"
            assert iface.tcp_port == 4403
            assert iface.online is True


class TestOnReceive:
    def test_valid_packet_forwarded(self, mock_owner):
        """on_receive passes decoded payload to owner.inbound."""
        mocks = _build_mocks()
        mocks['meshtastic.serial_interface'].SerialInterface.side_effect = OSError("No device")

        with patch.dict('sys.modules', mocks):
            _clear_cached_modules()
            from src.Meshtastic_Interface import MeshtasticInterface
            iface = MeshtasticInterface(mock_owner, "Test", config={})

            packet = {'decoded': {'payload': b'\x01\x02\x03'}}
            iface.on_receive(packet, MagicMock())

            mock_owner.inbound.assert_called_once_with(b'\x01\x02\x03', iface)
            assert iface.rxb == 3

    def test_malformed_packet_ignored(self, mock_owner):
        """on_receive handles packets without decoded/payload gracefully."""
        mocks = _build_mocks()
        mocks['meshtastic.serial_interface'].SerialInterface.side_effect = OSError("No device")

        with patch.dict('sys.modules', mocks):
            _clear_cached_modules()
            from src.Meshtastic_Interface import MeshtasticInterface
            iface = MeshtasticInterface(mock_owner, "Test", config={})

            iface.on_receive({}, MagicMock())
            mock_owner.inbound.assert_not_called()


class TestProcessIncoming:
    def test_transmit_calls_sendData(self, mock_owner):
        """process_incoming sends data to mesh radio via sendData."""
        mocks = _build_mocks()

        with patch.dict('sys.modules', mocks):
            _clear_cached_modules()
            from src.Meshtastic_Interface import MeshtasticInterface
            config = {
                "connection_type": "tcp", "host": "localhost", "tcp_port": 4403,
                "features": {"circuit_breaker": False, "tx_queue": False},
            }
            iface = MeshtasticInterface(mock_owner, "Test", config=config)

            data = b'\xAA\xBB\xCC'
            iface.process_incoming(data)

            iface.interface.sendData.assert_called_once_with(data, destinationId='^all')
            assert iface.txb == 3

    def test_transmit_when_offline_does_nothing(self, mock_owner):
        """process_incoming skips transmission when interface is offline."""
        mocks = _build_mocks()
        mocks['meshtastic.serial_interface'].SerialInterface.side_effect = OSError("No device")

        with patch.dict('sys.modules', mocks):
            _clear_cached_modules()
            from src.Meshtastic_Interface import MeshtasticInterface
            iface = MeshtasticInterface(mock_owner, "Test", config=_no_features())

            assert iface.online is False
            iface.process_incoming(b'\x01\x02')
            assert iface.txb == 0


class TestReconnect:
    def test_reconnect_unsubscribes_then_resubscribes(self, mock_owner):
        """reconnect unsubscribes old handler before re-initializing."""
        mocks = _build_mocks()
        mock_pub = mocks['meshtastic.pub']

        with patch.dict('sys.modules', mocks):
            _clear_cached_modules()
            from src.Meshtastic_Interface import MeshtasticInterface
            config = {"connection_type": "tcp", "host": "localhost", "tcp_port": 4403}
            iface = MeshtasticInterface(mock_owner, "Test", config=config)

            # Initial subscribe happened during init
            initial_subscribe_count = mock_pub.subscribe.call_count
            assert initial_subscribe_count == 1

            iface.reconnect()

            # Should have unsubscribed, then subscribed again
            mock_pub.unsubscribe.assert_called_once()
            assert mock_pub.subscribe.call_count == 2

    def test_reconnect_closes_existing_interface(self, mock_owner):
        """reconnect closes the old interface before creating a new one."""
        mocks = _build_mocks()

        with patch.dict('sys.modules', mocks):
            _clear_cached_modules()
            from src.Meshtastic_Interface import MeshtasticInterface
            config = {"connection_type": "tcp", "host": "localhost", "tcp_port": 4403}
            iface = MeshtasticInterface(mock_owner, "Test", config=config)

            old_interface = iface.interface
            iface.reconnect()

            old_interface.close.assert_called_once()
            assert iface.online is True


class TestDetach:
    def test_detach_closes_and_marks_offline(self, mock_owner):
        """detach closes interface and sets offline state."""
        mocks = _build_mocks()

        with patch.dict('sys.modules', mocks):
            _clear_cached_modules()
            from src.Meshtastic_Interface import MeshtasticInterface
            config = {"connection_type": "tcp", "host": "localhost", "tcp_port": 4403}
            iface = MeshtasticInterface(mock_owner, "Test", config=config)

            assert iface.online is True
            iface.detach()

            iface.interface.close.assert_called_once()
            assert iface.detached is True
            assert iface.online is False


class TestTransmitErrors:
    def test_sendData_exception_increments_tx_errors(self, mock_owner):
        """When sendData raises, tx_errors should increment."""
        mocks = _build_mocks()

        with patch.dict('sys.modules', mocks):
            _clear_cached_modules()
            from src.Meshtastic_Interface import MeshtasticInterface
            config = {
                "connection_type": "tcp", "host": "localhost", "tcp_port": 4403,
                "features": {"circuit_breaker": False, "tx_queue": False},
            }
            iface = MeshtasticInterface(mock_owner, "Test", config=config)
            iface.interface.sendData.side_effect = OSError("radio dead")

            iface.process_incoming(b'\x01\x02')
            assert iface.tx_errors == 1

    def test_oversized_message_still_sent(self, mock_owner):
        """Oversized messages are warned but still attempted."""
        mocks = _build_mocks()

        with patch.dict('sys.modules', mocks):
            _clear_cached_modules()
            from src.Meshtastic_Interface import MeshtasticInterface
            config = {
                "connection_type": "tcp", "host": "localhost", "tcp_port": 4403,
                "features": {"circuit_breaker": False, "tx_queue": False},
            }
            iface = MeshtasticInterface(mock_owner, "Test", config=config)
            big_data = b'\x00' * 300
            iface.process_incoming(big_data)
            iface.interface.sendData.assert_called_once()
            assert iface.txb == 300


class TestProcessOutgoing:
    def test_delegates_to_process_incoming(self, mock_owner):
        """process_outgoing should delegate to process_incoming."""
        mocks = _build_mocks()

        with patch.dict('sys.modules', mocks):
            _clear_cached_modules()
            from src.Meshtastic_Interface import MeshtasticInterface
            config = {
                "connection_type": "tcp", "host": "localhost", "tcp_port": 4403,
                "features": {"circuit_breaker": False, "tx_queue": False},
            }
            iface = MeshtasticInterface(mock_owner, "Test", config=config)
            data = b'\xAA'
            iface.process_outgoing(data)
            iface.interface.sendData.assert_called_once_with(data, destinationId='^all')


class TestStrRepr:
    def test_str(self, mock_owner):
        mocks = _build_mocks()
        mocks['meshtastic.serial_interface'].SerialInterface.side_effect = OSError("No device")

        with patch.dict('sys.modules', mocks):
            _clear_cached_modules()
            from src.Meshtastic_Interface import MeshtasticInterface
            iface = MeshtasticInterface(mock_owner, "Test", config=_no_features())
            s = str(iface)
            assert "Meshtastic Radio" in s
            assert "serial" in s

    def test_repr(self, mock_owner):
        mocks = _build_mocks()
        mocks['meshtastic.serial_interface'].SerialInterface.side_effect = OSError("No device")

        with patch.dict('sys.modules', mocks):
            _clear_cached_modules()
            from src.Meshtastic_Interface import MeshtasticInterface
            iface = MeshtasticInterface(mock_owner, "Test", config=_no_features())
            r = repr(iface)
            assert "MeshtasticInterface" in r
            assert "name='Test'" in r


class TestHealthCheck:
    def test_healthy_when_interface_exists(self, mock_owner):
        mocks = _build_mocks()

        with patch.dict('sys.modules', mocks):
            _clear_cached_modules()
            from src.Meshtastic_Interface import MeshtasticInterface
            config = {
                "connection_type": "tcp", "host": "localhost", "tcp_port": 4403,
                "features": {"circuit_breaker": False, "tx_queue": False},
            }
            iface = MeshtasticInterface(mock_owner, "Test", config=config)
            assert iface.health_check() is True

    def test_unhealthy_when_interface_is_none(self, mock_owner):
        mocks = _build_mocks()
        mocks['meshtastic.serial_interface'].SerialInterface.side_effect = OSError("No device")

        with patch.dict('sys.modules', mocks):
            _clear_cached_modules()
            from src.Meshtastic_Interface import MeshtasticInterface
            iface = MeshtasticInterface(mock_owner, "Test", config=_no_features())
            assert iface.health_check() is False

    def test_unhealthy_when_circuit_breaker_open(self, mock_owner):
        mocks = _build_mocks()

        with patch.dict('sys.modules', mocks):
            _clear_cached_modules()
            from src.Meshtastic_Interface import MeshtasticInterface
            config = {
                "connection_type": "tcp", "host": "localhost", "tcp_port": 4403,
                "features": {"circuit_breaker": True, "tx_queue": False},
            }
            iface = MeshtasticInterface(mock_owner, "Test", config=config)
            # Trip the circuit breaker
            for _ in range(5):
                iface._circuit_breaker.record_failure()
            assert iface.health_check() is False


class TestMetrics:
    def test_metrics_returns_dict(self, mock_owner):
        mocks = _build_mocks()

        with patch.dict('sys.modules', mocks):
            _clear_cached_modules()
            from src.Meshtastic_Interface import MeshtasticInterface
            config = {"connection_type": "tcp", "host": "localhost", "tcp_port": 4403}
            iface = MeshtasticInterface(mock_owner, "Test", config=config)
            m = iface.metrics
            assert isinstance(m, dict)
            assert "tx_packets" in m
            assert "rx_packets" in m
            assert "tx_bytes" in m
            assert "circuit_breaker_state" in m
            assert "tx_queue_pending" in m


class TestCircuitBreakerIntegration:
    def test_circuit_breaker_blocks_tx_when_open(self, mock_owner):
        """When circuit breaker is OPEN, process_incoming should not send."""
        mocks = _build_mocks()

        with patch.dict('sys.modules', mocks):
            _clear_cached_modules()
            from src.Meshtastic_Interface import MeshtasticInterface
            config = {
                "connection_type": "tcp", "host": "localhost", "tcp_port": 4403,
                "features": {"circuit_breaker": True, "tx_queue": False},
            }
            iface = MeshtasticInterface(mock_owner, "Test", config=config)
            # Trip the breaker
            for _ in range(5):
                iface._circuit_breaker.record_failure()

            iface.process_incoming(b'\x01')
            iface.interface.sendData.assert_not_called()

    def test_reconnect_resets_circuit_breaker(self, mock_owner):
        """Reconnect should reset the circuit breaker."""
        mocks = _build_mocks()

        with patch.dict('sys.modules', mocks):
            _clear_cached_modules()
            from src.Meshtastic_Interface import MeshtasticInterface
            from src.utils.circuit_breaker import State
            config = {
                "connection_type": "tcp", "host": "localhost", "tcp_port": 4403,
                "features": {"circuit_breaker": True, "tx_queue": False},
            }
            iface = MeshtasticInterface(mock_owner, "Test", config=config)
            for _ in range(5):
                iface._circuit_breaker.record_failure()
            assert iface._circuit_breaker.state is State.OPEN

            iface.reconnect()
            assert iface._circuit_breaker.state is State.CLOSED
