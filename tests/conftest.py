import json
import os
import sys

import pytest

# Ensure project root is on sys.path so src.* imports work
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


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
