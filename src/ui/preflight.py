"""
One-shot startup environment checks for the Supervisor NOC menu.

Prints warnings for common issues so users don't discover them the hard
way after trying to launch a service.  Adopted from MeshForge's
startup_checks.py pattern — simplified for the gateway tool's scope.
"""
import logging
import os

from src.ui.widgets import C
from src.utils.common import CONFIG_PATH, load_config, validate_config
from src.utils.common import RNS_CONFIG_DIR
from src.utils.service_check import (
    check_meshtastic_lib,
    check_rns_config,
    check_rns_lib,
    check_rns_udp_port,
    check_serial_ports,
    check_tcp_port,
)

log = logging.getLogger("preflight")


def startup_preflight():
    """Run one-shot environment checks and print warnings.

    Called once at menu launch.  Returns a list of warning strings
    (empty list = all clear).  Also prints them to stdout with colour.
    """
    warnings = []

    # 0. First-run detection (MeshForge startup_checks pattern)
    rns_found_early, _ = check_rns_config()
    if not os.path.isfile(CONFIG_PATH) and not rns_found_early:
        print()
        print(f"  {C.CYN}{C.BOLD}  Welcome to Supervisor NOC!{C.RST}")
        print(f"  {C.DIM}  This appears to be your first run. Quick setup:{C.RST}")
        print(f"  {C.DIM}  1. Copy config.json.example -> config.json and edit it{C.RST}")
        print(f"  {C.DIM}  2. Run 'rnsd' once to generate Reticulum config{C.RST}")
        print(f"  {C.DIM}  3. Connect your Meshtastic radio via USB{C.RST}")
        print()

    # 1. Config file exists and parses?
    if not os.path.isfile(CONFIG_PATH):
        warnings.append(f"config.json not found at {CONFIG_PATH}")
        cfg = None
    else:
        cfg = load_config(fallback=None)
        if cfg is None:
            warnings.append("config.json exists but could not be parsed")
        else:
            errors = validate_config(cfg)
            for e in errors:
                warnings.append(f"Config: {e}")

    # 2. Required libraries
    rns_ok, _ = check_rns_lib()
    if not rns_ok:
        warnings.append("Reticulum (RNS) library not installed — pip install rns")

    mesh_ok, _ = check_meshtastic_lib()
    if not mesh_ok:
        warnings.append("Meshtastic library not installed — pip install meshtastic")

    # 3. Serial device present? (only when config says serial mode)
    if cfg:
        gw = cfg.get("gateway", {})
        if gw.get("connection_type", "serial") == "serial":
            ports = check_serial_ports()
            if not ports or ports == ["(none detected)"] or ports == ["(pyserial not installed)"]:
                warnings.append("No serial devices detected — is a radio connected?")

    # 4. RNS config exists?
    rns_found, _ = check_rns_config()
    if not rns_found:
        warnings.append("No Reticulum config found — run 'rnsd' once to generate it")

    # 5. RNS storage directory writable? (MeshForge _heal_rns_storage_dirs pattern)
    if rns_found:
        storage_dir = os.path.join(RNS_CONFIG_DIR, "storage")
        if os.path.isdir(storage_dir) and not os.access(storage_dir, os.W_OK):
            warnings.append(
                f"RNS storage dir not writable: {storage_dir} — "
                f"fix with: sudo chown -R $USER {RNS_CONFIG_DIR}"
            )
        elif os.path.isdir(RNS_CONFIG_DIR) and not os.path.isdir(storage_dir):
            warnings.append(
                f"RNS storage dir missing: {storage_dir} — "
                "run 'rnsd' once to initialize it"
            )

    # Print warnings
    if warnings:
        print()
        for w in warnings:
            print(f"  {C.YLW}  * {w}{C.RST}")
        print()
    else:
        log.debug("Preflight checks passed — no warnings")

    return warnings


def check_port_conflicts(cfg):
    """Check for port conflicts before launching the gateway.

    Returns a list of ``(port, description, detail)`` tuples for each
    conflict found.  An empty list means all clear.
    """
    if not cfg:
        return []

    conflicts = []
    gw = cfg.get("gateway", {})

    # UDP 37428 — RNS shared-instance port
    udp_in_use, udp_detail = check_rns_udp_port(37428)
    if udp_in_use:
        conflicts.append((37428, "RNS shared-instance UDP port already bound", udp_detail))

    # meshtasticd TCP port (only in TCP mode)
    if gw.get("connection_type") == "tcp":
        tcp_port = gw.get("tcp_port", 4403)
        tcp_ok, tcp_detail = check_tcp_port(tcp_port)
        if not tcp_ok:
            conflicts.append((tcp_port, "meshtasticd TCP not reachable", tcp_detail))

    # Dashboard port
    dash_port = cfg.get("dashboard", {}).get("port", 5000)
    if isinstance(dash_port, int):
        dash_listening, dash_detail = check_tcp_port(dash_port)
        if dash_listening:
            conflicts.append((dash_port, "Dashboard port already in use", dash_detail))

    return conflicts
