"""
Environment and dependency checking utilities.
Used by both terminal and web dashboards.

Includes TCP/serial pre-flight probes adopted from MeshForge's
service_check.py and startup_checks.py patterns.
"""
import os
import socket


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


def check_meshtasticd_status():
    """Check if meshtasticd service is running.

    Tries systemctl first (SSOT for systemd), then falls back to pgrep.
    Returns (running: bool, detail: str).
    """
    import subprocess

    # Prefer systemctl (single source of truth for systemd services)
    try:
        result = subprocess.run(
            ['systemctl', 'is-active', 'meshtasticd'],
            capture_output=True, text=True, timeout=5,
        )
        state = result.stdout.strip()
        if state == 'active':
            # Verify port is actually listening (catches zombies)
            port_ok, _ = check_tcp_port(4403)
            if port_ok:
                return True, "active (systemd) [port 4403 listening]"
            return True, "active (systemd) [WARNING: port 4403 not listening]"
        return False, f"{state} (systemd)"
    except FileNotFoundError:
        pass  # systemctl not available, fall through
    except subprocess.TimeoutExpired:
        return False, "check timed out"

    # Fallback: pgrep
    try:
        result = subprocess.run(
            ['pgrep', '-x', 'meshtasticd'],
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
    """Check if RNS UDP port is in use.

    On Linux, uses passive /proc/net/udp scanning to avoid TOCTOU race
    conditions and service disruption on resource-constrained hardware
    (adopted from MeshForge PR #920-922).  Falls back to socket probe
    on other platforms.
    """
    # Linux: passive scan — no socket contention
    if os.path.isfile('/proc/net/udp'):
        hex_port = f'{port:04X}'
        try:
            with open('/proc/net/udp', 'r') as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) >= 2 and ':' in parts[1]:
                        local_port = parts[1].split(':')[1]
                        if local_port == hex_port:
                            return True, f"UDP :{port} in use (passive scan)"
            return False, f"UDP :{port} not in use"
        except (OSError, PermissionError):
            pass  # fall through to socket probe

    # Fallback: socket probe (non-Linux or /proc unavailable)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind(('127.0.0.1', port))
        return False, f"UDP :{port} not in use"
    except OSError:
        return True, f"UDP :{port} in use"
    finally:
        sock.close()


# ── Pre-flight probes (MeshForge patterns) ──────────────────
def check_tcp_port(port, host="127.0.0.1", timeout=2):
    """Check if a TCP port is accepting connections.

    Returns (listening: bool, detail: str).
    Catches zombie processes where systemctl says 'active' but the
    port is not actually bound.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            result = sock.connect_ex((host, port))
            if result == 0:
                return True, "TCP :%d listening" % port
            return False, "TCP :%d not listening" % port
    except OSError as e:
        return False, "TCP :%d check failed: %s" % (port, e)


def check_serial_device(path):
    """Verify a serial device exists and is accessible.

    Returns (ok: bool, detail: str).
    """
    if not os.path.exists(path):
        return False, "device not found: %s" % path
    if not os.access(path, os.R_OK | os.W_OK):
        return False, "device not readable/writable: %s (check permissions)" % path
    return True, "device OK: %s" % path


def check_serial_ports_detailed():
    """List serial ports with vendor/model info.

    Returns list of dicts with keys: device, description, vendor, model.
    Falls back to basic list if pyserial doesn't expose detailed info.
    """
    try:
        from serial.tools.list_ports import comports
        result = []
        for p in comports():
            result.append({
                "device": p.device,
                "description": getattr(p, "description", ""),
                "vendor": getattr(p, "manufacturer", ""),
                "model": getattr(p, "product", ""),
            })
        return result if result else []
    except ImportError:
        return []
