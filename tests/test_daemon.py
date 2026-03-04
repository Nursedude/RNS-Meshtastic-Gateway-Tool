"""Tests for src/daemon.py — daemon mode, PID management, watchdog."""
import json
import os
import threading
import time
from unittest.mock import MagicMock

from src.daemon import (
    PidFile,
    GatewayBridgeService,
    Watchdog,
    _cmd_status,
    _parse_args,
)


# ── PID File tests ─────────────────────────────────────────────


class TestPidFile:
    def test_write_and_read(self, tmp_path):
        pf = PidFile(path=str(tmp_path / "test.pid"))
        pf.write()
        assert pf.read() == os.getpid()

    def test_read_nonexistent(self, tmp_path):
        pf = PidFile(path=str(tmp_path / "nofile.pid"))
        assert pf.read() is None

    def test_is_running_current_process(self, tmp_path):
        pf = PidFile(path=str(tmp_path / "test.pid"))
        pf.write()
        assert pf.is_running() is True

    def test_is_running_dead_process(self, tmp_path):
        pf = PidFile(path=str(tmp_path / "test.pid"))
        with open(pf.path, 'w') as f:
            f.write("999999999")  # Non-existent PID
        assert pf.is_running() is False

    def test_is_running_no_file(self, tmp_path):
        pf = PidFile(path=str(tmp_path / "nofile.pid"))
        assert pf.is_running() is False

    def test_remove(self, tmp_path):
        pf = PidFile(path=str(tmp_path / "test.pid"))
        pf.write()
        pf.remove()
        assert not os.path.exists(pf.path)

    def test_remove_nonexistent(self, tmp_path):
        pf = PidFile(path=str(tmp_path / "nofile.pid"))
        pf.remove()  # Should not raise

    def test_acquire_success(self, tmp_path):
        pf = PidFile(path=str(tmp_path / "test.pid"))
        assert pf.acquire() is True
        assert pf.read() == os.getpid()

    def test_acquire_fails_if_running(self, tmp_path):
        pf = PidFile(path=str(tmp_path / "test.pid"))
        pf.write()  # Current PID is running
        pf2 = PidFile(path=str(tmp_path / "test.pid"))
        assert pf2.acquire() is False

    def test_acquire_overwrites_stale(self, tmp_path):
        pf = PidFile(path=str(tmp_path / "test.pid"))
        with open(pf.path, 'w') as f:
            f.write("999999999")  # Stale PID
        assert pf.acquire() is True
        assert pf.read() == os.getpid()

    def test_release(self, tmp_path):
        pf = PidFile(path=str(tmp_path / "test.pid"))
        pf.write()
        pf.release()
        assert not os.path.exists(pf.path)

    def test_release_wrong_pid(self, tmp_path):
        pf = PidFile(path=str(tmp_path / "test.pid"))
        with open(pf.path, 'w') as f:
            f.write("999999999")
        pf.release()
        # Should NOT remove because PID doesn't match
        assert os.path.exists(pf.path)


# ── GatewayBridgeService tests ─────────────────────────────────


class TestGatewayBridgeService:
    def test_initial_state(self):
        svc = GatewayBridgeService()
        assert svc.is_alive() is False
        status = svc.get_status()
        assert status['running'] is False

    def test_get_status_includes_pid(self):
        svc = GatewayBridgeService()
        status = svc.get_status()
        assert status['pid'] == os.getpid()

    def test_double_start_safe(self):
        svc = GatewayBridgeService()
        mock_thread = MagicMock()
        mock_thread.is_alive.return_value = True
        svc._thread = mock_thread
        svc.start()  # Should not create new thread
        mock_thread.start.assert_not_called()

    def test_stop_without_start_safe(self):
        svc = GatewayBridgeService()
        svc.stop()  # Should not raise

    def test_start_with_mock_launcher(self):
        svc = GatewayBridgeService()
        # Use a simple thread that sleeps, simulating a running gateway
        def mock_run():
            while not svc._stop_event.is_set():
                svc._stop_event.wait(0.1)

        svc._thread = threading.Thread(target=mock_run, daemon=True)
        svc._started_at = time.time()
        svc._thread.start()
        assert svc.is_alive() is True
        svc.stop()
        assert svc.is_alive() is False


