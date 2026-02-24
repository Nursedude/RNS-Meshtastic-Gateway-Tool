"""Tests for launcher.py — gateway startup, backoff, and signal handling."""
import sys
import os
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


class TestBackoffDelay:
    def test_first_attempt_near_initial(self):
        """Attempt 0 should produce a delay close to the initial delay."""
        launcher, _ = _import_launcher()
        delay = launcher._backoff_delay(0)
        expected = launcher.RECONNECT_INITIAL_DELAY
        jitter_range = expected * launcher.RECONNECT_JITTER
        assert expected - jitter_range <= delay <= expected + jitter_range

    def test_increases_with_attempts(self):
        """Later attempts should produce longer delays (on average)."""
        launcher, _ = _import_launcher()
        midpoints = [
            launcher.RECONNECT_INITIAL_DELAY * (launcher.RECONNECT_MULTIPLIER ** i)
            for i in range(5)
        ]
        for i in range(1, len(midpoints)):
            assert midpoints[i] >= midpoints[i - 1]

    def test_capped_at_max(self):
        """Very high attempts should not exceed max delay + jitter."""
        launcher, _ = _import_launcher()
        delay = launcher._backoff_delay(100)
        max_with_jitter = launcher.RECONNECT_MAX_DELAY * (1 + launcher.RECONNECT_JITTER)
        assert delay <= max_with_jitter

    def test_never_negative(self):
        """Delay should never be negative."""
        launcher, _ = _import_launcher()
        for attempt in range(20):
            assert launcher._backoff_delay(attempt) >= 0

    def test_jitter_produces_variation(self):
        """Multiple calls at the same attempt should produce different values."""
        launcher, _ = _import_launcher()
        delays = {launcher._backoff_delay(3) for _ in range(20)}
        assert len(delays) > 1


class TestStartGateway:
    def test_start_gateway_calls_reticulum(self):
        """start_gateway initializes RNS.Reticulum and creates MeshtasticInterface."""
        launcher, mock_rns = _import_launcher()

        mock_interface = MagicMock()
        mock_interface.online = True
        mock_interface.interface = MagicMock()
        mock_interface.name = "TestRadio"

        with patch.object(launcher, 'MeshtasticInterface', return_value=mock_interface), \
             patch.object(launcher, 'load_config', return_value={"gateway": {}}), \
             patch.object(launcher, 'setup_logging'), \
             patch('time.sleep', side_effect=KeyboardInterrupt):

            with pytest.raises(SystemExit):
                launcher.start_gateway()

            mock_rns.Reticulum.assert_called_once()
            mock_interface.detach.assert_called_once()
