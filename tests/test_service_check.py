"""Tests for src/utils/service_check.py — environment probes."""
from unittest.mock import patch, MagicMock

from src.utils.service_check import (
    check_rns_lib,
    check_meshtastic_lib,
    check_serial_ports,
    check_rns_config,
    check_rnsd_status,
    check_rns_udp_port,
)


class TestCheckRnsLib:
    def test_available(self):
        mock_rns = MagicMock(__version__='0.7.4')
        with patch.dict('sys.modules', {'RNS': mock_rns}):
            ok, ver = check_rns_lib()
            assert ok is True
            assert ver == '0.7.4'

    def test_missing(self):
        def fake_import(name, *args, **kwargs):
            if name == 'RNS':
                raise ImportError("no RNS")
            return original_import(name, *args, **kwargs)

        import builtins
        original_import = builtins.__import__
        with patch('builtins.__import__', side_effect=fake_import):
            ok, ver = check_rns_lib()
            assert ok is False
            assert ver == "not installed"


class TestCheckMeshtasticLib:
    def test_available(self):
        mock_mesh = MagicMock(__version__='2.3.0')
        with patch.dict('sys.modules', {'meshtastic': mock_mesh}):
            ok, ver = check_meshtastic_lib()
            assert ok is True
            assert ver == '2.3.0'

    def test_missing(self):
        def fake_import(name, *args, **kwargs):
            if name == 'meshtastic':
                raise ImportError("no meshtastic")
            return original_import(name, *args, **kwargs)

        import builtins
        original_import = builtins.__import__
        with patch('builtins.__import__', side_effect=fake_import):
            ok, ver = check_meshtastic_lib()
            assert ok is False
            assert ver == "not installed"


class TestCheckSerialPorts:
    def test_with_ports(self):
        mock_port = MagicMock()
        mock_port.device = '/dev/ttyUSB0'
        mock_list_ports = MagicMock()
        mock_list_ports.comports.return_value = [mock_port]
        mock_serial_tools = MagicMock()
        mock_serial_tools.list_ports = mock_list_ports
        mock_serial = MagicMock()
        mock_serial.tools = mock_serial_tools
        with patch.dict('sys.modules', {
            'serial': mock_serial,
            'serial.tools': mock_serial_tools,
            'serial.tools.list_ports': mock_list_ports,
        }):
            ports = check_serial_ports()
            assert ports == ['/dev/ttyUSB0']

    def test_no_ports(self):
        mock_list_ports = MagicMock()
        mock_list_ports.comports.return_value = []
        with patch.dict('sys.modules', {
            'serial': MagicMock(),
            'serial.tools': MagicMock(),
            'serial.tools.list_ports': mock_list_ports,
        }):
            ports = check_serial_ports()
            assert ports == ['(none detected)']


class TestCheckRnsConfig:
    def test_config_exists(self, tmp_path):
        config_file = tmp_path / "config"
        config_file.write_text("test config content")
        with patch('src.utils.common.RNS_CONFIG_FILE', str(config_file)):
            ok, info = check_rns_config()
            assert ok is True
            assert "bytes" in info

    def test_config_missing(self, tmp_path):
        missing = str(tmp_path / "nonexistent")
        with patch('src.utils.common.RNS_CONFIG_FILE', missing):
            ok, info = check_rns_config()
            assert ok is False
            assert info == "not found"


class TestCheckRnsdStatus:
    def test_running(self):
        mock_result = MagicMock(returncode=0, stdout="12345\n")
        with patch('subprocess.run', return_value=mock_result):
            ok, info = check_rnsd_status()
            assert ok is True
            assert "12345" in info

    def test_not_running(self):
        mock_result = MagicMock(returncode=1, stdout="")
        with patch('subprocess.run', return_value=mock_result):
            ok, info = check_rnsd_status()
            assert ok is False
            assert info == "not running"

    def test_pgrep_unavailable(self):
        with patch('subprocess.run', side_effect=FileNotFoundError):
            ok, info = check_rnsd_status()
            assert ok is False
            assert "pgrep unavailable" in info


class TestCheckRnsUdpPort:
    def test_port_in_use(self):
        with patch('socket.socket') as mock_sock_cls:
            mock_sock = MagicMock()
            mock_sock.bind.side_effect = OSError("Address already in use")
            mock_sock_cls.return_value = mock_sock
            ok, info = check_rns_udp_port()
            assert ok is True
            assert "in use" in info

    def test_port_not_in_use(self):
        with patch('socket.socket') as mock_sock_cls:
            mock_sock = MagicMock()
            mock_sock_cls.return_value = mock_sock
            ok, info = check_rns_udp_port()
            assert ok is False
            assert "not in use" in info
