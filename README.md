# Supervisor NOC: RNS-Meshtastic Gateway

**Status:** Alpha — functional but under active testing
**Version:** 1.5
**License:** GPL-3.0
**Python:** 3.9+

> Bridges the **Reticulum Network Stack (RNS)** with **Meshtastic LoRa radios**, allowing RNS traffic (LXMF messages, Sideband, NomadNet, etc.) to ride over LoRa hardware.

## Quick Start

```bash
# 1. Clone
git clone https://github.com/Nursedude/RNS-Meshtastic-Gateway-Tool.git
cd RNS-Meshtastic-Gateway-Tool

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure
cp config.json.example config.json
# Edit config.json — set your serial port or switch to TCP/MQTT mode

# 4. Launch
python src/ui/menu.py
```

## Installation

### Prerequisites

- Python 3.9 or newer
- A Meshtastic radio (connected via USB or accessible via meshtasticd TCP)
- pip (Python package manager)

### Install

```bash
git clone https://github.com/Nursedude/RNS-Meshtastic-Gateway-Tool.git
cd RNS-Meshtastic-Gateway-Tool
pip install -r requirements.txt
```

### Update

```bash
cd RNS-Meshtastic-Gateway-Tool
git pull --ff-only
pip install --upgrade -r requirements.txt
```

Or use option **9** in the Command Center menu to pull updates directly.

### Configuration

Copy the example config and edit it for your setup:

```bash
cp config.json.example config.json
```

**Key settings in `config.json`:**

| Setting | Description | Default |
|---------|-------------|---------|
| `gateway.connection_type` | `serial` or `tcp` | `serial` |
| `gateway.port` | Serial device path (`/dev/ttyUSB0`, `COM3`, etc.) | `COM3` |
| `gateway.host` / `gateway.tcp_port` | meshtasticd TCP address (when using `tcp` mode) | `localhost:4403` |
| `gateway.bridge_mode` | `direct` (Meshtastic API) or `mqtt` (zero-interference MQTT bridge) | `direct` |
| `gateway.bitrate` | LoRa bitrate in bps | `500` |
| `dashboard.host` / `dashboard.port` | Web dashboard bind address | `127.0.0.1:5000` |
| `features.circuit_breaker` | Enable TX circuit breaker | `true` |
| `features.tx_queue` | Enable async TX queue | `true` |
| `features.message_queue` | Enable persistent message queue with retries | `false` |

If no serial port is set, the tool auto-detects connected devices.

### Setup at a Glance

```mermaid
flowchart TD
    A["Clone repository"] --> B["pip install -r requirements.txt"]
    B --> C["cp config.json.example config.json"]
    C --> D{"Connection type?"}

    D -->|"USB radio attached"| E["serial mode<br/>Set gateway.port"]
    D -->|"meshtasticd on network"| F["tcp mode<br/>Set host + tcp_port"]
    D -->|"Zero-interference"| G["mqtt mode<br/>Set mqtt_host + mqtt_port"]

    E --> H{"Launch mode?"}
    F --> H
    G --> H

    H -->|"Interactive"| I["python src/ui/menu.py<br/>Command Center TUI"]
    H -->|"Direct"| J["python launcher.py --debug"]
    H -->|"Service"| K["systemd daemon"]
    H -->|"Browser"| L["python src/monitoring/web_dashboard.py"]

    K --> M["Copy meshgateway.service to /etc/systemd/system/"]
    M --> N["systemctl enable --now meshgateway"]
```

## Usage

### Command Center (recommended)

```bash
python src/ui/menu.py
```

Interactive TUI menu with service status indicators, config editors, and diagnostic tools.

### Direct Gateway Launch

```bash
python launcher.py [--debug]
```

### Daemon Mode (systemd)

```bash
python src/daemon.py start    # Start in foreground (for systemd)
python src/daemon.py stop     # Stop running gateway
python src/daemon.py status   # Check if running
python src/daemon.py restart  # Stop + start
```

### Web Dashboard

```bash
python src/monitoring/web_dashboard.py
```

Opens a browser dashboard at `http://127.0.0.1:5000` with system status, known nodes, and recent messages. Auto-refreshes every 30 seconds.

## Architecture

