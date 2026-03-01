"""Tests for src/ui/menu.py — TUI menu helpers."""
import sys
import os
from unittest.mock import patch, MagicMock

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.ui.menu import get_editor, get_python, clear_screen, launch_detached, _parse_args


class TestGetEditor:
    def test_returns_string(self):
        """get_editor should always return a non-empty string."""
        editor = get_editor()
        assert isinstance(editor, str)
        assert len(editor) > 0

    def test_env_editor_used_if_valid(self):
        """If $EDITOR is set and found on PATH, it should be used."""
        with patch.dict(os.environ, {'EDITOR': 'nano'}), \
             patch('shutil.which', return_value='/usr/bin/nano'):
            assert get_editor() == 'nano'

    def test_invalid_env_editor_ignored(self):
        """If $EDITOR is set but not found on PATH, it should be ignored."""
        with patch.dict(os.environ, {'EDITOR': '/nonexistent/evil'}), \
             patch('shutil.which', side_effect=lambda x: None if x == '/nonexistent/evil' else '/usr/bin/vi'):
            editor = get_editor()
            assert editor != '/nonexistent/evil'

    def test_windows_default(self):
        """On Windows, default should be notepad."""
        with patch.dict(os.environ, {}, clear=True), \
             patch('os.name', 'nt'), \
             patch('shutil.which', return_value=None):
            assert get_editor() == 'notepad'


class TestGetPython:
    def test_returns_executable(self):
        """get_python should return the current Python executable path."""
        python = get_python()
        assert python == sys.executable

    def test_returns_string(self):
        """get_python should return a non-empty string."""
        python = get_python()
        assert isinstance(python, str)
        assert len(python) > 0


class TestClearScreen:
    def test_does_not_raise_on_posix(self):
        """clear_screen should not raise on POSIX systems."""
        with patch('os.name', 'posix'):
            # Should write ANSI escape codes to stdout without error
            clear_screen()

    def test_does_not_raise_on_nt(self):
        """clear_screen should not raise on Windows (mocked)."""
        with patch('os.name', 'nt'), \
             patch('subprocess.run') as mock_run:
            clear_screen()
            mock_run.assert_called_once()


class TestLaunchDetached:
    def test_returns_true_on_success(self):
        """launch_detached should return True when process starts OK."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # Still running
        with patch('subprocess.Popen', return_value=mock_proc):
            result = launch_detached([sys.executable, '-c', 'pass'])
        assert result is True

    def test_returns_false_on_immediate_exit(self):
        """launch_detached should return False if process exits immediately."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 1  # Exited with error
        mock_proc.returncode = 1
        with patch('subprocess.Popen', return_value=mock_proc):
            result = launch_detached([sys.executable, '-c', 'import sys; sys.exit(1)'])
        assert result is False

    def test_returns_false_on_file_not_found(self):
        """launch_detached should return False when command not found."""
        with patch('subprocess.Popen', side_effect=FileNotFoundError):
            result = launch_detached(['/nonexistent/binary'])
        assert result is False

    def test_returns_false_on_os_error(self):
        """launch_detached should return False on OSError."""
        with patch('subprocess.Popen', side_effect=OSError("test")):
            result = launch_detached(['/some/binary'])
        assert result is False


class TestParseArgs:
    def test_default_no_debug(self):
        """With no args, debug should be False."""
        args = _parse_args([])
        assert args.debug is False

    def test_debug_flag(self):
        """--debug should set debug=True."""
        args = _parse_args(['--debug'])
        assert args.debug is True

    def test_version_flag(self):
        """--version should cause SystemExit."""
        with pytest.raises(SystemExit):
            _parse_args(['--version'])
