"""
Centralized paths, config loading, and project constants.
Single source of truth -- all modules import from here.
"""
import json
import logging
import os
import re
import stat

log = logging.getLogger("config")


def get_real_user_home():
    """Return the real user's home directory, even under sudo.

    When running with ``sudo``, ``os.path.expanduser("~")`` returns
    ``/root`` instead of the invoking user's home.  This function checks
    the ``SUDO_USER`` environment variable and resolves the correct path.
    Adopted from MeshForge ``utils/paths.py:get_real_user_home()``.
    """
    sudo_user = os.environ.get("SUDO_USER")
    if sudo_user:
        try:
            import pwd
            return pwd.getpwnam(sudo_user).pw_dir
        except (KeyError, ImportError):
            pass
    return os.path.expanduser("~")


# ── Canonical Paths ──────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CONFIG_PATH = os.path.join(BASE_DIR, 'config.json')
_HOME = get_real_user_home()
RNS_CONFIG_DIR = os.path.join(_HOME, ".reticulum")
RNS_CONFIG_FILE = os.path.join(RNS_CONFIG_DIR, "config")
NOMAD_CONFIG = os.path.join(_HOME, ".nomadnet", "config")


_UNSET = object()

_VALID_CONNECTION_TYPES = ("serial", "tcp")

_HOSTNAME_RE = re.compile(r'^[a-zA-Z0-9._:\-]+$')


def validate_hostname(host):
    """Validate a hostname/IP string (MeshForge pattern).

    Rejects flag-injection attempts (leading '-'), overly long values,
    and characters outside the safe set.

    Returns:
        (ok: bool, error_message: str)
    """
    if not host or not isinstance(host, str):
        return False, "hostname must be a non-empty string"
    if host.startswith('-'):
        return False, "hostname must not start with '-' (flag injection)"
    if len(host) > 253:
        return False, "hostname exceeds 253 characters"
    if not _HOSTNAME_RE.match(host):
        return False, f"hostname contains invalid characters: {host!r}"
    return True, ""


def validate_port(port):
    """Validate a network port number.

    Returns:
        (ok: bool, error_message: str)
    """
    if not isinstance(port, int) or isinstance(port, bool):
        return False, f"port must be an integer, got {type(port).__name__}"
    if port < 1 or port > 65535:
        return False, f"port must be 1-65535, got {port}"
    return True, ""


def check_config_permissions(path):
    """Warn if config file has overly permissive modes (Linux/POSIX only).

    Returns a list of warning strings (empty when permissions are fine).
    """
    warnings = []
    if os.name != 'posix':
        return warnings
    try:
        mode = os.stat(path).st_mode
        if mode & stat.S_IROTH:
            warnings.append(
                f"{path} is world-readable (mode {oct(mode)}). "
                "Consider: chmod 600 " + path
            )
        if mode & stat.S_IWOTH:
            warnings.append(
                f"{path} is world-writable (mode {oct(mode)}). "
                "Consider: chmod 600 " + path
            )
    except OSError:
        pass
    return warnings


def validate_config(cfg):
    """Validate gateway config structure and return a list of warnings.

    Returns an empty list when the config is valid.
    """
    warnings = []
    if not isinstance(cfg, dict):
        return ["Config is not a JSON object"]

    gw = cfg.get("gateway", {})
    if not isinstance(gw, dict):
        warnings.append("gateway section must be a JSON object")
    else:
        conn = gw.get("connection_type")
        if conn is not None and conn not in _VALID_CONNECTION_TYPES:
            warnings.append(f"gateway.connection_type must be one of {_VALID_CONNECTION_TYPES}, got '{conn}'")

        for port_key in ("tcp_port",):
            val = gw.get(port_key)
            if val is not None:
                ok, err = validate_port(val) if isinstance(val, int) and not isinstance(val, bool) else (False, f"must be an integer, got {type(val).__name__}")
                if not ok:
                    warnings.append(f"gateway.{port_key}: {err}")

        host = gw.get("host")
        if host is not None:
            ok, err = validate_hostname(host)
            if not ok:
                warnings.append(f"gateway.host: {err}")

        bitrate = gw.get("bitrate")
        if bitrate is not None and (not isinstance(bitrate, (int, float)) or bitrate <= 0):
            warnings.append(f"gateway.bitrate must be a positive number, got {bitrate!r}")

    dash = cfg.get("dashboard", {})
    if isinstance(dash, dict):
        port = dash.get("port")
        if port is not None:
            ok, err = validate_port(port) if isinstance(port, int) and not isinstance(port, bool) else (False, f"must be an integer, got {type(port).__name__}")
            if not ok:
                warnings.append(f"dashboard.port: {err}")
        dash_host = dash.get("host")
        if dash_host is not None:
            ok, err = validate_hostname(dash_host)
            if not ok:
                warnings.append(f"dashboard.host: {err}")

    return warnings


def validate_message_length(data, max_bytes=228):
    """Validate that a message payload fits within the Meshtastic frame limit.

    Args:
        data: The bytes payload to check.
        max_bytes: Maximum allowed length (default: 228, Meshtastic LoRa limit).

    Returns:
        (ok: bool, message: str)
    """
    if not isinstance(data, (bytes, bytearray)):
        return False, f"data must be bytes, got {type(data).__name__}"
    length = len(data)
    if length > max_bytes:
        return False, f"payload {length} bytes exceeds {max_bytes} byte limit"
    return True, f"payload {length} bytes OK"


def load_config(fallback=_UNSET):
    """Load gateway config.json, returning *fallback* on failure.

    Args:
        fallback: Value to return if config cannot be loaded.
                  Defaults to empty dict {} when not specified.
    """
    if fallback is _UNSET:
        fallback = {}
    try:
        with open(CONFIG_PATH, 'r') as f:
            cfg = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, PermissionError):
        return fallback

    for warning in check_config_permissions(CONFIG_PATH):
        log.warning(warning)
    for warning in validate_config(cfg):
        log.warning(warning)
    return cfg
