"""
Daemon mode for the RNS-Meshtastic Gateway.

Provides CLI-driven service management with PID file locking,
watchdog auto-restart, and systemd integration.

Adapted from MeshForge's src/daemon.py.

Usage:
    python src/daemon.py start              # Run in foreground (for systemd)
    python src/daemon.py stop               # Stop running daemon
    python src/daemon.py status             # Show daemon status
    python src/daemon.py status --json      # JSON status output
    python src/daemon.py restart            # Stop + start
"""

import argparse
import json
import logging
import os
import signal
import sys
import threading
import time
from typing import Any, Dict, Optional, Protocol, runtime_checkable

# Add project root to path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, 'src'))

from src.utils.timeouts import (
    WATCHDOG_INTERVAL,
    WATCHDOG_FAILURES,
    DAEMON_STOP_TIMEOUT,
    THREAD_JOIN,
)

log = logging.getLogger("daemon")


# ── Service Protocol ─────────────────────────────────────────

@runtime_checkable
class DaemonService(Protocol):
    """Protocol for services managed by the daemon."""

    def start(self) -> None: ...
    def stop(self) -> None: ...
    def is_alive(self) -> bool: ...
    def get_status(self) -> Dict[str, Any]: ...


# ── PID File Management ──────────────────────────────────────

def _default_pid_path() -> str:
    """Return the default PID file path: ~/.config/rns-gateway/gateway.pid"""
    from src.utils.common import get_real_user_home
    pid_dir = os.path.join(get_real_user_home(), ".config", "rns-gateway")
    os.makedirs(pid_dir, mode=0o700, exist_ok=True)
    try:
        os.chmod(pid_dir, 0o700)
    except OSError:
        pass
    return os.path.join(pid_dir, "gateway.pid")


class PidFile:
    """PID file management with proper file locking.

    Uses fcntl.flock() on POSIX systems to prevent race conditions
    between concurrent daemon starts (TOCTOU prevention).

    Args:
        path: Path to PID file.  Defaults to ~/.config/rns-gateway/gateway.pid.
    """

    def __init__(self, path: Optional[str] = None):
        self.path = path or _default_pid_path()
        self._lock_fd = None

    def write(self) -> None:
        """Write current PID to file with restrictive permissions."""
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        # Use os.open with explicit mode to avoid default umask
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, str(os.getpid()).encode())
        finally:
            os.close(fd)

    def read(self) -> Optional[int]:
        """Read PID from file.  Returns None if not found or invalid."""
        try:
            with open(self.path, 'r') as f:
                return int(f.read().strip())
        except (FileNotFoundError, ValueError):
            return None

    def is_running(self) -> bool:
        """Check if the PID in the file corresponds to a running process."""
        pid = self.read()
        if pid is None:
            return False
        try:
            os.kill(pid, 0)  # Signal 0 = check existence
            return True
        except (ProcessLookupError, PermissionError):
            return False

    def remove(self) -> None:
        """Remove the PID file."""
        try:
            os.remove(self.path)
        except FileNotFoundError:
            pass

    def acquire(self) -> bool:
        """Acquire PID file lock atomically.

        Uses fcntl.flock() on POSIX to prevent race conditions where
        two processes could both see a stale PID and overwrite each other.
        Falls back to the check-then-write pattern on non-POSIX systems.

        Returns False if another instance is running.
        """
        # Always check if an existing PID is running first
        if self.is_running():
            return False

        try:
            import fcntl
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (OSError, BlockingIOError):
                os.close(fd)
                return False
            # Lock acquired — write PID
            os.ftruncate(fd, 0)
            os.lseek(fd, 0, os.SEEK_SET)
            os.write(fd, str(os.getpid()).encode())
            self._lock_fd = fd
            return True
        except ImportError:
            # Non-POSIX fallback (Windows)
            self.write()
            return True

    def release(self) -> None:
        """Release PID file lock (unlock and remove file if PID matches)."""
        if self._lock_fd is not None:
            try:
                import fcntl
                fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
            except (ImportError, OSError):
                pass
            try:
                os.close(self._lock_fd)
            except OSError:
                pass
            self._lock_fd = None
        pid = self.read()
        if pid == os.getpid():
            self.remove()


# ── Gateway Bridge Service ────────────────────────────────────

