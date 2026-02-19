"""Tests for src/utils/common.py — config loading."""
from unittest.mock import patch


class TestLoadConfig:
    def test_load_valid_config(self, tmp_config):
        with patch('src.utils.common.CONFIG_PATH', tmp_config):
            from src.utils.common import load_config
            cfg = load_config()
            assert cfg['gateway']['name'] == 'TestNode'
            assert cfg['gateway']['connection_type'] == 'serial'

    def test_missing_config_returns_default_fallback(self, tmp_path):
        missing = str(tmp_path / "nonexistent.json")
        with patch('src.utils.common.CONFIG_PATH', missing):
            from src.utils.common import load_config
            assert load_config() == {}

    def test_invalid_json_returns_fallback(self, bad_config):
        with patch('src.utils.common.CONFIG_PATH', bad_config):
            from src.utils.common import load_config
            assert load_config() == {}

    def test_custom_fallback(self, tmp_path):
        missing = str(tmp_path / "nonexistent.json")
        with patch('src.utils.common.CONFIG_PATH', missing):
            from src.utils.common import load_config
            assert load_config(fallback=None) is None

    def test_custom_dict_fallback(self, tmp_path):
        missing = str(tmp_path / "nonexistent.json")
        sentinel = {"gateway": {"name": "Fallback"}}
        with patch('src.utils.common.CONFIG_PATH', missing):
            from src.utils.common import load_config
            result = load_config(fallback=sentinel)
            assert result['gateway']['name'] == 'Fallback'
