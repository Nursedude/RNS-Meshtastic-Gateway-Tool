"""Tests for src/utils/log.py — logging configuration and JSON formatter."""
import json
import logging

import pytest

from src.utils.log import JsonFormatter


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
