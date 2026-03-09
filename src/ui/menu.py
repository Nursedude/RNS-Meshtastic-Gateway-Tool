import argparse
import logging
import os
import subprocess
import shutil
import sys
import time
import webbrowser

# Ensure project root is on path for imports
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from version import __version__ as VERSION
from src.ui.widgets import (
    C, cols, center,
    box_top, box_mid, box_bot, box_row, box_section,
)
from src.utils.common import CONFIG_PATH, NOMAD_CONFIG, RNS_CONFIG_FILE, load_config, validate_port
from src.utils.log import setup_logging, default_log_path, install_crash_handler
from src.utils.service_check import check_rnsd_status, check_meshtasticd_status
from src.utils.timeouts import STATUS_CACHE_TTL

log = logging.getLogger("menu")


# ── Service Status Cache (MeshForge StatusBar pattern) ───────
class _StatusCache:
    """TTL cache for service status checks.

    Avoids shelling out to pgrep/systemctl on every menu redraw.
    Noticeably faster on Raspberry Pi hardware.
    """

    def __init__(self, ttl=STATUS_CACHE_TTL):
        self._ttl = ttl
        self._cache = {}  # key -> (timestamp, value)

    def get(self, key, check_fn):
        """Return cached result or call *check_fn* if stale/missing."""
        now = time.time()
        entry = self._cache.get(key)
        if entry and (now - entry[0]) < self._ttl:
            return entry[1]
        result = check_fn()
        self._cache[key] = (now, result)
        return result

    def invalidate(self, key=None):
        """Clear one key or the entire cache."""
        if key:
            self._cache.pop(key, None)
        else:
            self._cache.clear()


_status_cache = _StatusCache()


# ── Service Status ───────────────────────────────────────────
def _service_status_line():
    """Quick service status for banner display (cached, 10s TTL)."""
    rnsd_ok, _ = _status_cache.get("rnsd", check_rnsd_status)
    meshd_ok, _ = _status_cache.get("meshtasticd", check_meshtasticd_status)
    rnsd_tag = f"{C.GRN}●{C.RST}" if rnsd_ok else f"{C.DIM}○{C.RST}"
    meshd_tag = f"{C.GRN}●{C.RST}" if meshd_ok else f"{C.DIM}○{C.RST}"
    return f"rnsd {rnsd_tag}  meshtasticd {meshd_tag}"


# ── Cross-Platform Helpers ───────────────────────────────────
def _flush_input():
    """Discard stale keystrokes from terminal input buffer.

    Prevents phantom menu selections when the user types during
    a subprocess (MeshForge backend.py termios pattern).
    """
    try:
        import termios
        termios.tcflush(sys.stdin.fileno(), termios.TCIFLUSH)
    except (ImportError, OSError, ValueError):
        pass  # Windows, piped stdin, or not a TTY — safe to skip


def clear_screen():
    """Clear terminal without shell invocation."""
    if os.name == 'nt':
        subprocess.run(['cmd', '/c', 'cls'], shell=False, timeout=5)
    else:
        sys.stdout.write('\033[H\033[2J\033[3J')
        sys.stdout.flush()


def get_editor():
    """Detect a text editor available on this platform.

    Validates $EDITOR/$VISUAL with shutil.which() to prevent command
    injection via malicious environment variables (MeshForge pattern).
    """
    env_editor = os.environ.get('EDITOR') or os.environ.get('VISUAL')
    if env_editor and shutil.which(env_editor):
        return env_editor
    if os.name == 'nt':
        return 'notepad'
    for editor in ['nano', 'vim', 'vi']:
        if shutil.which(editor):
            return editor
    return 'vi'


def get_python():
    """Return the python executable path."""
    return sys.executable


def edit_file(path):
    """Open a file in the platform editor."""
    if not os.path.exists(path):
        print(f"\n  {C.RED}  File not found: {path}{C.RST}")
        time.sleep(2)
        return
    editor = get_editor()
    print(f"\n  {C.YLW}  Opening {os.path.basename(path)} with {editor}...{C.RST}")
    try:
        subprocess.run([editor, path], timeout=300)
    except FileNotFoundError:
        print(f"  {C.RED}  Editor '{editor}' not found. Set $EDITOR env var.{C.RST}")
        time.sleep(2)
    except subprocess.TimeoutExpired:
        print(f"  {C.YLW}  Editor session timed out.{C.RST}")
        time.sleep(1)


