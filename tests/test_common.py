"""Tests for src/utils/common.py — config loading and validation."""
import os
from unittest.mock import patch

from src.utils.common import (
    validate_hostname, validate_port, validate_config,
    validate_message_length, get_real_user_home, check_config_permissions,
)


class TestValidateHostname:
    def test_valid_localhost(self):
        ok, _ = validate_hostname("localhost")
        assert ok

    def test_valid_ip(self):
        ok, _ = validate_hostname("192.168.1.1")
        assert ok

    def test_valid_ipv6_colon(self):
        ok, _ = validate_hostname("::1")
        assert ok

    def test_flag_injection_rejected(self):
        ok, err = validate_hostname("-evil")
        assert not ok
        assert "flag injection" in err

    def test_too_long_rejected(self):
        ok, _ = validate_hostname("a" * 254)
        assert not ok

    def test_exactly_253_ok(self):
        ok, _ = validate_hostname("a" * 253)
        assert ok

    def test_invalid_chars_rejected(self):
        ok, _ = validate_hostname("host; rm -rf /")
        assert not ok

    def test_empty_rejected(self):
        ok, _ = validate_hostname("")
        assert not ok

    def test_none_rejected(self):
        ok, _ = validate_hostname(None)
        assert not ok

    def test_int_rejected(self):
        ok, _ = validate_hostname(123)
        assert not ok


class TestValidatePort:
    def test_valid_port(self):
        ok, _ = validate_port(5000)
        assert ok

    def test_port_1(self):
        ok, _ = validate_port(1)
        assert ok

    def test_port_65535(self):
        ok, _ = validate_port(65535)
        assert ok

    def test_zero_rejected(self):
        ok, _ = validate_port(0)
        assert not ok

    def test_negative_rejected(self):
        ok, _ = validate_port(-1)
        assert not ok

    def test_too_high_rejected(self):
        ok, _ = validate_port(70000)
        assert not ok

    def test_string_rejected(self):
        ok, _ = validate_port("5000")
        assert not ok

    def test_bool_rejected(self):
        ok, _ = validate_port(True)
        assert not ok

    def test_float_rejected(self):
        ok, _ = validate_port(5000.0)
        assert not ok


class TestValidateConfig:
    def test_valid_serial_config(self):
        cfg = {"gateway": {"connection_type": "serial", "bitrate": 500}}
        assert validate_config(cfg) == []

    def test_valid_tcp_config(self):
        cfg = {"gateway": {"connection_type": "tcp", "host": "localhost", "tcp_port": 4403}}
        assert validate_config(cfg) == []

    def test_invalid_connection_type(self):
        cfg = {"gateway": {"connection_type": "bluetooth"}}
        warnings = validate_config(cfg)
        assert len(warnings) >= 1
        assert any("connection_type" in w for w in warnings)

    def test_invalid_host_flag_injection(self):
        cfg = {"gateway": {"host": "-evil"}}
        warnings = validate_config(cfg)
        assert any("host" in w.lower() for w in warnings)

    def test_invalid_tcp_port_string(self):
        cfg = {"gateway": {"tcp_port": "not_a_number"}}
        warnings = validate_config(cfg)
        assert len(warnings) >= 1

    def test_invalid_tcp_port_out_of_range(self):
        cfg = {"gateway": {"tcp_port": 99999}}
        warnings = validate_config(cfg)
        assert len(warnings) >= 1

    def test_invalid_bitrate(self):
        cfg = {"gateway": {"bitrate": -10}}
        warnings = validate_config(cfg)
        assert any("bitrate" in w for w in warnings)

    def test_invalid_dashboard_port(self):
        cfg = {"dashboard": {"port": 0}}
        warnings = validate_config(cfg)
        assert len(warnings) >= 1

    def test_invalid_dashboard_host(self):
        cfg = {"dashboard": {"host": "evil; cmd"}}
        warnings = validate_config(cfg)
        assert any("dashboard.host" in w for w in warnings)

    def test_not_dict(self):
        assert validate_config("not a dict") == ["Config is not a JSON object"]

    def test_empty_dict_is_valid(self):
        assert validate_config({}) == []


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


