# RNS-Meshtastic Gateway Tool - Claude Code Configuration

> **Author**: WH6GXZ (Nursedude)
> **Status**: Alpha — functional, under active testing
> **Version**: 1.5

## Quick Context

Bridges the Reticulum Network Stack (RNS) with Meshtastic LoRa radios.
Allows RNS traffic (LXMF messages, Sideband, NomadNet) to ride over LoRa hardware.
Supports serial, TCP, and MQTT bridge modes.

## Key Commands

```bash
# Install
pip install -r requirements.txt

# Configure
cp config.json.example config.json

# Launch TUI menu
python src/ui/menu.py

# Launch daemon directly
python src/daemon.py

# Run tests
python -m pytest tests/ -v
```

## Architecture

```
├── launcher.py            # Entry point
├── config.json.example    # Configuration template
├── version.py             # Version info
├── src/
│   ├── daemon.py          # Gateway daemon
│   ├── Meshtastic_Interface.py  # Meshtastic radio interface
│   ├── mqtt_bridge.py     # MQTT bridge mode (zero-interference)
│   ├── ui/                # TUI menu system
│   ├── monitoring/        # Network monitoring
│   └── utils/             # Shared utilities
├── scripts/               # Helper scripts
└── tests/                 # Test suite
```

## Configuration

Key settings in `config.json`:

| Setting | Description | Default |
|---------|-------------|---------|
| `gateway.connection_type` | `serial` or `tcp` | `serial` |
| `gateway.bridge_mode` | `direct` or `mqtt` | `direct` |
| `gateway.bitrate` | LoRa bitrate in bps | `500` |
| `features.circuit_breaker` | TX circuit breaker | `true` |
| `features.tx_queue` | Async TX queue | `true` |
| `features.message_queue` | Persistent queue with retries | `false` |

## Code Standards

- Python 3.9+
- Security: no `shell=True`, no bare `except:`, validate inputs, subprocess timeouts
- Use `config.json` for all runtime settings — no hardcoded values
- Test against both serial and TCP Meshtastic connections

## Relationship to MeshForge

This is the **standalone gateway tool**. MeshForge NOC (`/opt/meshforge`) has its own
integrated gateway in `src/gateway/`. They share concepts but are independent codebases.
Features proven here may be ported to MeshForge's gateway module.

## Contact

- GitHub: github.com/Nursedude/RNS-Meshtastic-Gateway-Tool
- Callsign: WH6GXZ
