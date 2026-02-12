# RNS-Meshtastic Gateway Tool

> Bridge the **Reticulum Network Stack (RNS)** with **Meshtastic LoRa radios** — route LXMF messages, Sideband traffic, and NomadNet pages over LoRa hardware.

**Version:** 2.4.0-alpha
**License:** GPL-3.0
**Python:** 3.9+
**Part of the [MeshForge](https://github.com/Nursedude/MeshForge) ecosystem**

---

## How It Works

The gateway sits between Reticulum and your Meshtastic radio. RNS packets go in, LoRa packets come out (and vice versa).

```mermaid
graph LR
    subgraph Reticulum
        A[RNS Core] -->|packets| B[MeshtasticInterface Driver]
    end

    subgraph Hardware
        B -->|sendData| C[Meshtastic Radio]
        C -->|on_receive| B
    end

    subgraph Network
        C <-.->|LoRa RF| D[Other Mesh Nodes]
    end

    style A fill:#1a1a2e,stroke:#00ff00,color:#00ff00
    style B fill:#16213e,stroke:#0f3460,color:#e94560
    style C fill:#0f3460,stroke:#e94560,color:#fff
    style D fill:#0f3460,stroke:#e94560,color:#fff
```

## Architecture

```mermaid
graph TB
    subgraph "Entry Points"
        L[launcher.py<br/>Gateway Engine]
        M[src/ui/menu.py<br/>Command Center TUI]
        W[src/monitoring/web_dashboard.py<br/>Flask Dashboard :5000]
    end

    subgraph "Core Driver"
        I[src/Meshtastic_Interface.py<br/>RNS Interface Driver]
    end

    subgraph "External"
        RNS[Reticulum<br/>~/.reticulum/config]
        HW[Meshtastic Radio<br/>Serial/USB]
    end

    L --> I
    M --> L
    I <--> RNS
    I <--> HW
    W -.->|status| RNS

    style L fill:#1a1a2e,stroke:#00ff00,color:#00ff00
    style M fill:#1a1a2e,stroke:#0f3460,color:#e94560
    style W fill:#1a1a2e,stroke:#0f3460,color:#e94560
    style I fill:#16213e,stroke:#e94560,color:#fff
    style RNS fill:#0f3460,stroke:#00ff00,color:#00ff00
    style HW fill:#0f3460,stroke:#e94560,color:#fff
```

### Project Structure

```
RNS-Meshtastic-Gateway-Tool/
├── launcher.py                  # Gateway entry point — init RNS, load driver, keep alive
├── config.json.example          # Configuration template
├── requirements.txt             # Dependencies: rns, meshtastic, pyserial
├── start_gateway.bat            # Windows quick-start
│
├── src/
│   ├── Meshtastic_Interface.py  # RNS ↔ Meshtastic driver (core)
│   ├── proven_supervisor.py     # Supervisor logic
│   ├── monitoring/
│   │   └── web_dashboard.py     # Flask status dashboard
│   └── ui/
│       ├── menu.py              # TUI Command Center v4.1
│       ├── dashboard.py         # Terminal dashboard display
│       └── widgets.py           # Shared box-drawing widgets
│
├── tests/
│   └── broadcast.py             # RNS announce test utility
│
└── docs/
    └── KNOWLEDGE_BASE.md        # Crash resolutions & RNS compliance notes
```

---

## Quick Start

### Prerequisites

- Python 3.9+
- Meshtastic radio connected via USB (or meshtasticd running for TCP mode — see [Roadmap](#roadmap))
- Reticulum installed and configured

### Install

```bash
git clone https://github.com/Nursedude/RNS-Meshtastic-Gateway-Tool.git
cd RNS-Meshtastic-Gateway-Tool
pip install -r requirements.txt
```

### Configure

```bash
cp config.json.example config.json
```

Edit `config.json` to match your setup:

```json
{
    "gateway": {
        "name": "Supervisor NOC",
        "port": "COM3",
        "bitrate": 500
    },
    "dashboard": {
        "host": "0.0.0.0",
        "port": 5000
    }
}
```

| Field | Description | Default |
|-------|-------------|---------|
| `gateway.port` | Serial port for Meshtastic radio | `COM3` |
| `gateway.bitrate` | LoRa bitrate proxy for RNS | `500` |
| `dashboard.host` | Web dashboard bind address | `0.0.0.0` |
| `dashboard.port` | Web dashboard port | `5000` |

**Linux serial ports:** `/dev/ttyUSB0`, `/dev/ttyACM0`, etc.

### Run

**Gateway only:**
```bash
python launcher.py
```

**Command Center (full TUI):**
```bash
python -m src.ui.menu
```

**Windows:**
```
start_gateway.bat
```

### Verify

Look for this output:
```
============================================================
  SUPERVISOR NOC | RNS-MESHTASTIC GATEWAY v2.4
============================================================

[GO] Loading Interface 'Meshtastic Radio'...
[Meshtastic Radio] Initializing on COM3...
[Meshtastic Radio] Hardware Connected Successfully.
 [SUCCESS] Interface Loaded! Waiting for traffic...
```

Then run `rnstatus` in another terminal to confirm the interface is registered.

---

## Data Flow

```mermaid
sequenceDiagram
    participant App as RNS App<br/>(Sideband/LXMF)
    participant RNS as Reticulum Core
    participant DRV as MeshtasticInterface
    participant HW as Meshtastic Radio
    participant MESH as Mesh Network

    Note over App,MESH: Transmit Path (TX)
    App->>RNS: outbound packet
    RNS->>DRV: process_incoming(data)
    DRV->>HW: sendData(data, '^all')
    HW->>MESH: LoRa RF broadcast

    Note over App,MESH: Receive Path (RX)
    MESH->>HW: LoRa RF packet
    HW->>DRV: on_receive(packet)
    DRV->>RNS: owner.inbound(payload)
    RNS->>App: deliver to destination
```

---

## Command Center

The TUI provides a unified control panel:

| Key | Action | Description |
|-----|--------|-------------|
| `1` | Start Mesh Gateway | Launch `launcher.py` in background |
| `2` | Start NomadNet | Launch NomadNet client |
| `3` | Open Web Deep-Dive | Open dashboard in browser |
| `d` | Terminal Dashboard | Live terminal status view |
| `4` | Edit Gateway Config | Open `config.json` in editor |
| `5` | Edit Reticulum Config | Open `~/.reticulum/config` |
| `6` | Edit NomadNet Config | Open `~/.nomadnet/config` |
| `7` | RNS Status | Run `rnstatus` |
| `8` | Fire Test Ping | Send broadcast announce |
| `9` | Git Update | `git pull --ff-only` |
| `0` | Exit | Quit Command Center |

---

## RNS Driver Compliance

The driver must satisfy strict RNS interface requirements or the stack will crash. These are documented in [`docs/KNOWLEDGE_BASE.md`](docs/KNOWLEDGE_BASE.md).

| Attribute | Type | Why It Matters |
|-----------|------|----------------|
| `ingress_control` | `bool = False` | Prevents "Traffic Cop" crash |
| `held_announces` | `list = []` | Must be list, not int — `len()` crash |
| `ia_freq_deque` | `deque(maxlen=100)` | Required by `rnstatus` |
| `oa_freq_deque` | `deque(maxlen=100)` | Required by `rnstatus` |
| `mode` | `MODE_ACCESS_POINT` | Correct reporting in `rnstatus` |

---

## Testing

> **Status: Needs Testing** — The gateway works in isolated manual tests but has not been through systematic validation.

### Test Plan

```mermaid
graph TD
    T1[Unit: Driver Init]
    T2[Unit: RNS Compliance Attributes]
    T3[Integration: Serial Connection]
    T4[Integration: TX Path]
    T5[Integration: RX Path]
    T6[E2E: Two-Node Bridge]
    T7[E2E: LXMF Over Mesh]
    T8[Stress: Sustained Traffic]
    T9[Regression: rnstatus]

    T1 --> T3
    T2 --> T3
    T3 --> T4
    T3 --> T5
    T4 --> T6
    T5 --> T6
    T6 --> T7
    T7 --> T8
    T6 --> T9

    style T1 fill:#2d3436,stroke:#00b894,color:#00b894
    style T2 fill:#2d3436,stroke:#00b894,color:#00b894
    style T3 fill:#2d3436,stroke:#fdcb6e,color:#fdcb6e
    style T4 fill:#2d3436,stroke:#fdcb6e,color:#fdcb6e
    style T5 fill:#2d3436,stroke:#fdcb6e,color:#fdcb6e
    style T6 fill:#2d3436,stroke:#e17055,color:#e17055
    style T7 fill:#2d3436,stroke:#e17055,color:#e17055
    style T8 fill:#2d3436,stroke:#d63031,color:#d63031
    style T9 fill:#2d3436,stroke:#fdcb6e,color:#fdcb6e
```

### Test Matrix

| ID | Test | Type | Hardware | Status |
|----|------|------|----------|--------|
| T1 | Driver initializes without crash (no radio) | Unit | None | Not run |
| T2 | All RNS compliance attributes present and correct types | Unit | None | Not run |
| T3 | Serial connection to Meshtastic radio succeeds | Integration | 1 radio | Not run |
| T4 | TX: RNS packet reaches radio (`sendData` called) | Integration | 1 radio | Not run |
| T5 | RX: Mesh packet delivered to RNS (`owner.inbound` called) | Integration | 1 radio | Not run |
| T6 | Two-node bridge: packet sent from Node A arrives at Node B | E2E | 2 radios | Not run |
| T7 | LXMF message traverses mesh (Sideband-to-Sideband) | E2E | 2 radios | Not run |
| T8 | Sustained traffic (100 packets, measure loss rate) | Stress | 2 radios | Not run |
| T9 | `rnstatus` reports interface correctly while gateway runs | Regression | 1 radio | Not run |

### Running Tests

```bash
# Broadcast test (requires radio connected)
python tests/broadcast.py

# RNS status check (requires gateway running)
python -m RNS.Utilities.rnstatus
```

---

## Roadmap

```mermaid
gantt
    title RNS-Meshtastic Gateway Roadmap
    dateFormat YYYY-MM-DD
    axisFormat %b %Y

    section v2.4 Current
    Serial TX/RX                     :done,    v24a, 2026-01-01, 2026-01-15
    RNS Compliance Stabilization     :done,    v24b, 2026-01-05, 2026-01-10
    TUI Command Center               :done,    v24c, 2026-01-10, 2026-01-20
    Security Hardening               :done,    v24d, 2026-01-15, 2026-01-20

    section v2.5 TCP Connection Mode
    TCP Interface Support            :active,  v25a, 2026-02-12, 2026-02-28
    Config: connection_type field    :         v25b, 2026-02-12, 2026-02-20
    Unit Tests for Driver            :         v25c, 2026-02-20, 2026-03-01
    Integration Tests (Serial+TCP)   :         v25d, 2026-03-01, 2026-03-10

    section v2.6 HTTP Protobuf TX
    HTTP Protobuf Client             :         v26a, 2026-03-10, 2026-03-25
    Hybrid RX/TX Split               :         v26b, 2026-03-15, 2026-03-30
    Circuit Breaker                  :         v26c, 2026-03-20, 2026-04-01

    section v3.0 MQTT Bridge
    MQTT RX Subscription             :         v30a, 2026-04-01, 2026-04-15
    Zero-Interference Mode           :         v30b, 2026-04-10, 2026-04-25
    Full MeshForge Parity            :         v30c, 2026-04-15, 2026-05-01

    section v3.x Future
    Multi-Node Routing               :         v3xa, 2026-05-01, 2026-06-01
    Packet ACK Handling              :         v3xb, 2026-05-15, 2026-06-15
    AREDN Integration                :         v3xc, 2026-06-01, 2026-07-01
```

### Phase Details

#### v2.5 — TCP Connection Mode (Next)
Add meshtasticd TCP support alongside the existing serial path. No breaking changes.

| Task | Description | Files |
|------|-------------|-------|
| Add `TCPInterface` support | Connect via `meshtastic.tcp_interface.TCPInterface(host, port)` | `src/Meshtastic_Interface.py` |
| Config: `connection_type` | `"serial"` (default) or `"tcp"` with `host`/`tcp_port` fields | `config.json.example` |
| Pass config to driver | Load expanded config in launcher | `launcher.py` |
| Unit tests | Verify driver init, attribute compliance, connection mode selection | `tests/` |

```mermaid
graph LR
    subgraph "v2.5 Connection Modes"
        CFG[config.json] -->|connection_type| DRV[MeshtasticInterface]
        DRV -->|serial| SER[SerialInterface<br/>USB/COM]
        DRV -->|tcp| TCP[TCPInterface<br/>meshtasticd :4403]
    end

    style CFG fill:#1a1a2e,stroke:#00ff00,color:#00ff00
    style DRV fill:#16213e,stroke:#e94560,color:#fff
    style SER fill:#0f3460,stroke:#00ff00,color:#00ff00
    style TCP fill:#0f3460,stroke:#fdcb6e,color:#fdcb6e
```

#### v2.6 — HTTP Protobuf TX
Solve the meshtasticd **single-client TCP limitation** (port 4403 allows only ONE connection). Use HTTP API for transmit while keeping TCP/serial for receive.

| Task | Description |
|------|-------------|
| HTTP protobuf client | PUT `/api/v1/toradio` on port 9443 |
| Hybrid RX/TX split | RX via TCP pub/sub, TX via HTTP |
| Circuit breaker | Prevent cascading failures on connection loss |
| Auto-reconnect | Exponential backoff on disconnect |

```mermaid
graph LR
    subgraph "v2.6 Hybrid TX/RX"
        DRV[Driver]
        DRV -->|RX| TCP[TCP :4403<br/>pub/sub receive]
        DRV -->|TX| HTTP[HTTP :9443<br/>/api/v1/toradio]
        CB[Circuit Breaker] -.->|guards| HTTP
    end

    TCP --> DAEMON[meshtasticd]
    HTTP --> DAEMON

    style DRV fill:#16213e,stroke:#e94560,color:#fff
    style TCP fill:#0f3460,stroke:#00ff00,color:#00ff00
    style HTTP fill:#0f3460,stroke:#fdcb6e,color:#fdcb6e
    style CB fill:#2d3436,stroke:#d63031,color:#d63031
    style DAEMON fill:#0f3460,stroke:#e94560,color:#fff
```

#### v3.0 — MQTT Bridge Mode
Full MeshForge parity. Zero interference with the meshtasticd web client.

| Task | Description |
|------|-------------|
| MQTT RX | Subscribe to `msh/{region}/2/json/{channel}/#` |
| HTTP TX | Transmit via `/api/v1/toradio` protobuf |
| Zero-interference | No TCP connection held — web client works freely |
| Deduplication | 60-second window to prevent message loops |

```mermaid
graph TB
    subgraph "v3.0 Zero-Interference"
        MQTT[MQTT Broker<br/>mosquitto] -->|subscribe| DRV[Driver RX]
        DRV2[Driver TX] -->|HTTP protobuf| API[meshtasticd<br/>:9443 /api/v1/toradio]
        WEB[Web Client] -->|TCP :4403| DAEMON[meshtasticd]
    end

    DAEMON -->|publishes| MQTT
    API --> DAEMON

    style MQTT fill:#16213e,stroke:#00ff00,color:#00ff00
    style DRV fill:#16213e,stroke:#00ff00,color:#00ff00
    style DRV2 fill:#16213e,stroke:#fdcb6e,color:#fdcb6e
    style API fill:#0f3460,stroke:#fdcb6e,color:#fdcb6e
    style WEB fill:#0f3460,stroke:#e94560,color:#fff
    style DAEMON fill:#0f3460,stroke:#e94560,color:#fff
```

#### v3.x — Future
- **Multi-node routing** — Map RNS destination hashes to Meshtastic node IDs
- **Packet ACK handling** — Delivery confirmation across the bridge
- **AREDN integration** — Third mesh ecosystem bridge
- **Coverage mapping** — RF link quality visualization

---

## Version History

| Version | Date | Milestone |
|---------|------|-----------|
| **2.4.0-alpha** | 2026-02-12 | Current — Serial TX/RX, TUI Command Center, security hardening |
| 2.3.0 | 2026-01-20 | Security patch (shell=False, subprocess timeouts) |
| 2.2.0 | 2026-01-15 | TUI Command Center v4.1, box-drawing widgets |
| 2.1.0 | 2026-01-10 | RNS compliance stabilization (ia_freq_deque, ingress_control, held_announces) |
| 2.0.0 | 2026-01-05 | MeshForge directory restructure, driver architecture |
| 1.0.0 | 2025-12 | Initial serial bridge (TX + RX) |

### Commit History Reference

```
cf5e7a7 docs: add session notes for meshtasticd HTTP API research
3b7908d Merge pull request #7 — extract box-drawing widgets
04565d2 refactor(ui): extract box-drawing widgets, fix bare excepts
bb3548f Merge pull request #6 — improve meshforge TUI
0316b16 feat(tui): overhaul Command Center with box-drawing UI
4bc0d66 feat(nomadnet): integrate nomad_pages skeleton
11fddd2 feat(ui): implement Supervisor Command Center
42f6435 chore: add .gitignore, remove pycache
69c9468 refactor: apply Meshforge directory structure
6738100 feat(gateway): stabilize RNS-Meshtastic bridge
872a1a8 security: enforce shell=False and subprocess timeouts
1dc3c19 initial: restored MeshForge environment
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `Hardware Error: [Errno 2]` | Wrong serial port | Set `gateway.port` in `config.json` to your device (`/dev/ttyUSB0`, `COM3`, etc.) |
| `'meshtastic' library not found` | Missing dependency | `pip install meshtastic` |
| Crash on `rnstatus` | Missing deque attributes | Verify driver has `ia_freq_deque` and `oa_freq_deque` |
| "Traffic Cop" crash | `ingress_control` not set | Must be `False` in driver init |
| `held_announces` crash | Initialized as `int` | Must be `list []` |
| Packets not leaving radio | Missing broadcast flag | `sendData()` must use `destinationId='^all'` |
| Serial port locked | Another process has it | Only one process per port — stop conflicting scripts |
| Gateway starts but no traffic | RNS not finding interface | Check `~/.reticulum/config` and run `rnstatus` |

---

## Related Projects

- **[MeshForge](https://github.com/Nursedude/MeshForge)** — Full NOC with MQTT bridge, coverage mapping, RF tools
- **[Reticulum](https://github.com/markqvist/Reticulum)** — Encrypted networking stack
- **[Meshtastic](https://meshtastic.org/)** — LoRa mesh firmware
- **[NomadNet](https://github.com/markqvist/NomadNet)** — Resilient mesh communicator
- **[Sideband](https://github.com/markqvist/Sideband)** — Mobile LXMF client

---

## Contributing

1. Fork the repo
2. Create a feature branch (`git checkout -b feature/my-change`)
3. Commit with clear messages (`git commit -m "feat: add TCP connection mode"`)
4. Push and open a PR against `main`

See [`SESSION_NOTES_2026-02-12.md`](SESSION_NOTES_2026-02-12.md) for the current development plan.

---

## License

GPL-3.0 — See [LICENSE](LICENSE) for details.
