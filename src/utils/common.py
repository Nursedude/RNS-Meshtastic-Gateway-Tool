"""
Centralized paths, config loading, and project constants.
Single source of truth -- all modules import from here.
"""
import json
import logging
import os

log = logging.getLogger("config")

# ── Canonical Paths ──────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CONFIG_PATH = os.path.join(BASE_DIR, 'config.json')
RNS_CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".reticulum")
RNS_CONFIG_FILE = os.path.join(RNS_CONFIG_DIR, "config")
NOMAD_CONFIG = os.path.join(os.path.expanduser("~"), ".nomadnet", "config")


_UNSET = object()

_VALID_CONNECTION_TYPES = ("serial", "tcp")


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
            if val is not None and (not isinstance(val, int) or val < 1 or val > 65535):
                warnings.append(f"gateway.{port_key} must be an integer 1-65535, got {val!r}")

        bitrate = gw.get("bitrate")
        if bitrate is not None and (not isinstance(bitrate, (int, float)) or bitrate <= 0):
            warnings.append(f"gateway.bitrate must be a positive number, got {bitrate!r}")

    dash = cfg.get("dashboard", {})
    if isinstance(dash, dict):
        port = dash.get("port")
        if port is not None and (not isinstance(port, int) or port < 1 or port > 65535):
            warnings.append(f"dashboard.port must be an integer 1-65535, got {port!r}")

    return warnings


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

    for warning in validate_config(cfg):
        log.warning(warning)
    return cfg