# ── Watchdog tests ─────────────────────────────────────────────


class _MockService:
    """A simple mock service for watchdog testing."""

    def __init__(self, alive=True):
        self._alive = alive
        self.start_count = 0
        self.stop_count = 0

    def start(self):
        self.start_count += 1
        self._alive = True

    def stop(self):
        self.stop_count += 1
        self._alive = False

    def is_alive(self):
        return self._alive

    def get_status(self):
        return {"running": self._alive}


class TestWatchdog:
    def test_healthy_service_no_restart(self):
        service = _MockService(alive=True)
        wd = Watchdog(service, interval=0.1, max_failures=2)
        wd.start()
        time.sleep(0.5)
        wd.stop()
        assert service.stop_count == 0

    def test_unhealthy_triggers_restart(self):
        service = _MockService(alive=False)
        # Keep service dead even after restart attempts
        original_start = service.start
        def stubborn_start():
            original_start()
            service._alive = False  # Stay dead to keep triggering restarts
        service.start = stubborn_start

        wd = Watchdog(service, interval=0.1, max_failures=2)
        wd.start()
        time.sleep(3.0)  # Allow time for detection + backoff + restart
        wd.stop()
        assert service.stop_count >= 1
        assert service.start_count >= 1

    def test_restart_count_increments(self):
        service = _MockService(alive=False)
        wd = Watchdog(service, interval=0.1, max_failures=1)
        wd.start()
        time.sleep(1.0)
        wd.stop()
        assert wd.restart_count >= 1

    def test_start_stop_idempotent(self):
        service = _MockService(alive=True)
        wd = Watchdog(service)
        wd.start()
        wd.start()  # Should not raise
        wd.stop()
        wd.stop()  # Should not raise

    def test_stop_without_start_safe(self):
        service = _MockService(alive=True)
        wd = Watchdog(service)
        wd.stop()  # Should not raise


# ── CLI tests ──────────────────────────────────────────────────


class TestCmdStatus:
    def test_status_not_running(self, tmp_path, capsys):
        args = MagicMock()
        args.json = False
        args.pid_file = str(tmp_path / "test.pid")

        _cmd_status(args)
        captured = capsys.readouterr()
        assert "stopped" in captured.out

    def test_status_json_output(self, tmp_path, capsys):
        pid_path = str(tmp_path / "test.pid")
        with open(pid_path, 'w') as f:
            f.write(str(os.getpid()))

        args = MagicMock()
        args.json = True
        args.pid_file = pid_path

        _cmd_status(args)
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data['running'] is True
        assert data['pid'] == os.getpid()

    def test_status_running_plain(self, tmp_path, capsys):
        pid_path = str(tmp_path / "test.pid")
        with open(pid_path, 'w') as f:
            f.write(str(os.getpid()))

        args = MagicMock()
        args.json = False
        args.pid_file = pid_path

        _cmd_status(args)
        captured = capsys.readouterr()
        assert "running" in captured.out


class TestParseArgs:
    def test_start_command(self):
        args = _parse_args(["start"])
        assert args.command == "start"

    def test_start_with_debug(self):
        args = _parse_args(["start", "--debug"])
        assert args.command == "start"
        assert args.debug is True

    def test_stop_command(self):
        args = _parse_args(["stop"])
        assert args.command == "stop"

    def test_status_command(self):
        args = _parse_args(["status"])
        assert args.command == "status"

    def test_status_with_json(self):
        args = _parse_args(["status", "--json"])
        assert args.command == "status"
        assert args.json is True

    def test_restart_command(self):
        args = _parse_args(["restart"])
        assert args.command == "restart"

    def test_pid_file_override(self):
        args = _parse_args(["start", "--pid-file", "/tmp/test.pid"])
        assert args.pid_file == "/tmp/test.pid"