class GatewayBridgeService:
    """Wraps launcher.py:start_gateway() as a DaemonService.

    Runs start_gateway() in a dedicated thread so the daemon's
    watchdog can monitor it independently.
    """

    def __init__(self, debug: bool = False):
        self._debug = debug
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._started_at: Optional[float] = None
        self._error: Optional[str] = None

    def start(self) -> None:
        """Start the gateway in a background thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._error = None
        self._started_at = time.time()
        self._thread = threading.Thread(
            target=self._run, name="gateway-service", daemon=False,
        )
        self._thread.start()

    def _run(self) -> None:
        """Thread target: run the gateway, capturing crashes."""
        try:
            import launcher
            # Inject our stop event into launcher module so it can
            # be controlled externally (clean shutdown from daemon)
            launcher._stop_event = self._stop_event
            launcher.start_gateway(debug=self._debug)
        except SystemExit:
            pass  # Normal shutdown path
        except Exception as e:
            self._error = str(e)
            log.error("Gateway service crashed: %s", e, exc_info=True)

    def stop(self) -> None:
        """Signal the gateway to stop and wait for thread to finish."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=DAEMON_STOP_TIMEOUT)
            self._thread = None

    def is_alive(self) -> bool:
        """Check if the gateway thread is still running."""
        return self._thread is not None and self._thread.is_alive()

    def get_status(self) -> Dict[str, Any]:
        """Return JSON-serializable status dict."""
        return {
            "running": self.is_alive(),
            "uptime_seconds": time.time() - self._started_at if self._started_at else 0,
            "error": self._error,
            "pid": os.getpid(),
        }


# ── Watchdog ──────────────────────────────────────────────────

class Watchdog:
    """Monitors a DaemonService and auto-restarts on failure.

    Args:
        service: The service to monitor.
        interval: Seconds between health checks.
        max_failures: Consecutive failures before restart.
    """

    def __init__(
        self,
        service,
        interval: float = WATCHDOG_INTERVAL,
        max_failures: int = WATCHDOG_FAILURES,
    ):
        self._service = service
        self._interval = interval
        self._max_failures = max_failures
        self._consecutive_failures = 0
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._restart_count = 0

    def start(self) -> None:
        """Start the watchdog monitoring thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._watch_loop, name="watchdog", daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop the watchdog thread."""
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=THREAD_JOIN)
            self._thread = None

    def _watch_loop(self) -> None:
        """Background loop: check service health, restart if needed."""
        while not self._stop.is_set():
            self._stop.wait(self._interval)
            if self._stop.is_set():
                break
            try:
                if self._service.is_alive():
                    self._consecutive_failures = 0
                else:
                    self._consecutive_failures += 1
                    log.warning(
                        "Watchdog: service not alive (%d/%d)",
                        self._consecutive_failures, self._max_failures,
                    )
                    if self._consecutive_failures >= self._max_failures:
                        self._restart_service()
            except Exception as e:
                log.error("Watchdog check error: %s", e)

    def _restart_service(self) -> None:
        """Restart the service with exponential backoff."""
        self._restart_count += 1
        backoff = min(2.0 * (2 ** (self._restart_count - 1)), 60.0)
        log.warning(
            "Watchdog: restarting service (attempt %d, backoff %.1fs)",
            self._restart_count, backoff,
        )
        try:
            self._service.stop()
        except Exception as e:
            log.error("Watchdog: error stopping service: %s", e)
        self._stop.wait(backoff)
        if not self._stop.is_set():
            try:
                self._service.start()
                self._consecutive_failures = 0
            except Exception as e:
                log.error("Watchdog: error starting service: %s", e)

    @property
    def restart_count(self) -> int:
        """Number of service restarts performed by the watchdog."""
        return self._restart_count


# ── CLI Commands ──────────────────────────────────────────────

