"""Tests for src/ui/dashboard.py — system resource helpers."""
import os
import sys
from unittest.mock import patch, mock_open

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.ui.dashboard import _get_uptime, _get_memory, _get_disk


class TestGetUptime:
    def test_returns_string_on_linux(self):
        """On Linux, _get_uptime should return a formatted string."""
        with patch("os.path.isfile", return_value=True), \
             patch("builtins.open", mock_open(read_data="86523.45 172000.12\n")):
            result = _get_uptime()
        assert result is not None
        assert isinstance(result, str)
        assert "h" in result or "d" in result or "m" in result

    def test_formats_days_hours_minutes(self):
        """Should format 1d 0h 2m correctly."""
        # 86520 seconds = 1d 0h 2m
        with patch("os.path.isfile", return_value=True), \
             patch("builtins.open", mock_open(read_data="86520.0 0\n")):
            result = _get_uptime()
        assert "1d" in result
        assert "2m" in result

    def test_returns_none_when_no_proc(self):
        """Should return None when /proc/uptime doesn't exist."""
        with patch("os.path.isfile", return_value=False):
            result = _get_uptime()
        assert result is None

    def test_handles_oserror(self):
        """Should return None on OSError."""
        with patch("os.path.isfile", return_value=True), \
             patch("builtins.open", side_effect=OSError):
            result = _get_uptime()
        assert result is None


class TestGetMemory:
    MEMINFO = (
        "MemTotal:        8000000 kB\n"
        "MemFree:         2000000 kB\n"
        "MemAvailable:    4000000 kB\n"
        "Buffers:          500000 kB\n"
    )

    def test_returns_tuple_on_linux(self):
        """On Linux, _get_memory should return (used_mb, total_mb)."""
        with patch("os.path.isfile", return_value=True), \
             patch("builtins.open", mock_open(read_data=self.MEMINFO)):
            result = _get_memory()
        assert result is not None
        used_mb, total_mb = result
        assert total_mb == pytest.approx(8000000 / 1024, rel=0.01)
        assert used_mb == pytest.approx((8000000 - 4000000) / 1024, rel=0.01)

    def test_returns_none_when_no_proc(self):
        """Should return None when /proc/meminfo doesn't exist."""
        with patch("os.path.isfile", return_value=False):
            result = _get_memory()
        assert result is None


class TestGetDisk:
    def test_returns_tuple(self):
        """_get_disk should return (used_gb, total_gb)."""
        result = _get_disk()
        if result is not None:
            used_gb, total_gb = result
            assert total_gb > 0
            assert used_gb >= 0
            assert used_gb <= total_gb

    def test_handles_oserror(self):
        """Should return None on OSError."""
        with patch("shutil.disk_usage", side_effect=OSError):
            result = _get_disk()
        assert result is None
