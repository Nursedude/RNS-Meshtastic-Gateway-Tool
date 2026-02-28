"""Tests for src/utils/service_check.py — environment probes."""
from unittest.mock import patch, MagicMock

from src.utils.service_check import (
    check_rns_lib,
    check_meshtastic_lib,
    check_serial_ports,
    check_rns_config,
    check_rnsd_status,
    check_meshtasticd_status,
    check_rns_udp_port,
    check_tcp_port,
    check_serial_device,
    check_serial_ports_detailed,
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


class TestCheckMeshtasticdStatus:
    def test_running_via_systemctl(self):
        """meshtasticd active via systemctl, port verification included."""
        mock_result = MagicMock(returncode=0, stdout="active\n")
        with patch('subprocess.run', return_value=mock_result), \
             patch('src.utils.service_check.check_tcp_port', return_value=(True, "listening")):
            ok, info = check_meshtasticd_status()
            assert ok is True
            assert "active" in info

    def test_inactive_via_systemctl(self):
        """meshtasticd inactive via systemctl."""
        mock_result = MagicMock(returncode=3, stdout="inactive\n")
        with patch('subprocess.run', return_value=mock_result):
            ok, info = check_meshtasticd_status()
            assert ok is False
            assert "inactive" in info

    def test_fallback_to_pgrep_running(self):
        """Falls back to pgrep when systemctl is unavailable."""
        call_count = [0]

        def mock_run(cmd, **kwargs):
            call_count[0] += 1
            if cmd[0] == 'systemctl':
                raise FileNotFoundError("no systemctl")
            # pgrep call
            result = MagicMock(returncode=0, stdout="9876\n")
            return result

        with patch('subprocess.run', side_effect=mock_run):
            ok, info = check_meshtasticd_status()
            assert ok is True
            assert "9876" in info

    def test_fallback_to_pgrep_not_running(self):
        """Falls back to pgrep, meshtasticd not running."""
        def mock_run(cmd, **kwargs):
            if cmd[0] == 'systemctl':
                raise FileNotFoundError("no systemctl")
            return MagicMock(returncode=1, stdout="")

        with patch('subprocess.run', side_effect=mock_run):
            ok, info = check_meshtasticd_status()
            assert ok is False
            assert "not running" in info

    def test_both_unavailable(self):
        """Neither systemctl nor pgrep available."""
        with patch('subprocess.run', side_effect=FileNotFoundError):
            ok, info = check_meshtasticd_status()
            assert ok is False
            assert "pgrep unavailable" in info


class TestCheckRnsUdpPort:
    def test_port_in_use_via_proc(self):
        """Passive /proc/net/udp scan detects port in use."""
        # Port 37428 = 0x9234
        proc_content = (
            "  sl  local_address rem_address   st\n"
            "   0: 00000000:9234 00000000:0000 07\n"
        )
        with patch('os.path.isfile', return_value=True), \
             patch('builtins.open', create=True) as mock_open:
            mock_open.return_value.__enter__ = lambda s: iter(proc_content.splitlines())
            mock_open.return_value.__exit__ = MagicMock(return_value=False)
            ok, info = check_rns_udp_port()
            assert ok is True
            assert "in use" in info

    def test_port_not_in_use_via_proc(self):
        """Passive /proc/net/udp scan shows port not in use."""
        proc_content = (
            "  sl  local_address rem_address   st\n"
            "   0: 00000000:1234 00000000:0000 07\n"
        )
        with patch('os.path.isfile', return_value=True), \
             patch('builtins.open', create=True) as mock_open:
            mock_open.return_value.__enter__ = lambda s: iter(proc_content.splitlines())
            mock_open.return_value.__exit__ = MagicMock(return_value=False)
            ok, info = check_rns_udp_port()
            assert ok is False
            assert "not in use" in info

    def test_fallback_socket_probe_port_in_use(self):
        """Socket probe fallback when /proc/net/udp is unavailable."""
        with patch('os.path.isfile', return_value=False), \
             patch('socket.socket') as mock_sock_cls:
            mock_sock = MagicMock()
            mock_sock.bind.side_effect = OSError("Address already in use")
            mock_sock_cls.return_value = mock_sock
            ok, info = check_rns_udp_port()
            assert ok is True
            assert "in use" in info

    def test_fallback_socket_probe_port_free(self):
        """Socket probe fallback when /proc/net/udp is unavailable."""
        with patch('os.path.isfile', return_value=False), \
             patch('socket.socket') as mock_sock_cls:
            mock_sock = MagicMock()
            mock_sock_cls.return_value = mock_sock
            ok, info = check_rns_udp_port()
            assert ok is False
            assert "not in use" in info


class TestCheckTcpPort:
    def test_port_listening(self):
        """TCP port accepting connections."""
        with patch('src.utils.service_check.socket.socket') as mock_cls:
            mock_sock = MagicMock()
            mock_sock.connect_ex.return_value = 0
            mock_cls.return_value.__enter__ = lambda s: mock_sock
            mock_cls.return_value.__exit__ = MagicMock(return_value=False)
            ok, info = check_tcp_port(4403)
            assert ok is True
            assert "listening" in info

    def test_port_not_listening(self):
        """TCP port not accepting connections."""
        with patch('src.utils.service_check.socket.socket') as mock_cls:
            mock_sock = MagicMock()
            mock_sock.connect_ex.return_value = 111  # ECONNREFUSED
            mock_cls.return_value.__enter__ = lambda s: mock_sock
            mock_cls.return_value.__exit__ = MagicMock(return_value=False)
            ok, info = check_tcp_port(4403)
            assert ok is False
            assert "not listening" in info

    def test_port_check_error(self):
        """TCP port check raises OSError."""
        with patch('src.utils.service_check.socket.socket') as mock_cls:
            mock_cls.return_value.__enter__ = MagicMock(
                side_effect=OSError("network error")
            )
            mock_cls.return_value.__exit__ = MagicMock(return_value=False)
            ok, info = check_tcp_port(4403)
            assert ok is False
            assert "failed" in info


class TestCheckSerialDevice:
    def test_device_exists(self, tmp_path):
        """Serial device path exists and is accessible."""
        dev = tmp_path / "ttyUSB0"
        dev.touch()
        ok, info = check_serial_device(str(dev))
        assert ok is True
        assert "OK" in info

    def test_device_missing(self, tmp_path):
        """Serial device path does not exist."""
        ok, info = check_serial_device(str(tmp_path / "nope"))
        assert ok is False
        assert "not found" in info


class TestCheckSerialPortsDetailed:
    def test_returns_list(self):
        """Returns list of dicts even when empty."""
        mock_lp = MagicMock()
        mock_lp.comports.return_value = []
        with patch.dict('sys.modules', {
            'serial': MagicMock(),
            'serial.tools': MagicMock(),
            'serial.tools.list_ports': mock_lp,
        }):
            result = check_serial_ports_detailed()
            assert isinstance(result, list)
