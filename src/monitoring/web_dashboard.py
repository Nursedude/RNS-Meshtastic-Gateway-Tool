import json
import os
import platform
import sys

from flask import Flask, render_template_string

# Ensure project root is on path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from version import __version__

app = Flask(__name__)

CONFIG_PATH = os.path.join(BASE_DIR, 'config.json')


def load_config():
    try:
        with open(CONFIG_PATH, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, PermissionError):
        return {}


def check_rns_lib():
    try:
        import RNS
        return True, getattr(RNS, '__version__', 'unknown')
    except ImportError:
        return False, "not installed"


def check_meshtastic_lib():
    try:
        import meshtastic
        return True, getattr(meshtastic, '__version__', 'unknown')
    except ImportError:
        return False, "not installed"


def check_serial_ports():
    try:
        from serial.tools.list_ports import comports
        ports = [p.device for p in comports()]
        return ports if ports else ["(none detected)"]
    except ImportError:
        return ["(pyserial not installed)"]


HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Supervisor NOC | Dashboard v{{ version }}</title>
    <meta http-equiv="refresh" content="30">
    <style>
        body { font-family: monospace; background: #1a1a1a; color: #00ff00; padding: 20px; max-width: 800px; margin: 0 auto; }
        .card { border: 1px solid #444; padding: 15px; margin-bottom: 20px; border-radius: 4px; }
        h1 { color: #fff; border-bottom: 2px solid #00ff00; padding-bottom: 10px; }
        h3 { color: #00ccff; margin-top: 0; }
        .ok { color: #00ff00; font-weight: bold; }
        .err { color: #ff4444; font-weight: bold; }
        .dim { color: #888; }
        table { width: 100%; border-collapse: collapse; }
        td { padding: 4px 8px; }
        td:first-child { color: #00ccff; white-space: nowrap; width: 140px; }
    </style>
</head>
<body>
    <h1>SUPERVISOR NOC <span class="dim">v{{ version }}</span></h1>

    <div class="card">
        <h3>System</h3>
        <table>
            <tr><td>Platform</td><td>{{ system_platform }}</td></tr>
            <tr><td>Hostname</td><td>{{ hostname }}</td></tr>
            <tr><td>Python</td><td>{{ python_version }}</td></tr>
        </table>
    </div>

    <div class="card">
        <h3>Libraries</h3>
        <table>
            <tr>
                <td>Reticulum</td>
                <td>{% if rns_ok %}<span class="ok">OK</span> v{{ rns_ver }}{% else %}<span class="err">MISSING</span>{% endif %}</td>
            </tr>
            <tr>
                <td>Meshtastic</td>
                <td>{% if mesh_ok %}<span class="ok">OK</span> v{{ mesh_ver }}{% else %}<span class="err">MISSING</span>{% endif %}</td>
            </tr>
        </table>
    </div>

    <div class="card">
        <h3>Serial Ports</h3>
        <table>
            {% for port in serial_ports %}
            <tr><td colspan="2">{{ port }}</td></tr>
            {% endfor %}
        </table>
    </div>

    <div class="card">
        <h3>Gateway Config</h3>
        {% if has_config %}
        <table>
            <tr><td>Node Name</td><td>{{ gw_name }}</td></tr>
            <tr><td>Radio Port</td><td>{{ gw_port }}</td></tr>
            <tr><td>Connection</td><td>{{ gw_connection }}</td></tr>
            <tr><td>Bitrate</td><td>{{ gw_bitrate }} bps</td></tr>
        </table>
        {% else %}
        <p class="err">config.json not found or invalid</p>
        <p class="dim">Expected at: {{ config_path }}</p>
        {% endif %}
    </div>

    <p class="dim">Auto-refreshes every 30s</p>
</body>
</html>
"""


@app.route('/')
def home():
    cfg = load_config()
    gw = cfg.get('gateway', {})
    rns_ok, rns_ver = check_rns_lib()
    mesh_ok, mesh_ver = check_meshtastic_lib()
    serial_ports = check_serial_ports()

    return render_template_string(
        HTML_TEMPLATE,
        version=__version__,
        system_platform=f"{platform.system()} {platform.release()}",
        hostname=platform.node(),
        python_version=platform.python_version(),
        rns_ok=rns_ok,
        rns_ver=rns_ver,
        mesh_ok=mesh_ok,
        mesh_ver=mesh_ver,
        serial_ports=serial_ports,
        has_config=bool(cfg),
        gw_name=gw.get('name', '(unset)'),
        gw_port=gw.get('port', '(unset)'),
        gw_connection=gw.get('connection_type', 'serial'),
        gw_bitrate=gw.get('bitrate', '?'),
        config_path=CONFIG_PATH,
    )


if __name__ == '__main__':
    cfg = load_config()
    dash = cfg.get('dashboard', {})
    host = dash.get('host', '0.0.0.0')
    port = dash.get('port', 5000)
    print(f"Starting Web Dashboard on {host}:{port}...")
    app.run(host=host, port=port)
