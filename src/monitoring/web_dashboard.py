import logging
import os
import platform
import sys
import threading
import time
from collections import defaultdict, deque
from functools import wraps

from flask import Flask, jsonify, render_template, request

# Ensure project root is on path
_BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _BASE not in sys.path:
    sys.path.insert(0, _BASE)

from version import __version__
from src.utils.common import load_config, validate_hostname, validate_port
from src.utils.log import setup_logging
from src.utils.service_check import (
    check_rns_lib, check_meshtastic_lib, check_serial_ports,
    check_rnsd_status, check_meshtasticd_status, check_rns_udp_port,
)

log = logging.getLogger("dashboard")

app = Flask(
    __name__,
    template_folder=os.path.join(os.path.dirname(__file__), 'templates'),
)

# ── Live Data (populated by event bus subscribers) ────────────
_recent_messages = deque(maxlen=50)
_message_lock = threading.Lock()
_bridge_health_ref = None
_node_tracker_ref = None


# ── Rate limiting ─────────────────────────────────────────────
# Per-IP fixed-window counter for /api/* endpoints. Localhost-only by
# default, but a reverse proxy or SSH tunnel can expose these — a flood
# would lock the GIL on Flask's threaded server.
RATE_LIMIT_WINDOW = 60.0  # seconds
RATE_LIMIT_MAX_REQUESTS = 60  # per IP per endpoint per window

_rate_lock = threading.Lock()
_rate_buckets: "defaultdict[tuple[str, str], deque[float]]" = defaultdict(deque)


def _client_ip() -> str:
    """Best-effort client IP. Falls back to 'unknown' off-request."""
    try:
        # request.remote_addr is the direct peer; we deliberately do NOT
        # honour X-Forwarded-For here because the dashboard is meant to bind
        # to localhost. Trusting that header without a known proxy chain
        # would let any caller forge an IP and bypass the limit.
        return request.remote_addr or "unknown"
    except RuntimeError:
        return "unknown"


def rate_limited(max_requests: int = RATE_LIMIT_MAX_REQUESTS,
                 window: float = RATE_LIMIT_WINDOW):
    """Decorator: return HTTP 429 once an IP exceeds the per-route budget."""
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            key = (_client_ip(), request.endpoint or view.__name__)
            now = time.monotonic()
            cutoff = now - window
            with _rate_lock:
                bucket = _rate_buckets[key]
                while bucket and bucket[0] < cutoff:
                    bucket.popleft()
                if len(bucket) >= max_requests:
                    retry_after = max(1, int(window - (now - bucket[0])))
                    response = jsonify({
                        "error": "rate limit exceeded",
                        "retry_after_seconds": retry_after,
                    })
                    response.status_code = 429
                    response.headers["Retry-After"] = str(retry_after)
                    return response
                bucket.append(now)
            return view(*args, **kwargs)
        return wrapper
    return decorator


def _reset_rate_limits() -> None:
    """Test hook — clear all per-IP counters."""
    with _rate_lock:
        _rate_buckets.clear()


def set_bridge_health(health):
    """Wire bridge health monitor into the dashboard (called by launcher)."""
    global _bridge_health_ref
    _bridge_health_ref = health


def set_node_tracker(tracker):
    """Wire node tracker into the dashboard (called by launcher)."""
    global _node_tracker_ref
    _node_tracker_ref = tracker


def _on_message_event(event):
    """Event bus subscriber: buffer recent messages for API."""
    with _message_lock:
        _recent_messages.append({
            "direction": event.direction,
            "content": event.content,
            "node_id": event.node_id,
            "channel": event.channel,
            "network": event.network,
            "timestamp": event.timestamp.isoformat(),
        })


def init_event_subscribers():
    """Subscribe to event bus for dashboard data. Called once at startup."""
    from src.utils.event_bus import event_bus
    event_bus.subscribe("message", _on_message_event)


@app.after_request
def add_security_headers(response):
    """Add security headers to every response (OWASP recommendations)."""
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline'; "
        "frame-ancestors 'none'"
    )
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    return response


@app.route('/')
def home():
    cfg = load_config()
    gw = cfg.get('gateway', {})

    rns_ok, rns_ver = check_rns_lib()
    mesh_ok, mesh_ver = check_meshtastic_lib()
    serial_ports = check_serial_ports()
    rnsd_ok, rnsd_info = check_rnsd_status()
    meshd_ok, meshd_info = check_meshtasticd_status()
    udp_ok, udp_info = check_rns_udp_port()

    return render_template(
        'dashboard.html',
        version=__version__,
        system_platform=f"{platform.system()} {platform.release()}",
        hostname=platform.node(),
        python_version=platform.python_version(),
        rns_ok=rns_ok,
        rns_ver=rns_ver,
        mesh_ok=mesh_ok,
        mesh_ver=mesh_ver,
        serial_ports=serial_ports,
        rnsd_ok=rnsd_ok,
        rnsd_info=rnsd_info,
        meshd_ok=meshd_ok,
        meshd_info=meshd_info,
        udp_ok=udp_ok,
        udp_info=udp_info,
        has_config=bool(cfg),
        gw_name=gw.get('name', '(unset)'),
        gw_port=gw.get('port', '(unset)'),
        gw_connection=gw.get('connection_type', 'serial'),
        gw_bitrate=gw.get('bitrate', '?'),
        bridge_mode=gw.get('bridge_mode', 'direct'),
        node_count=_node_tracker_ref.node_count if _node_tracker_ref else 0,
        bridge_status=(
            _bridge_health_ref.get_bridge_status().value
            if _bridge_health_ref else 'unknown'
        ),
    )


@app.route('/api/messages')
@rate_limited()
def api_messages():
    """Recent message feed (last 50 messages)."""
    with _message_lock:
        messages = list(_recent_messages)
    return jsonify(messages)


@app.route('/api/health')
@rate_limited()
def api_health():
    """Bridge health summary."""
    if _bridge_health_ref is None:
        return jsonify({"error": "Bridge health monitor not initialized"}), 503
    return jsonify(_bridge_health_ref.get_summary())


@app.route('/api/nodes')
@rate_limited()
def api_nodes():
    """Known mesh nodes list."""
    if _node_tracker_ref is None:
        return jsonify({"error": "Node tracker not initialized"}), 503
    return jsonify(_node_tracker_ref.get_all_nodes())


if __name__ == '__main__':
    setup_logging()
    cfg = load_config()
    dash = cfg.get('dashboard', {})
    host = dash.get('host', '127.0.0.1')
    port = dash.get('port', 5000)

    # Validate host/port before binding (MeshForge security pattern)
    ok, err = validate_hostname(host)
    if not ok:
        log.error("Invalid dashboard host: %s. Falling back to 127.0.0.1", err)
        host = '127.0.0.1'
    ok, err = validate_port(port)
    if not ok:
        log.error("Invalid dashboard port: %s. Falling back to 5000", err)
        port = 5000

    if host == '0.0.0.0':
        log.warning("Dashboard binding to all interfaces (0.0.0.0). "
                     "No authentication is enabled. Restrict to 127.0.0.1 in production.")
    log.info("Starting Web Dashboard on %s:%s...", host, port)
    app.run(host=host, port=port, debug=False)
