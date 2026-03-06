"""Tests for src/ui/preflight.py — startup checks and port conflict detection."""
import os
import sys
from unittest.mock import patch

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.ui.preflight import startup_preflight, check_port_conflicts


class TestStartupPreflight:
    """Tests for one-shot startup environment checks."""

    def test_warns_missing_config(self, tmp_path):
        """Warns when config.json is missing."""
        with patch('src.ui.preflight.CONFIG_PATH', str(tmp_path / 'nope.json')):
            warnings = startup_preflight()
        assert any('config.json' in w for w in warnings)

    def test_warns_invalid_config(self, tmp_path):
        """Warns when config.json exists but cannot be parsed."""
        bad_config = tmp_path / 'config.json'
        bad_config.write_text('{invalid json')
        with patch('src.ui.preflight.CONFIG_PATH', str(bad_config)), \
             patch('src.ui.preflight.load_config', return_value=None):
            warnings = startup_preflight()
        assert any('could not be parsed' in w for w in warnings)

    def test_warns_missing_rns_lib(self):
        """Warns when RNS library is not installed."""
        with patch('src.ui.preflight.CONFIG_PATH', '/nonexistent'), \
             patch('src.ui.preflight.check_rns_lib', return_value=(False, 'not installed')), \
             patch('src.ui.preflight.check_meshtastic_lib', return_value=(True, '2.3.0')), \
             patch('src.ui.preflight.check_rns_config', return_value=(True, '123 bytes')):
            warnings = startup_preflight()
        assert any('RNS' in w for w in warnings)

    def test_warns_missing_meshtastic_lib(self):
        """Warns when Meshtastic library is not installed."""
        with patch('src.ui.preflight.CONFIG_PATH', '/nonexistent'), \
             patch('src.ui.preflight.check_rns_lib', return_value=(True, '0.7.4')), \
             patch('src.ui.preflight.check_meshtastic_lib', return_value=(False, 'not installed')), \
             patch('src.ui.preflight.check_rns_config', return_value=(True, '123 bytes')):
            warnings = startup_preflight()
        assert any('Meshtastic' in w for w in warnings)

    def test_warns_no_serial_in_serial_mode(self):
        """Warns when serial mode is configured but no devices found."""
        cfg = {"gateway": {"connection_type": "serial"}}
        with patch('src.ui.preflight.CONFIG_PATH', '/exists'), \
             patch('os.path.isfile', return_value=True), \
             patch('src.ui.preflight.load_config', return_value=cfg), \
             patch('src.ui.preflight.validate_config', return_value=[]), \
             patch('src.ui.preflight.check_rns_lib', return_value=(True, '0.7.4')), \
             patch('src.ui.preflight.check_meshtastic_lib', return_value=(True, '2.3.0')), \
             patch('src.ui.preflight.check_serial_ports', return_value=["(none detected)"]), \
             patch('src.ui.preflight.check_rns_config', return_value=(True, '123 bytes')):
            warnings = startup_preflight()
        assert any('serial' in w.lower() for w in warnings)

    def test_no_warnings_when_all_ok(self):
        """Returns empty list when everything is in order."""
        cfg = {"gateway": {"connection_type": "tcp"}}
        with patch('src.ui.preflight.CONFIG_PATH', '/exists'), \
             patch('os.path.isfile', return_value=True), \
             patch('src.ui.preflight.load_config', return_value=cfg), \
             patch('src.ui.preflight.validate_config', return_value=[]), \
             patch('src.ui.preflight.check_rns_lib', return_value=(True, '0.7.4')), \
             patch('src.ui.preflight.check_meshtastic_lib', return_value=(True, '2.3.0')), \
             patch('src.ui.preflight.check_rns_config', return_value=(True, '123 bytes')):
            warnings = startup_preflight()
        assert warnings == []


class TestCheckPortConflicts:
    """Tests for pre-launch port conflict detection."""

    def test_no_conflicts_returns_empty(self):
        """No conflicts when all ports are free."""
        cfg = {"gateway": {"connection_type": "serial"}, "dashboard": {"port": 5000}}
        with patch('src.ui.preflight.check_rns_udp_port', return_value=(False, "not in use")), \
             patch('src.ui.preflight.check_tcp_port', return_value=(False, "not listening")):
            assert check_port_conflicts(cfg) == []

    def test_detects_udp_conflict(self):
        """Detects RNS shared-instance UDP port conflict."""
        cfg = {"gateway": {}, "dashboard": {"port": 5000}}
        with patch('src.ui.preflight.check_rns_udp_port', return_value=(True, "UDP :37428 in use")), \
             patch('src.ui.preflight.check_tcp_port', return_value=(False, "not listening")):
            conflicts = check_port_conflicts(cfg)
        assert len(conflicts) >= 1
        assert conflicts[0][0] == 37428

    def test_detects_dashboard_conflict(self):
        """Detects dashboard port already in use."""
        cfg = {"gateway": {}, "dashboard": {"port": 5000}}
        with patch('src.ui.preflight.check_rns_udp_port', return_value=(False, "not in use")), \
             patch('src.ui.preflight.check_tcp_port', return_value=(True, "TCP :5000 listening")):
            conflicts = check_port_conflicts(cfg)
        assert any(c[0] == 5000 for c in conflicts)

    def test_tcp_mode_checks_meshtasticd(self):
        """In TCP mode, checks meshtasticd port reachability."""
        cfg = {"gateway": {"connection_type": "tcp", "tcp_port": 4403}, "dashboard": {"port": 5000}}
        with patch('src.ui.preflight.check_rns_udp_port', return_value=(False, "not in use")), \
             patch('src.ui.preflight.check_tcp_port', return_value=(False, "not listening")):
            conflicts = check_port_conflicts(cfg)
        assert any(c[0] == 4403 for c in conflicts)

    def test_returns_empty_for_none_config(self):
        """Returns empty list when cfg is None."""
        assert check_port_conflicts(None) == []