def launch_detached(cmd_list):
    """Launch a process detached from the current terminal (cross-platform).

    Returns True if the process started successfully, False otherwise.
    Uses MeshForge startup-verification pattern: sleep + poll to catch
    immediate crashes (e.g. missing modules, bad config).
    """
    try:
        if os.name == 'nt':
            # Windows: CREATE_NEW_CONSOLE flag
            CREATE_NEW_CONSOLE = 0x00000010
            proc = subprocess.Popen(cmd_list, creationflags=CREATE_NEW_CONSOLE)
        else:
            # POSIX: start_new_session detaches
            proc = subprocess.Popen(
                cmd_list,
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        # Verify process didn't crash immediately (MeshForge MF004 pattern)
        time.sleep(1)
        if proc.poll() is not None:
            print(f"  {C.RED}  Process exited immediately (code {proc.returncode}){C.RST}")
            log.warning("Detached process %s exited immediately (code %s)",
                        cmd_list, proc.returncode)
            time.sleep(2)
            return False
        return True
    except FileNotFoundError:
        print(f"  {C.RED}  Command not found: {cmd_list[0]}{C.RST}")
        log.warning("Command not found: %s", cmd_list[0])
        time.sleep(2)
        return False
    except OSError as e:
        print(f"  {C.RED}  Launch error: {e}{C.RST}")
        log.exception("Launch error for %s", cmd_list)
        time.sleep(2)
        return False


def run_tool(cmd_list, cwd=None):
    """Run a subprocess, wait for completion, then pause."""
    try:
        subprocess.run(cmd_list, cwd=cwd or BASE_DIR, timeout=180)
    except FileNotFoundError:
        print(f"\n  {C.RED}  Command not found: {cmd_list[0]}{C.RST}")
    except subprocess.TimeoutExpired:
        print(f"\n  {C.YLW}  Command timed out.{C.RST}")
    except OSError as e:
        print(f"\n  {C.RED}  Error: {e}{C.RST}")
    _status_cache.invalidate()
    _flush_input()
    input(f"\n  {C.DIM}Press Enter to continue...{C.RST}")


# ── Banner & Menu Rendering ──────────────────────────────────
def print_banner(cfg):
    clear_screen()
    w = min(cols() - 4, 62)  # cap box width
    port = cfg.get('gateway', {}).get('port', '???')
    dash = cfg.get('dashboard', {}).get('port', '???')
    name = cfg.get('gateway', {}).get('name', 'Supervisor NOC')

    print()
    print(box_top(w))
    print(box_row(
        center(f"{C.BOLD}{C.GRN}SUPERVISOR NOC{C.RST}  {C.DIM}Command Center v{VERSION}{C.RST}", w - 4),
        w,
    ))
    print(box_row(
        center(f"{C.DIM}Node: {name}{C.RST}", w - 4),
        w,
    ))
    print(box_mid(w))
    print(box_row(
        f"{C.CYN}Radio:{C.RST} {C.WHT}{port}{C.RST}    "
        f"{C.CYN}Dashboard:{C.RST} {C.WHT}:{dash}{C.RST}",
        w,
    ))
    print(box_row(
        center(_service_status_line(), w - 4),
        w,
    ))
    print(box_bot(w))
    print()


def print_menu():
    w = min(cols() - 4, 62)

    print(box_top(w))
    print(box_section("LAUNCHERS", w))
    print(box_row(f"  {C.GRN}1{C.RST}  Start Mesh Gateway", w))
    print(box_row(f"  {C.GRN}2{C.RST}  Start NomadNet", w))
    print(box_row(f"  {C.GRN}3{C.RST}  Open Web Deep-Dive", w))
    print(box_row(f"  {C.GRN}d{C.RST}  Terminal Dashboard", w))
    print(box_section("CONFIG", w))
    print(box_row(f"  {C.YLW}4{C.RST}  Edit Gateway Config  {C.DIM}(JSON){C.RST}", w))
    print(box_row(f"  {C.YLW}5{C.RST}  Edit Reticulum Config", w))
    print(box_row(f"  {C.YLW}6{C.RST}  Edit NomadNet Config", w))
    print(box_section("TOOLS", w))
    print(box_row(f"  {C.BLU}7{C.RST}  RNS Status", w))
    print(box_row(f"  {C.BLU}8{C.RST}  Fire Test Ping", w))
    print(box_row(f"  {C.BLU}9{C.RST}  Git Update  {C.DIM}(pull --ff-only){C.RST}", w))
    print(box_mid(w))
    print(box_row(f"  {C.RED}0{C.RST}  Exit", w))
    print(box_bot(w))


# ── Main Loop ────────────────────────────────────────────────
def main_menu():
    python = get_python()

    # One-shot environment check (MeshForge startup_checks pattern)
    from src.ui.preflight import startup_preflight
    startup_preflight()

    while True:
        try:
            cfg = load_config(fallback={
                "gateway": {"name": "Supervisor NOC", "port": "COM3"},
                "dashboard": {"port": 5000},
            })
            print_banner(cfg)
            print_menu()

            _flush_input()
            choice = input(f"\n  {C.CYN}Supervisor ▸{C.RST} ").strip().lower()

            if choice == '1':
                # Pre-launch conflict check (MeshForge conflict_resolver pattern)
                from src.ui.preflight import check_port_conflicts
                conflicts = check_port_conflicts(cfg)
                if conflicts:
                    print(f"\n  {C.YLW}{C.BOLD}  Port conflicts detected:{C.RST}")
                    for port, desc, detail in conflicts:
                        print(f"  {C.YLW}    :{port} — {desc}{C.RST}")
                        print(f"  {C.DIM}    {detail}{C.RST}")
                    _flush_input()
                    answer = input(f"\n  {C.CYN}  Launch anyway? [y/N]{C.RST} ").strip().lower()
                    if answer != 'y':
                        continue
                launcher = os.path.join(BASE_DIR, 'launcher.py')
                if launch_detached([python, launcher]):
                    _status_cache.invalidate()
                    print(f"  {C.GRN}  Gateway launched.{C.RST}")
                time.sleep(1)
            elif choice == '2':
                nomadnet = shutil.which('nomadnet')
                if nomadnet:
                    if launch_detached([nomadnet]):
                        _status_cache.invalidate()
                        print(f"  {C.GRN}  NomadNet launched.{C.RST}")
                else:
                    if launch_detached([python, '-m', 'nomadnet']):
                        _status_cache.invalidate()
                        print(f"  {C.GRN}  NomadNet launched (module mode).{C.RST}")
                time.sleep(1)
            elif choice == '3':
                dash_port = cfg.get('dashboard', {}).get('port', 5000)
                ok, err = validate_port(dash_port) if isinstance(dash_port, int) else (False, "not an integer")
                if ok:
                    try:
                        webbrowser.open(f"http://localhost:{dash_port}")
                    except OSError as e:
                        print(f"  {C.RED}  Could not open browser: {e}{C.RST}")
                        time.sleep(2)
                else:
                    print(f"  {C.RED}  Invalid dashboard port: {err}{C.RST}")
                    time.sleep(2)
            elif choice == 'd':
                dashboard = os.path.join(BASE_DIR, 'src', 'ui', 'dashboard.py')
                run_tool([python, dashboard])
            elif choice == '4':
                edit_file(CONFIG_PATH)
            elif choice == '5':
                edit_file(RNS_CONFIG_FILE)
            elif choice == '6':
                edit_file(NOMAD_CONFIG)
            elif choice == '7':
                run_tool([python, '-m', 'RNS.Utilities.rnstatus'])
            elif choice == '8':
                broadcast = os.path.join(BASE_DIR, 'scripts', 'broadcast.py')
                run_tool([python, broadcast])
            elif choice == '9':
                run_tool(['git', 'pull', '--ff-only'], cwd=BASE_DIR)
            elif choice == '0':
                print(f"\n  {C.DIM}Goodbye.{C.RST}\n")
                sys.exit(0)
            elif choice:
                print(f"\n  {C.YLW}  Unknown option: '{choice}'{C.RST}")
                time.sleep(1)
        except KeyboardInterrupt:
            print(f"\n  {C.DIM}Goodbye.{C.RST}\n")
            sys.exit(0)
        except FileNotFoundError as e:
            log.exception("File not found")
            print(f"\n  {C.RED}  File not found: {e}{C.RST}")
            time.sleep(2)
        except PermissionError as e:
            log.exception("Permission denied")
            print(f"\n  {C.RED}  Permission denied: {e}{C.RST}")
            print(f"  {C.DIM}  Try running with sudo if this is a system file.{C.RST}")
            time.sleep(2)
        except subprocess.TimeoutExpired:
            log.exception("Operation timed out")
            print(f"\n  {C.YLW}  Operation timed out.{C.RST}")
            time.sleep(2)
        except Exception as e:
            log.exception("Unexpected error in menu")
            print(f"\n  {C.RED}  Error: {e}{C.RST}")
            print(f"  {C.DIM}  (details logged to ~/.config/rns-gateway/logs/){C.RST}")
            time.sleep(2)


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Supervisor NOC — Command Center for RNS-Meshtastic Gateway",
    )
    parser.add_argument(
        "--version", action="version",
        version=f"%(prog)s {VERSION}",
    )
    parser.add_argument(
        "--debug", action="store_true",
        help="Enable debug-level logging",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    install_crash_handler()
    args = _parse_args()
    # TUI mode: suppress console logging to prevent whiptail/curses corruption
    # (MeshForge industrial-strength TUI pattern — commit 259f22ee)
    log_level = logging.DEBUG if args.debug else logging.INFO
    setup_logging(
        level=log_level,
        log_file=default_log_path(),
        console_level=logging.WARNING,
    )
    main_menu()
