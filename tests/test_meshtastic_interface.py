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
