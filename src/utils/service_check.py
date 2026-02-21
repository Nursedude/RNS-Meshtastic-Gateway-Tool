"""
Environment and dependency checking utilities.
Used by both terminal and web dashboards.
"""
import os


def check_rns_lib():
    """Check whether RNS is importable. Returns (ok: bool, version: str)."""
    try:
        import RNS
        return True, getattr(RNS, '__version__', 'unknown')
    except ImportError:
        return False, "not installed"


def check_meshtastic_lib():
    """Check whether meshtastic lib is importable. Returns (ok: bool, version: str)."""
    try:
        import meshtastic
        return True, getattr(meshtastic, '__version__', 'unknown')
    except ImportError:
        return False, "not installed"


def check_serial_ports():
    """List serial ports if pyserial is available. Returns list of strings."""
    try:
        from serial.tools.list_ports import comports
        ports = [p.device for p in comports()]
        return ports if ports else ["(none detected)"]
    except ImportError:
        return ["(pyserial not installed)"]


def check_rns_config():
    """Check if Reticulum config directory exists and has a config file."""
    from src.utils.common import RNS_CONFIG_FILE
    if os.path.isfile(RNS_CONFIG_FILE):
        size = os.path.getsize(RNS_CONFIG_FILE)
        return True, f"{size} bytes"
    return False, "not found"


def check_rnsd_status():
    """Check if rnsd process is running. Returns (running: bool, detail: str)."""
    import subprocess
    try:
        result = subprocess.run(
            ['pgrep', '-x', 'rnsd'],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            pids = result.stdout.strip().split('\n')
            return True, f"PID(s): {', '.join(pids)}"
        return False, "not running"
    except FileNotFoundError:
        return False, "cannot check (pgrep unavailable)"
    except subprocess.TimeoutExpired:
        return False, "check timed out"


def check_rns_udp_port(port=37428):
    """Check if RNS UDP port is in use."""
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind(('127.0.0.1', port))
        return False, f"UDP :{port} not in use"
    except OSError:
        return True, f"UDP :{port} in use"
    finally:
        sock.close()
