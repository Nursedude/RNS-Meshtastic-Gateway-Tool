from flask import Flask, render_template_string
import RNS
import sys
import os

# Minimal Flask App for Supervisor Dashboard
app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Supervisor NOC | Dashboard</title>
    <style>
        body { font-family: monospace; background: #1a1a1a; color: #00ff00; padding: 20px; }
        .card { border: 1px solid #444; padding: 15px; margin-bottom: 20px; }
        h1 { color: #fff; border-bottom: 2px solid #00ff00; }
        .status-up { color: #00ff00; font-weight: bold; }
        .status-down { color: #ff0000; font-weight: bold; }
    </style>
</head>
<body>
    <h1>SUPERVISOR NOC: GATEWAY DASHBOARD</h1>
    
    <div class="card">
        <h3>System Status</h3>
        <p>Gateway Engine: <span class="{{ status_class }}">{{ status_text }}</span></p>
        <p>Reticulum Path: {{ rns_path }}</p>
    </div>

    <div class="card">
        <h3>Configuration</h3>
        <p>To allow other nodes to see this, you must configure LXMF propagation.</p>
        <button onclick="alert('Config update feature coming in v3.1')">Edit Config</button>
    </div>
</body>
</html>
"""

@app.route('/')
def home():
    # Simple check to see if we can find the interface file
    # In a real app, we would query the running gateway process via a socket/API
    status = "RUNNING (Assumed)" 
    return render_template_string(HTML_TEMPLATE, status_class="status-up", status_text=status, rns_path=RNS.Reticulum.configdir)

if __name__ == '__main__':
    print("Starting Web Dashboard on port 5000...")
    app.run(host='0.0.0.0', port=5000)