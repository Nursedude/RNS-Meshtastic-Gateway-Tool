# Supervisor NOC: RNS & Meshtastic Gateway
**Status:** Alpha / Functional
**Version:** 1.1

## Overview
This tool bridges the **Reticulum Network Stack (RNS)** with **Meshtastic LoRa radios**. It allows RNS traffic (LXMF messages, Sideband, etc.) to ride over LoRa hardware using the Meshtastic Python API.

## Architecture
* **Launcher (`launcher.py`):** Main entry point. Initializes RNS, loads `config.json`, and starts the Meshtastic driver.
* **Driver (`src/Meshtastic_Interface.py`):** Custom RNS interface that translates packets into Meshtastic `sendData()` calls. Supports serial/USB and TCP (meshtasticd) connections with auto-detection of serial ports.
* **Command Center (`src/ui/menu.py`):** Interactive TUI menu for launching the gateway, editing configs, running diagnostics, and more.
* **Terminal Dashboard (`src/ui/dashboard.py`):** Snapshot view of system info, library versions, serial ports, and gateway config.
* **Web Dashboard (`src/monitoring/web_dashboard.py`):** Flask-based browser dashboard showing system status, library versions, serial ports, and config. Auto-refreshes every 30s.
* **Config:** Uses `config.json` for gateway settings and `~/.reticulum/config` for RNS.

## How to Run

### Install Dependencies
```bash
pip install -r requirements.txt
```

### Option A: Command Center (recommended)
```bash
python src/ui/menu.py
```
This opens the interactive menu where you can launch the gateway, edit configs, view status, and run tools.

### Option B: Direct Gateway Launch
```bash
python launcher.py
```

### Setup
1. **Connect Radio:** Plug in your Meshtastic device via USB.
2. **Configure:** Copy `config.json.example` to `config.json` and set your serial port:
   - **Windows:** `COM3`, `COM4`, etc.
   - **Linux:** `/dev/ttyUSB0`, `/dev/ttyACM0`, etc.
   - If no port is set, the tool auto-detects connected serial devices.
3. **Start:** Launch via Command Center or directly with `python launcher.py`.
4. **Verify:** Look for `[Meshtastic Radio] Hardware Connected Successfully`.

## Features
* Interactive Command Center (TUI) with box-drawing UI
* Terminal dashboard with system diagnostics and RNS daemon health checks
* Web dashboard (Flask) with auto-refresh
* Serial/USB and TCP (meshtasticd) connection modes
* Auto-reconnect with exponential backoff and jitter
* Cross-platform serial port auto-detection
* Config editor integration (nano/vim/notepad)
* RNS status tool integration
* Broadcast test utility
* Git self-update from menu

## Running Tests
```bash
pip install pytest
pytest tests/ -v
```

## Security
This project has undergone a security review. See `docs/SECURITY.md` for:
* Full findings and severity ratings
* Remediation status
* Security best practices for deployment

**Key notes:**
* The web dashboard binds to `127.0.0.1` by default. Do not expose it to untrusted networks without authentication.
* Copy `config.json.example` to `config.json` — the latter is gitignored to prevent credential leaks.
* Keep dependencies updated: `pip install --upgrade -r requirements.txt`

## Troubleshooting
* **No LED activity?** Check `ingress_control` in the driver — must be `False`.
* **Crash on start?** Verify `RNS.Interfaces.Interface` inheritance and check `docs/KNOWLEDGE_BASE.md`.
* **Stuck on "Waiting"?** Run the test ping from the Command Center (option 8) or `python tests/broadcast.py`.
* **Wrong port?** Edit `config.json` and set `gateway.port` to your device path.

## Roadmap
* [x] Basic Transmit (TX)
* [x] Basic Receive (RX)
* [x] Command Center TUI
* [x] Terminal & Web Dashboards
* [x] Cross-platform support
* [x] TCP connection mode (meshtasticd)
* [ ] Multi-node testing
* [ ] Packet acknowledgement handling
