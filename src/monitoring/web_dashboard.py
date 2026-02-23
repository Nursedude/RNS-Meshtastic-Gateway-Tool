import logging
import os
import platform
import sys

from flask import Flask, render_template

# Ensure project root is on path
_BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _BASE not in sys.path:
    sys.path.insert(0, _BASE)

from version import __version__
from src.utils.common import CONFIG_PATH, load_config, validate_hostname, validate_port
from src.utils.log import setup_logging
from src.utils.service_check import (
    check_rns_lib, check_meshtastic_lib, check_serial_ports,
    check_rnsd_status, check_rns_udp_port,
)

log = logging.getLogger("dashboard")

app = Flask(
    __name__,
    template_folder=os.path.join(os.path.dirname(__file__), 'templates'),
)


@app.route('/')
def home():
    cfg = load_config()
    gw = cfg.get('gateway', {})

    rns_ok, rns_ver = check_rns_lib()
    mesh_ok, mesh_ver = check_meshtastic_lib()
    serial_ports = check_serial_ports()
    rnsd_ok, rnsd_info = check_rnsd_status()
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
        udp_ok=udp_ok,
        udp_info=udp_info,
        has_config=bool(cfg),
        gw_name=gw.get('name', '(unset)'),
        gw_port=gw.get('port', '(unset)'),
        gw_connection=gw.get('connection_type', 'serial'),
        gw_bitrate=gw.get('bitrate', '?'),
    )


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
    app.run(host=host, port=port)
