"""
Terminal Dashboard for Supervisor NOC.

Displays a snapshot of gateway status, system info, and config
directly in the terminal.  No external dependencies (no Flask, no curses).
Invoked from the Command Center menu (option 'd').
"""
import os
import platform
import shutil
import sys

# Ensure project root is on path
_BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _BASE not in sys.path:
    sys.path.insert(0, _BASE)

from src.ui.widgets import (
    C, BOX_V, cols, strip_ansi,
    box_top, box_mid, box_bot, box_row, box_section, box_kv,
)
from src.utils.common import CONFIG_PATH, RNS_CONFIG_DIR, load_config
from src.utils.service_check import (
    check_rns_lib, check_meshtastic_lib, check_serial_ports, check_rns_config,
    check_rnsd_status, check_meshtasticd_status, check_rns_udp_port,
)


# ── System Resource Helpers (stdlib only, MeshForge pattern) ──
def _get_uptime():
    """Return system uptime string, or None if unavailable."""
    try:
        if os.path.isfile('/proc/uptime'):
            with open('/proc/uptime') as f:
                secs = int(float(f.read().split()[0]))
            days, rem = divmod(secs, 86400)
            hours, rem = divmod(rem, 3600)
            mins = rem // 60
            parts = []
            if days:
                parts.append(f"{days}d")
            if hours:
                parts.append(f"{hours}h")
            parts.append(f"{mins}m")
            return " ".join(parts)
    except (OSError, ValueError):
        pass
    return None


def _get_memory():
    """Return (used_mb, total_mb) from /proc/meminfo, or None."""
    try:
        if os.path.isfile('/proc/meminfo'):
            info = {}
            with open('/proc/meminfo') as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2:
                        info[parts[0].rstrip(':')] = int(parts[1])
            total = info.get('MemTotal', 0)
            avail = info.get('MemAvailable', 0)
            if total > 0:
                used_mb = (total - avail) / 1024
                total_mb = total / 1024
                return (used_mb, total_mb)
    except (OSError, ValueError, KeyError):
        pass
    return None


def _get_disk():
    """Return (used_gb, total_gb) for root filesystem."""
    try:
        usage = shutil.disk_usage("/")
        used_gb = (usage.total - usage.free) / (1024 ** 3)
        total_gb = usage.total / (1024 ** 3)
        return (used_gb, total_gb)
    except OSError:
        return None


# ── Render ───────────────────────────────────────────────────
def render_dashboard():
    sys.stdout.write('\033[H\033[2J\033[3J')
    sys.stdout.flush()

    w = min(cols() - 4, 66)
    cfg = load_config(fallback=None)

    # Title
    print()
    print(box_top(w))
    title = f"{C.BOLD}{C.GRN}SUPERVISOR NOC{C.RST}  {C.DIM}Terminal Dashboard{C.RST}"
    visible_title = len(strip_ansi(title))
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

    uptime = _get_uptime()
    if uptime:
        print(box_kv("Uptime", uptime, w))

    mem = _get_memory()
    if mem:
        used_mb, total_mb = mem
        pct = (used_mb / total_mb * 100) if total_mb else 0
        color = C.GRN if pct < 70 else (C.YLW if pct < 90 else C.RED)
        print(box_kv("Memory", f"{color}{used_mb:.0f}{C.RST}/{total_mb:.0f} MB ({pct:.0f}%)", w))

    disk = _get_disk()
    if disk:
        used_gb, total_gb = disk
        pct = (used_gb / total_gb * 100) if total_gb else 0
        color = C.GRN if pct < 80 else (C.YLW if pct < 95 else C.RED)
        print(box_kv("Disk", f"{color}{used_gb:.1f}{C.RST}/{total_gb:.1f} GB ({pct:.0f}%)", w))

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

    # ── Services Panel ──
    rnsd_ok, rnsd_info = check_rnsd_status()
    meshd_ok, meshd_info = check_meshtasticd_status()
    udp_ok, udp_info = check_rns_udp_port()
    print(box_top(w))
    print(box_section("SERVICES", w))
    rnsd_status = f"{C.GRN}RUNNING{C.RST}  {rnsd_info}" if rnsd_ok else f"{C.YLW}STOPPED{C.RST}  {rnsd_info}"
    print(box_kv("rnsd", rnsd_status, w))
    meshd_status = f"{C.GRN}RUNNING{C.RST}  {meshd_info}" if meshd_ok else f"{C.YLW}STOPPED{C.RST}  {meshd_info}"
    print(box_kv("meshtasticd", meshd_status, w))
    udp_tag = f"{C.GRN}{udp_info}{C.RST}" if udp_ok else f"{C.YLW}{udp_info}{C.RST}"
    print(box_kv("UDP 37428", udp_tag, w))
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
        conn_type = gw.get('connection_type', 'serial')
        print(box_kv("Node Name", gw.get('name', '(unset)'), w))
        bridge_mode = gw.get('bridge_mode', 'direct')
        print(box_kv("Bridge Mode", bridge_mode, w))
        print(box_kv("Connection", conn_type, w))
        if bridge_mode == "mqtt":
            mqtt_host = gw.get('mqtt_host', 'localhost')
            mqtt_port = gw.get('mqtt_port', 1883)
            print(box_kv("MQTT Broker", f"{mqtt_host}:{mqtt_port}", w))
            print(box_kv("HTTP API", f":{gw.get('http_api_port', 9443)}", w))
        elif conn_type == "tcp":
            print(box_kv("TCP Host", f"{gw.get('host', 'localhost')}:{gw.get('tcp_port', 4403)}", w))
        else:
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

    # ── Node Tracker Panel (Session 4) ──
    try:
        from src.utils.node_tracker import NodeTracker
        tracker = NodeTracker()
        nodes = tracker.get_all_nodes()
        print(box_top(w))
        print(box_section("KNOWN NODES", w))
        print(box_kv("Total Nodes", str(len(nodes)), w))
        if nodes:
            import time as _time
            print(box_mid(w))
            for node in nodes[:5]:
                name = node.get("node_name") or node.get("node_id", "?")
                ago = _time.time() - node.get("last_seen", 0)
                if ago < 60:
                    seen = f"{ago:.0f}s ago"
                elif ago < 3600:
                    seen = f"{ago / 60:.0f}m ago"
                else:
                    seen = f"{ago / 3600:.1f}h ago"
                snr = f"{node['snr']:.1f}dB" if node.get("snr") is not None else "-"
                print(box_kv(name[:20], f"seen {seen}  SNR {snr}", w))
        print(box_bot(w))
        print()
    except Exception:  # noqa: S110
        pass  # Node tracker not available in standalone mode


# ── Entry Point ──────────────────────────────────────────────
def main():
    render_dashboard()
    # No auto-loop; single snapshot, then return to menu


if __name__ == '__main__':
    main()
