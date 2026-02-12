"""
Terminal Dashboard for Supervisor NOC.

Displays a snapshot of gateway status, system info, and config
directly in the terminal.  No external dependencies (no Flask, no curses).
Invoked from the Command Center menu (option 'd').
"""
import json
import os
import platform
import shutil
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_PATH = os.path.join(BASE_DIR, 'config.json')
RNS_CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".reticulum")


# ── ANSI helpers ─────────────────────────────────────────────
class C:
    RST  = '\033[0m'
    BOLD = '\033[1m'
    DIM  = '\033[2m'
    RED  = '\033[91m'
    GRN  = '\033[92m'
    YLW  = '\033[93m'
    BLU  = '\033[94m'
    CYN  = '\033[96m'
    WHT  = '\033[97m'

BOX_H  = '─'
BOX_V  = '│'
BOX_TL = '┌'
BOX_TR = '┐'
BOX_BL = '└'
BOX_BR = '┘'
BOX_LT = '├'
BOX_RT = '┤'


def _cols():
    return shutil.get_terminal_size((80, 24)).columns


def _strip_ansi(text):
    import re
    return re.sub(r'\033\[[0-9;]*m', '', text)


def box_top(w):
    return f"  {C.DIM}{BOX_TL}{BOX_H * (w - 2)}{BOX_TR}{C.RST}"

def box_mid(w):
    return f"  {C.DIM}{BOX_LT}{BOX_H * (w - 2)}{BOX_RT}{C.RST}"

def box_bot(w):
    return f"  {C.DIM}{BOX_BL}{BOX_H * (w - 2)}{BOX_BR}{C.RST}"

def box_row(content, w):
    visible = len(_strip_ansi(content))
    inner = w - 4
    pad = max(0, inner - visible)
    return f"  {C.DIM}{BOX_V}{C.RST} {content}{' ' * pad} {C.DIM}{BOX_V}{C.RST}"

def box_section(label, w):
    inner = w - 4
    lbl = f" {label} "
    bar_len = max(0, inner - len(lbl))
    left = bar_len // 2
    right = bar_len - left
    return f"  {C.DIM}{BOX_LT}{BOX_H * left}{C.RST}{C.BOLD}{C.CYN}{lbl}{C.RST}{C.DIM}{BOX_H * right}{BOX_RT}{C.RST}"

def box_kv(key, value, w, key_color=C.CYN, val_color=C.WHT):
    """Key-value row inside a box."""
    return box_row(f"{key_color}{key}:{C.RST}  {val_color}{value}{C.RST}", w)


# ── Data Collection ──────────────────────────────────────────
def load_config():
    try:
        with open(CONFIG_PATH, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, PermissionError):
        return None


def check_rns_config():
    """Check if Reticulum config directory exists and has a config file."""
    config_file = os.path.join(RNS_CONFIG_DIR, "config")
    if os.path.isfile(config_file):
        size = os.path.getsize(config_file)
        return True, f"{size} bytes"
    return False, "not found"


def check_serial_ports():
    """List serial ports if pyserial is available."""
    try:
        from serial.tools.list_ports import comports
        ports = [p.device for p in comports()]
        return ports if ports else ["(none detected)"]
    except ImportError:
        return ["(pyserial not installed)"]


def check_meshtastic_lib():
    """Check whether meshtastic python lib is importable."""
    try:
        import meshtastic
        return True, getattr(meshtastic, '__version__', 'unknown')
    except ImportError:
        return False, "not installed"


def check_rns_lib():
    """Check whether RNS is importable."""
    try:
        import RNS
        return True, getattr(RNS, '__version__', 'unknown')
    except ImportError:
        return False, "not installed"


# ── Render ───────────────────────────────────────────────────
def render_dashboard():
    sys.stdout.write('\033[2J\033[H')
    sys.stdout.flush()

    w = min(_cols() - 4, 66)
    cfg = load_config()

    # Title
    print()
    print(box_top(w))
    title = f"{C.BOLD}{C.GRN}SUPERVISOR NOC{C.RST}  {C.DIM}Terminal Dashboard{C.RST}"
    visible_title = len(_strip_ansi(title))
    inner = w - 4
    lpad = (inner - visible_title) // 2
    rpad = inner - visible_title - lpad
    print(f"  {C.DIM}{BOX_V}{C.RST} {' ' * lpad}{title}{' ' * rpad} {C.DIM}{BOX_V}{C.RST}")
    print(box_bot(w))
    print()

    # ── System Panel ──
    print(box_top(w))
    print(box_section("SYSTEM", w))
    print(box_kv("Platform", f"{platform.system()} {platform.release()}", w))
    print(box_kv("Python", f"{platform.python_version()} ({sys.executable})", w))
    print(box_kv("Hostname", platform.node(), w))
    print(box_bot(w))
    print()

    # ── Libraries Panel ──
    rns_ok, rns_ver = check_rns_lib()
    mesh_ok, mesh_ver = check_meshtastic_lib()
    print(box_top(w))
    print(box_section("LIBRARIES", w))

    rns_status = f"{C.GRN}OK{C.RST}  v{rns_ver}" if rns_ok else f"{C.RED}MISSING{C.RST}"
    mesh_status = f"{C.GRN}OK{C.RST}  v{mesh_ver}" if mesh_ok else f"{C.RED}MISSING{C.RST}"
    print(box_kv("Reticulum", rns_status, w))
    print(box_kv("Meshtastic", mesh_status, w))

    # Serial ports
    ports = check_serial_ports()
    print(box_kv("Serial Ports", ", ".join(ports), w))
    print(box_bot(w))
    print()

    # ── RNS Config Panel ──
    rns_found, rns_info = check_rns_config()
    print(box_top(w))
    print(box_section("RETICULUM", w))
    if rns_found:
        print(box_kv("Config", f"{C.GRN}found{C.RST}  ({rns_info})", w))
    else:
        print(box_kv("Config", f"{C.RED}not found{C.RST}  (run RNS once to create)", w))
    print(box_kv("Config Dir", RNS_CONFIG_DIR, w))
    print(box_bot(w))
    print()

    # ── Gateway Config Panel ──
    print(box_top(w))
    print(box_section("GATEWAY CONFIG", w))
    if cfg:
        gw = cfg.get('gateway', {})
        dash = cfg.get('dashboard', {})
        print(box_kv("Node Name", gw.get('name', '(unset)'), w))
        print(box_kv("Radio Port", gw.get('port', '(unset)'), w))
        print(box_kv("Bitrate", f"{gw.get('bitrate', '?')} bps", w))
        print(box_kv("Dash Host", f"{dash.get('host', '?')}:{dash.get('port', '?')}", w))
        features = cfg.get('features', {})
        if features:
            print(box_mid(w))
            print(box_row(f"{C.DIM}Features:{C.RST}", w))
            for k, v in features.items():
                tag = f"{C.GRN}ON{C.RST}" if v else f"{C.RED}OFF{C.RST}"
                print(box_row(f"  {k}: {tag}", w))
    else:
        print(box_row(f"{C.YLW}config.json not found or invalid{C.RST}", w))
        print(box_row(f"{C.DIM}Expected at: {CONFIG_PATH}{C.RST}", w))
    print(box_bot(w))
    print()


# ── Entry Point ──────────────────────────────────────────────
def main():
    render_dashboard()
    # No auto-loop; single snapshot, then return to menu


if __name__ == '__main__':
    main()