```mermaid
graph TB
    subgraph Apps["RNS Applications"]
        SB["Sideband"]
        NN["NomadNet"]
        LX["LXMF"]
    end

    subgraph Interface["Gateway Bridge"]
        MI["MeshtasticInterface<br/>Direct Mode"]
        MB["MqttBridge<br/>MQTT Mode"]
    end

    subgraph Radio["LoRa Radio"]
        LR["Meshtastic Device"]
    end

    SB & NN & LX --> MI & MB
    MI --> LR
    MB --> LR

    subgraph Connections["Connection Modes"]
        S["Serial / USB"]
        T["TCP via meshtasticd"]
        M["MQTT Broker"]
    end

    MI --- S
    MI --- T
    MB --- M

    subgraph Reliability["Reliability Layer"]
        CB["Circuit Breaker"]
        HP["Health Probe"]
        RS["Reconnect Strategy"]
        TQ["TX Queue"]
    end

    MI -.-> CB & HP & RS & TQ

    subgraph Services["Background Services"]
        EB["Event Bus"]
        NT["Node Tracker"]
        BH["Bridge Health Monitor"]
    end

    EB -.-> MI & MB
    NT -.-> MI
    BH -.-> MI

    subgraph UI["User Interfaces"]
        CC["Command Center TUI"]
        TD["Terminal Dashboard"]
        WD["Web Dashboard"]
    end

    EB -.-> CC & TD & WD
```

**Core modules:**

- **`launcher.py`** — Main entry point. Initializes RNS, loads config, starts the driver with auto-reconnect and health monitoring.
- **`src/Meshtastic_Interface.py`** — Custom RNS interface translating packets into Meshtastic `sendData()` calls. Supports serial, TCP, and auto-detection.
- **`src/mqtt_bridge.py`** — Alternative MQTT bridge mode that doesn't interfere with meshtasticd's web client.
- **`src/daemon.py`** — Service management with PID locking and watchdog auto-restart.

**UI:**

- **`src/ui/menu.py`** — Command Center TUI with cached service status and startup preflight checks.
- **`src/ui/dashboard.py`** — Terminal snapshot of system info, libraries, services, and config.
- **`src/monitoring/web_dashboard.py`** — Flask browser dashboard.

**Reliability (in `src/utils/`):**

- Circuit breaker, TX queue, reconnect with exponential backoff + jitter
- Active health probe with hysteresis
- Event bus for decoupled RX/TX notifications
- Node tracker with JSON persistence

### Gateway Lifecycle

```mermaid
flowchart TD
    A["Load config.json"] --> B["Initialize Reticulum"]
    B --> C{"bridge_mode?"}
    C -->|direct| D["Create MeshtasticInterface"]
    C -->|mqtt| E["Create MqttBridge"]
    D --> F["Start ReconnectStrategy + BridgeHealthMonitor"]
    E --> F
    F --> G["Start NodeTracker thread"]
    G --> H["Start ActiveHealthProbe thread"]
    H --> I["Register signal handlers"]
    I --> J{"Interface online?"}

    J -->|Yes| K["Record success / reset backoff"]
    K --> L{"Health probe OK?"}
    L -->|Yes| M["Sleep 1s"]
    M --> J
    L -->|"Sustained failure"| N["Mark interface offline"]
    N --> J

    J -->|No| O{"Retries left?"}
    O -->|Yes| P["Wait — exponential backoff + jitter"]
    P --> Q["Attempt reconnect"]
    Q -->|Success| K
    Q -->|Fail| J
    O -->|No| R["Reset strategy / long wait"]
    R --> J

    J -. "SIGTERM / Ctrl+C" .-> S["Shutdown"]
    S --> T["Stop health probe"]
    T --> U["Stop node tracker"]
    U --> V["Detach interface"]
    V --> W["Shutdown event bus + threads"]
    W --> X["Exit"]
```

### Packet Flow

```mermaid
sequenceDiagram
    participant App as RNS App
    participant RNS as Reticulum Transport
    participant IF as MeshtasticInterface
    participant CB as Circuit Breaker
    participant TQ as TX Queue
    participant Radio as LoRa Radio
    participant EB as Event Bus

    Note over App, Radio: TX Path — RNS to Mesh
    App->>RNS: Send packet
    RNS->>IF: process_incoming(data)
    IF->>CB: allow_request()?
    alt Circuit OPEN
        CB-->>IF: Blocked
        IF-->>RNS: Drop + log warning
    else Circuit CLOSED
        CB-->>IF: Allowed
        IF->>TQ: enqueue(data)
        TQ->>Radio: sendData(payload)
        TQ->>EB: emit tx MessageEvent
    end

    Note over App, Radio: RX Path — Mesh to RNS
    Radio->>IF: on_receive(packet)
    IF->>IF: Extract decoded payload
    IF->>EB: emit rx MessageEvent
    IF->>RNS: owner.inbound(payload)
    RNS->>App: Deliver to destination
```

