import os
import sys
import shutil
import subprocess
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
from src.utils.common import CONFIG_PATH, NOMAD_CONFIG, RNS_CONFIG_FILE, load_config


# ── Cross-Platform Helpers ───────────────────────────────────
def clear_screen():
    """Clear terminal without os.system shell invocation."""
    if os.name == 'nt':
        os.system('cls')
    else:
        sys.stdout.write('\033[2J\033[H')
        sys.stdout.flush()


def get_editor():
    """Detect a text editor available on this platform."""
    env_editor = os.environ.get('EDITOR') or os.environ.get('VISUAL')
    if env_editor:
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
    """Launch a process detached from the current terminal (cross-platform)."""
    try:
        if os.name == 'nt':
            # Windows: CREATE_NEW_CONSOLE flag
            CREATE_NEW_CONSOLE = 0x00000010
            subprocess.Popen(cmd_list, creationflags=CREATE_NEW_CONSOLE)
        else:
            # POSIX: start_new_session detaches
            subprocess.Popen(
                cmd_list,
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    except FileNotFoundError:
        print(f"  {C.RED}  Command not found: {cmd_list[0]}{C.RST}")
        time.sleep(2)
    except OSError as e:
        print(f"  {C.RED}  Launch error: {e}{C.RST}")
        time.sleep(2)


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
    while True:
        cfg = load_config(fallback={
            "gateway": {"name": "Supervisor NOC", "port": "COM3"},
            "dashboard": {"port": 5000},
        })
        print_banner(cfg)
        print_menu()

        choice = input(f"\n  {C.CYN}Supervisor ▸{C.RST} ").strip().lower()

        if choice == '1':
            launcher = os.path.join(BASE_DIR, 'launcher.py')
            launch_detached([python, launcher])
            print(f"  {C.GRN}  Gateway launched.{C.RST}")
            time.sleep(1)
        elif choice == '2':
            nomadnet = shutil.which('nomadnet')
            if nomadnet:
                launch_detached([nomadnet])
                print(f"  {C.GRN}  NomadNet launched.{C.RST}")
            else:
                launch_detached([python, '-m', 'nomadnet'])
                print(f"  {C.GRN}  NomadNet launched (module mode).{C.RST}")
            time.sleep(1)
        elif choice == '3':
            dash_port = cfg.get('dashboard', {}).get('port', 5000)
            webbrowser.open(f"http://localhost:{dash_port}")
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
            broadcast = os.path.join(BASE_DIR, 'tests', 'broadcast.py')
            run_tool([python, broadcast])
        elif choice == '9':
            run_tool(['git', 'pull', '--ff-only'], cwd=BASE_DIR)
        elif choice == '0':
            print(f"\n  {C.DIM}Goodbye.{C.RST}\n")
            sys.exit(0)
        elif choice:
            print(f"\n  {C.YLW}  Unknown option: '{choice}'{C.RST}")
            time.sleep(1)


if __name__ == "__main__":
    main_menu()
