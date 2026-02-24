import json
import os
import sys

import pytest
from unittest.mock import MagicMock, patch

# Ensure project root is on sys.path so src.* imports work
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Detect CI environment (adopted from MeshForge conftest.py)
CI = os.environ.get('CI', 'false').lower() == 'true'


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "hardware: mark test as requiring hardware (skipped in CI)"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "network: mark test as requiring network access"
    )


def pytest_collection_modifyitems(config, items):
    """Auto-skip hardware and network tests in CI environment."""
    if not CI:
        return

    skip_hardware = pytest.mark.skip(reason="Hardware not available in CI")
    skip_network = pytest.mark.skip(reason="Network tests skipped in CI")

    for item in items:
        if "hardware" in item.keywords:
            item.add_marker(skip_hardware)
        if "network" in item.keywords:
            item.add_marker(skip_network)


@pytest.fixture
def tmp_config(tmp_path):
    """Create a temporary config.json and return its path."""
    config = {
        "gateway": {
            "name": "TestNode",
            "connection_type": "serial",
            "port": "/dev/ttyUSB0",
            "bitrate": 500,
        },
        "dashboard": {"host": "127.0.0.1", "port": 5000},
        "features": {},
    }
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(config))
    return str(config_file)


@pytest.fixture
def bad_config(tmp_path):
    """Create an invalid JSON config file and return its path."""
    config_file = tmp_path / "config.json"
    config_file.write_text("{invalid json content")
    return str(config_file)


@pytest.fixture
def mock_rns_modules():
    """Build mock modules for RNS so the interface can import."""
    mock_rns = MagicMock()
    mock_rns_interfaces = MagicMock()
    mock_rns_interface = MagicMock()
    mock_rns_interface.Interface = type('Interface', (), {
        'MODE_ACCESS_POINT': 1,
    })
    mock_rns.Interfaces = mock_rns_interfaces
    mock_rns.Interfaces.Interface = mock_rns_interface

    return {
        'RNS': mock_rns,
        'RNS.Interfaces': mock_rns_interfaces,
        'RNS.Interfaces.Interface': mock_rns_interface,
    }


@pytest.fixture
def mock_meshtastic_modules():
    """Build mock modules for meshtastic so the interface can import."""
    mock_mesh = MagicMock()
    mock_serial = MagicMock()
    mock_tcp = MagicMock()
    mock_pub = MagicMock()
    mock_mesh.serial_interface = mock_serial
    mock_mesh.tcp_interface = mock_tcp
    mock_mesh.pub = mock_pub

    return {
        'meshtastic': mock_mesh,
        'meshtastic.serial_interface': mock_serial,
        'meshtastic.tcp_interface': mock_tcp,
        'meshtastic.pub': mock_pub,
    }
