"""Tests for src/Meshtastic_Interface.py — RNS interface driver."""
import sys
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


@pytest.fixture
def mock_owner():
    owner = MagicMock()
    owner.config = {}
    return owner


class TestMeshtasticInterfaceInit:
    def test_default_rns_attributes(self, mock_owner):
        """All required RNS attributes are set during init."""
        mocks = _build_mocks()
        mocks['meshtastic.serial_interface'].SerialInterface.side_effect = Exception("No device")

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
        mocks['meshtastic.serial_interface'].SerialInterface.side_effect = Exception("No device")

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
        mocks['meshtastic.serial_interface'].SerialInterface.side_effect = Exception("No device")

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
            config = {"connection_type": "tcp", "host": "localhost", "tcp_port": 4403}
            iface = MeshtasticInterface(mock_owner, "Test", config=config)

            data = b'\xAA\xBB\xCC'
            iface.process_incoming(data)

            iface.interface.sendData.assert_called_once_with(data, destinationId='^all')
            assert iface.txb == 3

    def test_transmit_when_offline_does_nothing(self, mock_owner):
        """process_incoming skips transmission when interface is offline."""
        mocks = _build_mocks()
        mocks['meshtastic.serial_interface'].SerialInterface.side_effect = Exception("No device")

        with patch.dict('sys.modules', mocks):
            _clear_cached_modules()
            from src.Meshtastic_Interface import MeshtasticInterface
            iface = MeshtasticInterface(mock_owner, "Test", config={})

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
