from flask import Flask, render_template_string, jsonify
import json
import os
import sys

# Add root to path so we can see RNS
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

app = Flask(__name__)

# Locate config relative to this script
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_PATH = os.path.join(BASE_DIR, 'config.json')

with open(CONFIG_PATH, 'r') as f:
    config = json.load(f)

HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Supervisor NOC | Deep Dive</title>
    <style>
        body { background-color: #0d1117; color: #c9d1d9; font-family: 'Segoe UI', monospace; padding: 20px; }
        .header { border-bottom: 2px solid #238636; padding-bottom: 10px; margin-bottom: 20px; }
        .card { background: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 20px; margin-bottom: 20px; }
        h1 { color: #238636; }
        h3 { margin-top: 0; color: #58a6ff; }
        .stat { font-size: 24px; font-weight: bold; }
        .status-ok { color: #3fb950; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; }
    </style>
    <script>
        setTimeout(function(){ location.reload(); }, 5000);
    </script>
</head>
<body>
    <div class="header">
        <h1>Supervisor NOC // Deep Dive</h1>
        <span>Gateway Node: <strong>{{ node_name }}</strong></span>
    </div>
    <div class="grid">
        <div class="card">
            <h3>Interface Status</h3>
            <div class="stat status-ok">ONLINE</div>
            <p>Port: {{ port }}</p>
            <p>Bitrate: {{ bitrate }} bps</p>
        </div>
        <div class="card">
            <h3>Configuration</h3>
            <pre>{{ config_dump }}</pre>
        </div>
    </div>
</body>
</html>
"""

@app.route('/')
def home():
    return render_template_string(HTML, 
                                  node_name=config['gateway']['name'],
                                  port=config['gateway']['port'],
                                  bitrate=config['gateway']['bitrate'],
                                  config_dump=json.dumps(config['features'], indent=2))

if __name__ == '__main__':
    print(f"Starting Dashboard on port {config['dashboard']['port']}")
    app.run(host=config['dashboard']['host'], port=config['dashboard']['port'])
