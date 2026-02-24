"""Tests for launcher.py — gateway startup, reconnect, and signal handling."""
import signal
import sys
import os
import threading
from unittest.mock import patch, MagicMock

import pytest

# Ensure project root on path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _import_launcher():
    """Import launcher module with RNS and meshtastic mocked.

    launcher.py has top-level 'import RNS' and imports MeshtasticInterface,
    which also import RNS and meshtastic. We must mock them before import.
    """
    # Clear any previously cached import
    for key in list(sys.modules):
        if key in ('launcher', 'Meshtastic_Interface') or 'Meshtastic_Interface' in key:
            del sys.modules[key]

    mock_rns = MagicMock()
    mock_rns_interfaces = MagicMock()
    mock_rns_interface_mod = MagicMock()
    mock_rns_interface_mod.Interface = type('Interface', (), {'MODE_ACCESS_POINT': 1})
    mock_rns.Interfaces = mock_rns_interfaces
    mock_rns.Interfaces.Interface = mock_rns_interface_mod

    mock_mesh = MagicMock()
    mock_serial = MagicMock()
    mock_tcp = MagicMock()
    mock_pub = MagicMock()
    mock_mesh.serial_interface = mock_serial
    mock_mesh.tcp_interface = mock_tcp
    mock_mesh.pub = mock_pub

    mocks = {
        'RNS': mock_rns,
        'RNS.Interfaces': mock_rns_interfaces,
        'RNS.Interfaces.Interface': mock_rns_interface_mod,
        'meshtastic': mock_mesh,
        'meshtastic.serial_interface': mock_serial,
        'meshtastic.tcp_interface': mock_tcp,
        'meshtastic.pub': mock_pub,
    }

    with patch.dict('sys.modules', mocks):
        import launcher
        return launcher, mock_rns


class TestStartGateway:
    def test_start_gateway_calls_reticulum_with_configdir(self):
        """start_gateway should pass configdir= to RNS.Reticulum()."""
        launcher, mock_rns = _import_launcher()

        mock_interface = MagicMock()
        mock_interface.online = True
        mock_interface.interface = MagicMock()
        mock_interface.name = "TestRadio"

        with patch.object(launcher, 'MeshtasticInterface', return_value=mock_interface), \
             patch.object(launcher, 'load_config', return_value={"gateway": {"rns_configdir": "/custom/path"}}), \
             patch.object(launcher, 'setup_logging'), \
             patch.object(launcher, '_stop_event', threading.Event()) as mock_event:

            # Set stop event immediately to exit the loop
            mock_event.set()
            with pytest.raises(SystemExit):
                launcher.start_gateway()

            mock_rns.Reticulum.assert_called_once_with(configdir="/custom/path")

    def test_start_gateway_default_configdir_is_none(self):
        """When rns_configdir is not in config, it should default to None."""
        launcher, mock_rns = _import_launcher()

        mock_interface = MagicMock()
        mock_interface.online = True
        mock_interface.interface = MagicMock()
        mock_interface.name = "TestRadio"

        with patch.object(launcher, 'MeshtasticInterface', return_value=mock_interface), \
             patch.object(launcher, 'load_config', return_value={"gateway": {}}), \
             patch.object(launcher, 'setup_logging'), \
             patch.object(launcher, '_stop_event', threading.Event()) as mock_event:

            mock_event.set()
            with pytest.raises(SystemExit):
                launcher.start_gateway()

            mock_rns.Reticulum.assert_called_once_with(configdir=None)

    def test_start_gateway_detaches_on_keyboard_interrupt(self):
        """start_gateway should call detach() on KeyboardInterrupt."""
        launcher, mock_rns = _import_launcher()

        mock_interface = MagicMock()
        mock_interface.online = True
        mock_interface.interface = MagicMock()
        mock_interface.name = "TestRadio"

        stop_event = threading.Event()

        def raise_interrupt(timeout=None):
            raise KeyboardInterrupt

        with patch.object(launcher, 'MeshtasticInterface', return_value=mock_interface), \
             patch.object(launcher, 'load_config', return_value={"gateway": {}}), \
             patch.object(launcher, 'setup_logging'), \
             patch.object(launcher, '_stop_event', stop_event):

            # Make the event wait raise KeyboardInterrupt
            stop_event.wait = raise_interrupt

            with pytest.raises(SystemExit):
                launcher.start_gateway()

            mock_interface.detach.assert_called_once()

    def test_health_check_detects_lost_interface(self):
        """Health check should mark interface offline when interface is None."""
        launcher, mock_rns = _import_launcher()

        mock_interface = MagicMock()
        mock_interface.online = True
        mock_interface.interface = None  # Lost interface
        mock_interface.name = "TestRadio"

        call_count = 0
        stop_event = threading.Event()

        original_wait = stop_event.wait

        def counting_wait(timeout=None):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                stop_event.set()
            return original_wait(0)

        stop_event.wait = counting_wait

        with patch.object(launcher, 'MeshtasticInterface', return_value=mock_interface), \
             patch.object(launcher, 'load_config', return_value={"gateway": {}}), \
             patch.object(launcher, 'setup_logging'), \
             patch.object(launcher, '_stop_event', stop_event), \
             patch.object(launcher, 'HEALTH_CHECK_INTERVAL', 0):  # Immediate health check

            with pytest.raises(SystemExit):
                launcher.start_gateway()

            # After health check with interface=None, online should be False
            assert mock_interface.online is False


class TestStopEvent:
    def test_stop_event_exists(self):
        """Module should have a threading.Event for clean shutdown."""
        launcher, _ = _import_launcher()
        assert isinstance(launcher._stop_event, threading.Event)

    def test_stop_event_not_set_initially(self):
        """Stop event should not be set on import."""
        launcher, _ = _import_launcher()
        assert not launcher._stop_event.is_set()