## Connection Modes

| Mode | Config | Use Case |
|------|--------|----------|
| **Serial** | `connection_type: "serial"` | Radio plugged in via USB |
| **TCP** | `connection_type: "tcp"` | Radio managed by meshtasticd on the network |
| **MQTT** | `bridge_mode: "mqtt"` | Zero-interference bridge via MQTT broker |

## Using with MeshForge

This gateway works as a standalone tool or as part of a [MeshForge](https://github.com/Nursedude/meshforge) deployment. MeshForge provides a full mesh network operations center — live NOC maps, multi-network bridging, RF tools, and more.

When running under MeshForge:

- MeshForge manages service lifecycles (rnsd, meshtasticd) — the gateway integrates with its health check and startup patterns
- Shared architectural patterns: circuit breaker, reconnect strategy, event bus, and status caching are aligned between both projects
- The gateway can be launched from MeshForge's TUI or run independently

To use standalone, no MeshForge installation is needed — the gateway has no dependency on it.

## Testing Status

This project is in **alpha**. Core gateway functionality (TX/RX, reconnect, health monitoring) is functional but many features need real-world multi-node testing.

**What has been tested:**

- Single-node TX/RX over serial and TCP
- Circuit breaker and reconnect logic (unit tests)
- TUI menu and dashboard rendering
- MQTT bridge message flow (unit tests)
- 436 unit tests passing

**What needs more testing:**

- Multi-node mesh scenarios
- Long-running stability (24h+ uptime)
- MQTT bridge under real broker load
- Packet acknowledgement and delivery confirmation
- Edge cases: radio disconnect during TX, firmware updates, channel changes
- Web dashboard under concurrent access
- Daemon watchdog recovery scenarios

### Running Tests

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

## Troubleshooting

| Problem | Fix |
|---------|-----|
| No LED activity on radio | Check that `ingress_control` is `False` in the driver |
| Crash on start | Verify RNS is installed (`pip install rns`) and check logs at `~/.config/rns-gateway/logs/` |
| "Port in use" error | The preflight check will warn you — stop the conflicting process or use a different port |
| No serial device found | Check USB connection; on Linux you may need `sudo usermod -aG dialout $USER` |
| Wrong serial port | Edit `config.json` and set `gateway.port` to your device path |
| Gateway starts but no traffic | Run the test ping from the Command Center (option 8) or check `rnstatus` (option 7) |
| Web dashboard won't start | Install Flask: `pip install flask` |

Logs are written to `~/.config/rns-gateway/logs/`. Use `--debug` for verbose output.

## Security

See [`docs/SECURITY.md`](docs/SECURITY.md) for the full security review.

Key points:

- Web dashboard binds to `127.0.0.1` by default — do not expose to untrusted networks without authentication
- `config.json` is gitignored to prevent credential leaks — never commit it
- Environment variable editor detection is validated against PATH to prevent injection
- Dependencies are pinned to compatible ranges — keep them updated

## Roadmap

```mermaid
gantt
    title Project Roadmap
    dateFormat YYYY-MM-DD
    axisFormat %b %Y

    section Completed
    Basic TX/RX over Meshtastic          :done, tx,     2024-06-01, 30d
    Command Center TUI                   :done, tui,    after tx, 30d
    Terminal + Web Dashboards            :done, dash,   after tui, 21d
    Cross-platform Support               :done, cross,  after dash, 14d
    TCP Connection Mode                  :done, tcp,    after cross, 21d
    MQTT Bridge Mode                     :done, mqtt,   after tcp, 21d
    Circuit Breaker + TX Queue           :done, cb,     after mqtt, 21d
    Node Tracking + Persistence          :done, nt,     after cb, 14d
    Daemon Mode + Watchdog               :done, daemon, after nt, 14d
    Preflight Checks + Port Detection    :done, pre,    after daemon, 14d

    section Next Up
    Multi-node Mesh Testing              :active, multi,   2025-06-01, 60d
    Packet Acknowledgement Handling      :         ack,     after multi, 45d
    Message Delivery Confirmation        :         confirm, after ack, 45d
    RPi Performance Profiling            :         rpi,     after confirm, 30d
```
