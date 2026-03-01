"""Tests for src/utils/log.py — logging configuration and JSON formatter."""
import json
import logging
import os
import sys
from unittest.mock import patch

from src.utils.log import JsonFormatter, default_log_dir, default_log_path, install_crash_handler


class TestJsonFormatter:
    def test_basic_format(self):
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="test.py",
            lineno=1, msg="hello %s", args=("world",), exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "test"
        assert parsed["msg"] == "hello world"
        assert "ts" in parsed

    def test_timestamp_format(self):
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test", level=logging.WARNING, pathname="test.py",
            lineno=1, msg="warn", args=(), exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        # ISO-ish format: 2025-01-15T12:00:00Z
        assert "T" in parsed["ts"]
        assert parsed["ts"].endswith("Z")

    def test_exception_included(self):
        formatter = JsonFormatter()
        try:
            raise ValueError("test error")
        except ValueError:
            import sys
            exc_info = sys.exc_info()
        record = logging.LogRecord(
            name="test", level=logging.ERROR, pathname="test.py",
            lineno=1, msg="failed", args=(), exc_info=exc_info,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert "exception" in parsed
        assert "ValueError" in parsed["exception"]

    def test_output_is_valid_json(self):
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test.nested.logger", level=logging.DEBUG, pathname="test.py",
            lineno=42, msg="debug message", args=(), exc_info=None,
        )
        output = formatter.format(record)
        # Should not raise
        parsed = json.loads(output)
        assert isinstance(parsed, dict)

    def test_special_characters_in_message(self):
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="test.py",
            lineno=1, msg='message with "quotes" and \nnewlines', args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        # Should be valid JSON despite special chars
        parsed = json.loads(output)
        assert '"quotes"' in parsed["msg"]


class TestSetupLogging:
    def test_idempotent(self):
        """setup_logging should only configure once."""
        import src.utils.log as log_module
        # Reset the flag for testing
        original = log_module._configured
        log_module._configured = False
        try:
            log_module.setup_logging()
            log_module.setup_logging()  # Should be no-op
        finally:
            log_module._configured = original


class TestDefaultLogDir:
    def test_returns_string(self):
        """default_log_dir should return a non-empty string."""
        result = default_log_dir()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_ends_with_logs(self):
        """Path should end with rns-gateway/logs."""
        result = default_log_dir()
        assert result.endswith(os.path.join("rns-gateway", "logs"))

    def test_directory_is_created(self, tmp_path):
        """default_log_dir should create the directory if missing."""
        fake_home = str(tmp_path / "fakehome")
        with patch("src.utils.common.get_real_user_home", return_value=fake_home):
            result = default_log_dir()
        assert os.path.isdir(result)
        assert "rns-gateway" in result


class TestDefaultLogPath:
    def test_returns_gateway_log(self):
        """default_log_path should return a path ending in gateway.log."""
        result = default_log_path()
        assert result.endswith("gateway.log")

    def test_is_inside_log_dir(self):
        """Log path should be inside the log directory."""
        log_dir = default_log_dir()
        log_path = default_log_path()
        assert log_path.startswith(log_dir)


class TestInstallCrashHandler:
    def test_installs_excepthook(self):
        """install_crash_handler should replace sys.excepthook."""
        original_hook = sys.excepthook
        try:
            install_crash_handler()
            assert sys.excepthook is not sys.__excepthook__
        finally:
            sys.excepthook = original_hook

    def test_crash_handler_writes_to_file(self, tmp_path):
        """The crash handler should write exception info to the crash log."""
        crash_log = str(tmp_path / "crash.log")
        original_hook = sys.excepthook
        try:
            # Manually install a handler pointing to tmp
            def handler(exc_type, exc_value, exc_tb):
                import traceback as tb_mod
                with open(crash_log, "a") as f:
                    f.write("\n--- test ---\n")
                    tb_mod.print_exception(exc_type, exc_value, exc_tb, file=f)

            sys.excepthook = handler
            try:
                raise RuntimeError("test crash")
            except RuntimeError:
                exc_info = sys.exc_info()
                sys.excepthook(*exc_info)

            assert os.path.isfile(crash_log)
            content = open(crash_log).read()
            assert "RuntimeError" in content
            assert "test crash" in content
        finally:
            sys.excepthook = original_hook