def _cmd_start(args) -> None:
    """Handle 'start' command."""
    pid_file = PidFile(path=getattr(args, 'pid_file', None))
    if not pid_file.acquire():
        existing_pid = pid_file.read()
        print(f"Gateway already running (PID {existing_pid})")
        sys.exit(1)

    from src.utils.log import setup_logging, default_log_path, install_crash_handler
    install_crash_handler()
    setup_logging(
        level=logging.DEBUG if args.debug else logging.INFO,
        log_file=default_log_path(),
    )

    service = GatewayBridgeService(debug=args.debug)
    watchdog = Watchdog(service)

    def handle_signal(signum, frame):
        sig_name = signal.Signals(signum).name
        log.info("Daemon received %s", sig_name)
        if signum in (signal.SIGTERM, signal.SIGINT):
            watchdog.stop()
            service.stop()
            pid_file.release()
            sys.exit(0)
        elif hasattr(signal, 'SIGHUP') and signum == signal.SIGHUP:
            log.info("SIGHUP: restarting service for config reload")
            service.stop()
            service.start()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    if hasattr(signal, 'SIGHUP'):
        signal.signal(signal.SIGHUP, handle_signal)

    service.start()
    watchdog.start()

    log.info("Daemon started (PID %d)", os.getpid())
    print(f"Gateway daemon started (PID {os.getpid()})")

    try:
        # Main loop — keeps the daemon process alive
        while not service._stop_event.is_set():
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("Daemon interrupted")
    finally:
        watchdog.stop()
        service.stop()
        pid_file.release()


def _cmd_stop(args) -> None:
    """Handle 'stop' command."""
    pid_file = PidFile(path=getattr(args, 'pid_file', None))
    pid = pid_file.read()
    if pid is None:
        print("No PID file found. Gateway may not be running.")
        sys.exit(1)
    if not pid_file.is_running():
        print(f"PID {pid} not running. Cleaning up stale PID file.")
        pid_file.remove()
        sys.exit(0)

    print(f"Stopping gateway (PID {pid})...")
    os.kill(pid, signal.SIGTERM)

    # Wait for process to exit
    for _ in range(int(DAEMON_STOP_TIMEOUT)):
        time.sleep(1)
        if not pid_file.is_running():
            print("Gateway stopped.")
            pid_file.remove()
            return
    print(f"Gateway did not stop within {DAEMON_STOP_TIMEOUT}s. Sending SIGKILL...")
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    pid_file.remove()


def _cmd_status(args) -> None:
    """Handle 'status' command."""
    pid_file = PidFile(path=getattr(args, 'pid_file', None))
    pid = pid_file.read()
    running = pid_file.is_running() if pid else False
    status = {
        "running": running,
        "pid": pid,
        "pid_file": pid_file.path,
    }
    if getattr(args, 'json', False):
        print(json.dumps(status, indent=2))
    else:
        state = "running" if running else "stopped"
        pid_info = f" (PID {pid})" if pid else ""
        print(f"Gateway: {state}{pid_info}")


def _cmd_restart(args) -> None:
    """Handle 'restart' command."""
    pid_file = PidFile(path=getattr(args, 'pid_file', None))
    if pid_file.is_running():
        _cmd_stop(args)
        time.sleep(1)
    _cmd_start(args)


# ── Argument Parsing ──────────────────────────────────────────

def _parse_args(argv=None):
    """Parse daemon CLI arguments."""
    parser = argparse.ArgumentParser(
        description="RNS-Meshtastic Gateway Daemon",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_start = sub.add_parser("start", help="Start the gateway daemon")
    p_start.add_argument("--debug", action="store_true",
                         help="Enable debug-level logging")
    p_start.add_argument("--pid-file", default=None,
                         help="Override PID file path")

    p_stop = sub.add_parser("stop", help="Stop the gateway daemon")
    p_stop.add_argument("--pid-file", default=None,
                        help="Override PID file path")

    p_status = sub.add_parser("status", help="Show daemon status")
    p_status.add_argument("--json", action="store_true",
                          help="Output status as JSON")
    p_status.add_argument("--pid-file", default=None,
                          help="Override PID file path")

    p_restart = sub.add_parser("restart", help="Restart the gateway daemon")
    p_restart.add_argument("--debug", action="store_true",
                           help="Enable debug-level logging")
    p_restart.add_argument("--pid-file", default=None,
                           help="Override PID file path")

    return parser.parse_args(argv)


# ── Entry Point ───────────────────────────────────────────────

def main(argv=None):
    """Daemon CLI entry point."""
    args = _parse_args(argv)

    if args.command == "start":
        _cmd_start(args)
    elif args.command == "stop":
        _cmd_stop(args)
    elif args.command == "status":
        _cmd_status(args)
    elif args.command == "restart":
        _cmd_restart(args)


if __name__ == "__main__":
    main()