class TestValidateMessageLength:
    def test_within_limit(self):
        ok, msg = validate_message_length(b'\x00' * 100)
        assert ok is True
        assert "100 bytes OK" in msg

    def test_exactly_at_limit(self):
        ok, msg = validate_message_length(b'\x00' * 228)
        assert ok is True

    def test_exceeds_limit(self):
        ok, msg = validate_message_length(b'\x00' * 300)
        assert ok is False
        assert "exceeds" in msg

    def test_empty_data(self):
        ok, msg = validate_message_length(b'')
        assert ok is True
        assert "0 bytes OK" in msg

    def test_custom_limit(self):
        ok, msg = validate_message_length(b'\x00' * 50, max_bytes=10)
        assert ok is False

    def test_non_bytes_rejected(self):
        ok, msg = validate_message_length("not bytes")
        assert ok is False
        assert "must be bytes" in msg


class TestGetRealUserHome:
    def test_returns_string(self):
        home = get_real_user_home()
        assert isinstance(home, str)
        assert len(home) > 0

    def test_uses_sudo_user_when_set(self):
        """When SUDO_USER is set, should resolve that user's home."""
        import pwd
        # Use current user as the sudo user for testing
        current_user = os.environ.get('USER', 'root')
        try:
            expected_home = pwd.getpwnam(current_user).pw_dir
        except (KeyError, ImportError):
            return  # Skip on systems where pwd lookup fails

        with patch.dict(os.environ, {'SUDO_USER': current_user}):
            home = get_real_user_home()
            assert home == expected_home

    def test_falls_back_without_sudo_user(self):
        """Without SUDO_USER, should use os.path.expanduser."""
        env = dict(os.environ)
        env.pop('SUDO_USER', None)
        with patch.dict(os.environ, env, clear=True):
            home = get_real_user_home()
            assert home == os.path.expanduser("~")


class TestCheckConfigPermissions:
    def test_world_readable_warned(self, tmp_path):
        """World-readable config should produce a warning."""
        config_file = tmp_path / "config.json"
        config_file.write_text("{}")
        config_file.chmod(0o644)  # world-readable

        if os.name != 'posix':
            return  # Only meaningful on POSIX

        warnings = check_config_permissions(str(config_file))
        assert any("world-readable" in w for w in warnings)

    def test_secure_permissions_no_warning(self, tmp_path):
        """Config with 600 perms should produce no warnings."""
        config_file = tmp_path / "config.json"
        config_file.write_text("{}")
        config_file.chmod(0o600)

        if os.name != 'posix':
            return

        warnings = check_config_permissions(str(config_file))
        assert len(warnings) == 0

    def test_nonexistent_file_no_warning(self, tmp_path):
        """Missing config file should not raise or warn."""
        warnings = check_config_permissions(str(tmp_path / "missing.json"))
        assert len(warnings) == 0


class TestValidateConfigExtended:
    """Additional config validation edge cases."""

    def test_empty_features_is_valid(self):
        cfg = {"features": {}}
        assert validate_config(cfg) == []

    def test_features_with_values_is_valid(self):
        cfg = {"features": {"circuit_breaker": True, "tx_queue": False}}
        assert validate_config(cfg) == []

    def test_bitrate_zero_rejected(self):
        cfg = {"gateway": {"bitrate": 0}}
        warnings = validate_config(cfg)
        assert any("bitrate" in w for w in warnings)

    def test_bitrate_string_rejected(self):
        cfg = {"gateway": {"bitrate": "fast"}}
        warnings = validate_config(cfg)
        assert any("bitrate" in w for w in warnings)

    def test_dashboard_host_invalid(self):
        cfg = {"dashboard": {"host": "-evil"}}
        warnings = validate_config(cfg)
        assert any("dashboard.host" in w for w in warnings)

    def test_gateway_section_not_dict(self):
        cfg = {"gateway": "not a dict"}
        warnings = validate_config(cfg)
        assert any("gateway section" in w for w in warnings)
