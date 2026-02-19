"""
Centralized paths, config loading, and project constants.
Single source of truth -- all modules import from here.
"""
import json
import os

# ── Canonical Paths ──────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CONFIG_PATH = os.path.join(BASE_DIR, 'config.json')
RNS_CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".reticulum")
RNS_CONFIG_FILE = os.path.join(RNS_CONFIG_DIR, "config")
NOMAD_CONFIG = os.path.join(os.path.expanduser("~"), ".nomadnet", "config")


_UNSET = object()


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
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, PermissionError):
        return fallback
