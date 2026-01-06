# RNS-Meshtastic Gateway Tool

[![Version](https://img.shields.io/badge/version-2.0.0--Alpha-blue.svg)](https://github.com/Nursedude/RNS-Meshtastic-Gateway-Tool)
[![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20Raspberry%20Pi%20%7C%20Windows-green.svg)](#installation)
[![License](https://img.shields.io/badge/license-GPL--3.0-orange.svg)](LICENSE)
[![MeshForge](https://img.shields.io/badge/MeshForge-Integrated-purple.svg)](https://github.com/Nursedude/meshforge)

> **Bridge the gap between Meshtastic and Reticulum networks.** A Supervisor NOC for heterogeneous mesh networks built with the Aloha spirit.

```
    ╔═══════════════════════════════════════════════════════════════╗
    ║                                                               ║
    ║   ┌─────────────┐         GATEWAY          ┌─────────────┐   ║
    ║   │ MESHTASTIC  │◄═══════════════════════►│  RETICULUM  │   ║
    ║   │   Network   │    Bidirectional Bridge  │   Network   │   ║
    ║   │             │                          │    (RNS)    │   ║
    ║   │  LoRa Mesh  │    ┌───────────────┐    │  Encrypted  │   ║
    ║   │  Long Range │◄──►│ Unified Node  │◄──►│   Secure    │   ║
    ║   │  Low Power  │    │   Tracking    │    │   Routing   │   ║
    ║   └─────────────┘    └───────────────┘    └─────────────┘   ║
    ║                              │                               ║
    ║                      ┌───────┴───────┐                      ║
    ║                      │  Dashboard &  │                      ║
    ║                      │  Diagnostics  │                      ║
    ║                      └───────────────┘                      ║
    ║                                                               ║
    ╚═══════════════════════════════════════════════════════════════╝
```

---

## TL;DR - Quick Start

```bash
# Get it running in 60 seconds
git clone https://github.com/Nursedude/RNS-Meshtastic-Gateway-Tool.git
cd RNS-Meshtastic-Gateway-Tool
pip3 install -r requirements.txt
python3 launcher.py
```

**What does it do?**
- Bridges messages between Meshtastic (LoRa) and Reticulum (RNS) networks
- Tracks all nodes from both networks in one unified view
- Provides RF signal analysis with actionable recommendations
- Runs 18+ diagnostic checks on your system and hardware
- Auto-detects your LoRa hardware (USB, SPI, I2C)

---

## Table of Contents

- [Why This Tool?](#why-this-tool)
- [Features](#features)
- [Real-World Use Cases](#real-world-use-cases)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Usage Guide](#usage-guide)
- [Configuration](#configuration)
- [Hardware Compatibility](#hardware-compatibility)
- [Field Deployment](#field-deployment)
- [Troubleshooting](#troubleshooting)
- [Module Reference](#module-reference)
- [Security](#security)
- [Development](#development)
- [Contributing](#contributing)
- [License](#license)

---

## Why This Tool?

### The Problem

You're running a mesh network. Maybe it's for:
- Emergency communications (EmComm/ARES/RACES)
- Off-grid community connectivity
- Backcountry expeditions
- Event coordination
- Ham radio experimentation

You have **Meshtastic nodes** (cheap, long-range, easy to deploy) AND you want the **security and routing capabilities of Reticulum**. But they don't talk to each other... until now.

### The Solution

This gateway bridges both worlds:

```
┌──────────────────────────────────────────────────────────────────┐
│  BEFORE                          AFTER                           │
│                                                                  │
│  Meshtastic ──X──► Reticulum    Meshtastic ◄═══► Gateway ◄═══► RNS  │
│  (isolated)       (isolated)    (bridged, tracked, monitored)   │
└──────────────────────────────────────────────────────────────────┘
```

---

## Features

### Core Capabilities

| Feature | What It Does | Why It Matters |
|---------|--------------|----------------|
| **Bidirectional Bridge** | Routes messages between networks | One message reaches both networks |
| **Unified Node Tracker** | Single view of all nodes | Know who's online across all systems |
| **Signal Analysis** | Classifies SNR/RSSI quality | Diagnose problems before they fail |
| **18+ Health Checks** | Network, hardware, services | Catch issues early |
| **Hardware Auto-Detect** | Finds USB/SPI/I2C devices | Plug and play setup |
| **LoRa Presets** | Meshtastic-compatible configs | Match your network settings |
| **GeoJSON Export** | Export node positions | Map your network coverage |

### Signal Quality Reference

The signal analyzer classifies RF quality and tells you what to do:

| Quality | SNR | RSSI | What It Means | Action |
|---------|-----|------|---------------|--------|
| **Excellent** | ≥ 10 dB | ≥ -90 dBm | Crystal clear | None needed |
| **Good** | ≥ 0 dB | ≥ -100 dBm | Normal ops | Monitor |
| **Fair** | ≥ -5 dB | ≥ -110 dBm | Marginal | Check antenna |
| **Poor** | ≥ -10 dB | ≥ -120 dBm | Degraded | Improve setup |
| **Critical** | < -10 dB | < -120 dBm | Failing | Immediate fix |

### Diagnostic Categories

```
NETWORK CHECKS          HARDWARE CHECKS         RESOURCE CHECKS
├── Localhost ping      ├── SPI enabled         ├── CPU usage
├── Gateway ping        ├── I2C enabled         ├── Memory available
├── Internet access     ├── GPIO access         ├── Disk space
├── DNS resolution      ├── Serial ports        ├── CPU temperature
└── Meshtastic API      └── LoRa detection      └── Throttle status
```

---

## Real-World Use Cases

### EmComm / Disaster Response

Deploy a gateway at your EOC (Emergency Operations Center) to bridge field teams using Meshtastic handhelds with your secure RNS backbone:

```
Field Team (Meshtastic)          EOC Gateway              Command (RNS)
    [Handheld]  ────►  [RPi + RAK HAT]  ────►  [Secure Server]
    [Handheld]  ◄────  [+ This Tool]   ◄────  [Other Gateways]
    [Handheld]
```

### Off-Grid Community Network

Connect solar-powered Meshtastic nodes with an RNS network for secure messaging:

```
Mountain Repeater ─┐
                   ├──► Central Gateway ──► RNS Cloud
Valley Nodes ──────┘    (RPi + Solar)      (Internet/HF)
```

### Field Day / Public Events

Coordinate volunteers across a large venue:

```
                    ┌── Volunteer A (Meshtastic)
Event Gateway ──────┼── Volunteer B (Meshtastic)
(Laptop + USB)      ├── Volunteer C (Meshtastic)
      │             └── Net Control (RNS App)
      │
      └── Real-time dashboard showing all positions
```

### Backcountry Expedition

Track your team across remote terrain:

```
Base Camp                         Field Teams
┌──────────────┐                  ┌──────────┐
│ RPi Gateway  │◄═══ LoRa ════════│ Handheld │
│ + Solar      │                  └──────────┘
│ + Battery    │◄═══ LoRa ════════┌──────────┐
│              │                  │ Handheld │
│ GeoJSON ─────┼──► Satellite     └──────────┘
│ Export       │    Uplink
└──────────────┘
```

---

## Installation

### Prerequisites

- **Python 3.9+** (check: `python3 --version`)
- **Git** (check: `git --version`)
- **pip** (check: `pip3 --version`)

### Option A: Quick Install (Basic Mode)

Runs with minimal dependencies - good for testing:

```bash
git clone https://github.com/Nursedude/RNS-Meshtastic-Gateway-Tool.git
cd RNS-Meshtastic-Gateway-Tool
python3 launcher.py
```

### Option B: Full Installation (Recommended)

All features enabled:

```bash
git clone https://github.com/Nursedude/RNS-Meshtastic-Gateway-Tool.git
cd RNS-Meshtastic-Gateway-Tool
pip3 install -r requirements.txt
python3 launcher.py
```

### Option C: System-Wide Install

Install as a command-line tool:

```bash
git clone https://github.com/Nursedude/RNS-Meshtastic-Gateway-Tool.git
cd RNS-Meshtastic-Gateway-Tool
pip3 install -e .

# Now run from anywhere:
rns-gateway
```

### Platform-Specific Notes

**Raspberry Pi (Recommended Platform):**
```bash
# Enable SPI and I2C first
sudo raspi-config  # Interface Options → Enable SPI, I2C

# Install
git clone https://github.com/Nursedude/RNS-Meshtastic-Gateway-Tool.git
cd RNS-Meshtastic-Gateway-Tool
pip3 install -r requirements.txt
python3 launcher.py
```

**Windows:**
```powershell
# USB devices work out of the box
git clone https://github.com/Nursedude/RNS-Meshtastic-Gateway-Tool.git
cd RNS-Meshtastic-Gateway-Tool
pip install -r requirements.txt
python launcher.py
```

**Headless / SSH:**
```bash
# Works great over SSH - no GUI required
python3 launcher.py

# Or run specific functions:
python3 launcher.py --status    # Quick status check
python3 launcher.py --daemon    # Run bridge in background
```

---

## Quick Start

### 1. Launch the Tool

```bash
python3 launcher.py
```

### 2. You'll See This Menu

```
============================================================
  RNS-MESHTASTIC GATEWAY TOOL | v2.0.0-Alpha
  MeshForge Integration - Supervisor NOC
============================================================
  [Full Integration Mode]

  MAIN MENU
----------------------------------------
  [1] Quick Status Dashboard
  [2] System Diagnostics
  [3] Signal Analysis
  [4] Gateway Bridge Control
  [5] Node Tracker
  [6] Hardware Configuration
  [7] Radio Settings
  [8] Update Tool
  [0] Exit
----------------------------------------
  Select option:
```

### 3. First Steps

1. **Run Diagnostics** (Option 2) - See what's working
2. **Check Hardware** (Option 6) - Detect your devices
3. **Start Bridge** (Option 4) - Begin bridging networks

---

## Usage Guide

### Command Line Options

```bash
python3 launcher.py [OPTIONS]

Options:
  --version     Show version and exit
  --status      Quick status check (non-interactive)
  --debug       Enable debug logging
  --daemon      Run bridge in background mode
  --help        Show help message
```

### Menu Options Explained

#### [1] Quick Status Dashboard

At-a-glance system health:
```
  SYSTEM STATUS
============================================================
  Health Score: 87%

  Hardware:    [OK] LoRa device detected on /dev/ttyUSB0
  Network:     [OK] Internet connected, gateway reachable
  Services:    [OK] meshtasticd running
  Resources:   [OK] CPU 23%, Memory 45%, Disk 67%
  Temperature: [OK] 52°C (normal)
```

#### [2] System Diagnostics

Deep health check with 18+ tests:
```
  Running comprehensive diagnostics...

  NETWORK
  [+] PASS: Localhost responding
  [+] PASS: Gateway 192.168.1.1 responding
  [+] PASS: Internet accessible
  [-] FAIL: DNS resolution slow (>500ms)

  HARDWARE
  [+] PASS: SPI interface enabled
  [+] PASS: I2C bus 1 available
  [+] PASS: LoRa device on /dev/ttyUSB0

  Results: 16/18 checks passed
  Health: 89%
```

#### [3] Signal Analysis

Enter your signal measurements for analysis:
```
  Enter signal measurements:

  SNR (dB) [-20 to +20]: -3
  RSSI (dBm) [-130 to -50]: -98

  ═══════════════════════════════════════
  Quality: FAIR
  ═══════════════════════════════════════

  Diagnosis:
    SNR -3.0dB is marginal - noise approaching signal level
    RSSI -98.0dBm is acceptable but not ideal

  Recommendations:
    • Raise antenna height if possible
    • Check for nearby interference sources
    • Consider directional antenna for point-to-point links
    • Verify antenna connections are tight
```

#### [4] Gateway Bridge Control

Manage the bidirectional bridge:
```
  GATEWAY BRIDGE CONTROL
============================================================

  Current Status:
  ├── Bridge: RUNNING
  ├── Meshtastic: Connected (localhost:4403)
  ├── RNS: Connected (identity: gateway)
  ├── Messages Bridged: 142
  └── Uptime: 2h 34m 12s

  [1] Start Bridge
  [2] Stop Bridge
  [3] View Traffic Log
  [4] Configure Routing Rules
  [0] Back to Main Menu
```

#### [5] Node Tracker

View all nodes across both networks:
```
  UNIFIED NODE TRACKER
============================================================
  Tracking 7 nodes across 2 networks

  MESHTASTIC NODES (5)
  ──────────────────────────────────────────────────────────
  !a1b2c3d4   "Base-Station"    [ONLINE]   SNR: 8.5dB
              Lat: 21.3099  Lon: -157.8581  Alt: 125m
              Battery: 87%  Last seen: 12s ago

  !e5f6g7h8   "Mobile-Alpha"    [ONLINE]   SNR: 2.1dB
              Lat: 21.3156  Lon: -157.8603  Alt: 45m
              Battery: 62%  Last seen: 45s ago

  RNS NODES (2)
  ──────────────────────────────────────────────────────────
  abc123...   "RNS-Gateway"     [ONLINE]
              Announced: 5m ago  Hops: 0

  [E] Export GeoJSON   [R] Refresh   [0] Back
```

---

## Configuration

### Gateway Configuration File

Located at `~/.config/rns-meshtastic-gateway/gateway.json`:

```json
{
  "meshtastic": {
    "host": "localhost",
    "port": 4403,
    "channel": 0
  },
  "rns": {
    "config_dir": null,
    "identity_name": "gateway",
    "announce_interval": 300
  },
  "bridge_enabled": true,
  "routing_rules": [
    {
      "name": "all_to_rns",
      "direction": "meshtastic_to_rns",
      "pattern": ".*",
      "priority": 10,
      "enabled": true
    },
    {
      "name": "emergency_priority",
      "direction": "both",
      "pattern": "^EMERGENCY:",
      "priority": 1,
      "enabled": true
    }
  ]
}
```

### LoRa Presets

Match your Meshtastic network settings:

| Preset | Bandwidth | SF | Speed | Range | Use Case |
|--------|-----------|----:|------:|------:|----------|
| **SHORT_TURBO** | 500 kHz | 7 | ~12 kbps | ~1 km | Events, dense areas |
| **MEDIUM_FAST** | 250 kHz | 10 | ~2.5 kbps | ~3 km | General use |
| **LONG_FAST** | 250 kHz | 11 | ~1.5 kbps | ~5 km | Default, balanced |
| **LONG_SLOW** | 125 kHz | 12 | ~0.3 kbps | ~10 km | Extended range |
| **VERY_LONG_SLOW** | 62.5 kHz | 12 | ~0.1 kbps | ~15 km | Maximum range |

### Environment Variables

```bash
# Optional configuration via environment
export RNS_GATEWAY_DEBUG=1          # Enable debug mode
export RNS_GATEWAY_CONFIG=/path     # Custom config directory
export MESHTASTIC_HOST=192.168.1.50 # Remote Meshtastic device
```

---

## Hardware Compatibility

### Verified Devices

| Device | Connection | Status | Best For |
|--------|------------|--------|----------|
| **RAK4631** | USB Serial | Verified | Portable gateway |
| **RAK13302 HAT** | SPI/GPIO | Verified | RPi permanent install |
| **T-Beam v1.1+** | USB Serial | Verified | Mobile + GPS |
| **T-Beam S3** | USB Serial | Verified | Latest ESP32-S3 |
| **Heltec V3** | USB Serial | Beta | Budget option |
| **Waveshare HAT** | SPI | Verified | RPi HAT alternative |
| **T-LoRa** | USB Serial | Beta | Basic nodes |

### Recommended Platforms

| Platform | RAM | Status | Notes |
|----------|----:|--------|-------|
| **Raspberry Pi 5** | 4-8 GB | Full Support | Best performance |
| **Raspberry Pi 4** | 2-8 GB | Full Support | Recommended |
| **Raspberry Pi 3B+** | 1 GB | Supported | Works fine |
| **Pi Zero 2W** | 512 MB | Beta | Limited, but works |
| **Ubuntu/Debian x86** | 2+ GB | Full Support | Server deployments |
| **Windows 10/11** | 4+ GB | Supported | USB devices only |

---

## Field Deployment

### Power Considerations

```
POWER BUDGET EXAMPLE (Raspberry Pi 4 + RAK HAT)

Component          Typical     Peak
─────────────────────────────────────
RPi 4              3.0W        6.0W
RAK13302 HAT       0.1W        0.5W (TX)
─────────────────────────────────────
Total              3.1W        6.5W

For 24h operation: 3.1W × 24h = 74.4 Wh
Recommended battery: 100Wh (with margin)
Solar panel: 30W+ for continuous operation
```

### Weatherproofing Checklist

```
□ IP65+ enclosure for outdoor use
□ Proper cable glands for antenna/power
□ Silica gel packets inside enclosure
□ Ventilation if high temperatures expected
□ Lightning arrestor on antenna feedline
□ Grounding for static discharge
```

### Remote Access

```bash
# Set up for headless operation
python3 launcher.py --daemon  # Run in background

# Access via SSH
ssh user@gateway-ip
python3 launcher.py --status  # Quick check

# View logs
tail -f ~/.config/rns-meshtastic-gateway/gateway.log
```

---

## Troubleshooting

### Common Issues

#### "No LoRa device found"

```bash
# Check USB devices
lsusb | grep -i silicon  # Most LoRa devices use Silicon Labs USB

# Check serial ports
ls -la /dev/ttyUSB* /dev/ttyACM*

# Permission issue?
sudo usermod -a -G dialout $USER
# Then log out and back in
```

#### "Cannot connect to Meshtastic API"

```bash
# Is meshtasticd running?
systemctl status meshtasticd

# Check if port is listening
ss -tlnp | grep 4403

# Try connecting manually
meshtastic --host localhost --info
```

#### "SPI not working on Raspberry Pi"

```bash
# Enable SPI
sudo raspi-config
# → Interface Options → SPI → Enable

# Verify
ls /dev/spi*
# Should show: /dev/spidev0.0  /dev/spidev0.1
```

#### "Bridge connects but no messages"

```
Checklist:
□ Both networks using same channel/frequency?
□ Routing rules enabled in config?
□ Nodes within range of gateway?
□ Check signal quality (Option 3)
□ Look at traffic log (Option 4 → View Traffic)
```

### Debug Mode

```bash
# Run with full debug output
python3 launcher.py --debug

# Check the log file
cat ~/.config/rns-meshtastic-gateway/gateway.log
```

### Getting Help

1. Check diagnostics (Option 2) for hardware/network issues
2. Run in debug mode to see detailed logs
3. Open an issue: https://github.com/Nursedude/RNS-Meshtastic-Gateway-Tool/issues

---

## Module Reference

### Python API

#### Gateway Module

```python
from src.gateway import RNSMeshtasticBridge, UnifiedNodeTracker, GatewayConfig

# Load configuration
config = GatewayConfig.load()

# Create components
tracker = UnifiedNodeTracker()
bridge = RNSMeshtasticBridge(config=config, node_tracker=tracker)

# Start bridging
bridge.start()

# Send a message
bridge.send_message("Hello mesh!", destination_network="meshtastic")

# Check status
status = bridge.get_status()
print(f"Bridged: {status['messages_bridged']} messages")
print(f"Uptime: {status['uptime']}s")

# Export node positions
geojson = tracker.to_geojson()
with open("nodes.geojson", "w") as f:
    f.write(geojson)

# Cleanup
bridge.stop()
```

#### Diagnostics Module

```python
from src.diagnostics import SystemDiagnostics, SignalAnalyzer

# Run full diagnostics
diag = SystemDiagnostics()
report = diag.run_full_diagnostics()

print(f"Health: {report['summary']['health_percentage']:.0f}%")
print(f"Passed: {report['summary']['passed']}/{report['summary']['total']}")

for check in report['results']:
    status = "[+]" if check['passed'] else "[-]"
    print(f"{status} {check['name']}: {check['message']}")

# Analyze signal quality
analyzer = SignalAnalyzer()
result = analyzer.analyze(snr=-5, rssi=-95)

print(f"Quality: {result.quality.value}")
print(f"Diagnosis: {result.diagnosis}")
for rec in result.recommendations:
    print(f"  • {rec}")
```

#### Configuration Module

```python
from src.config import HardwareDetector, LoRaConfig, RadioConfig

# Detect hardware
detector = HardwareDetector()
summary = detector.get_device_summary()
print(f"Found {summary['total_devices']} devices")

for device in summary['devices']:
    print(f"  {device['path']}: {device['description']}")

# Work with LoRa settings
lora = LoRaConfig.from_preset("LONG_FAST")
print(f"Bandwidth: {lora.bandwidth_hz / 1000:.0f} kHz")
print(f"Spreading Factor: {lora.spreading_factor}")
print(f"Data Rate: {lora.data_rate_bps:.0f} bps")
print(f"Range (rural): {lora.estimate_range_km('rural'):.1f} km")
print(f"Airtime (32 bytes): {lora.calculate_airtime_ms(32):.1f} ms")
```

---

## Security

### Design Principles

- **No shell injection**: All subprocess calls use `shell=False`
- **Input validation**: Hostnames, service names, and paths are validated
- **Secure permissions**: Config files created with 0600 permissions
- **No hardcoded secrets**: Credentials stored in user config directory

### What We Protect Against

```
✓ Command injection via user input
✓ Path traversal attacks
✓ Service name injection
✓ Malformed host/IP addresses
✓ Sensitive data in logs (filtered)
```

### Security Review

The codebase has been reviewed for:
- OWASP Top 10 vulnerabilities
- Python-specific security issues
- Subprocess execution safety
- File operation security

---

## Development

### Running Tests

```bash
python3 test_suite.py
```

Expected output:
```
============================================================
  RNS-MESHTASTIC GATEWAY TOOL - TEST SUITE
============================================================

  [+] PASS: Basic Imports
  [+] PASS: Src Package Imports
  [+] PASS: Version Format
  [+] PASS: DiagnosticEngine Init
  [+] PASS: Signal Analyzer
  [+] PASS: Node Tracker
  [+] PASS: Gateway Config
  [+] PASS: LoRa Config
  [+] PASS: Radio Config
  [+] PASS: System Utils Security
  ...

  RESULTS: 14/14 tests passed
============================================================
```

### Project Architecture

```
RNS-Meshtastic-Gateway-Tool/
├── launcher.py              # CLI entry point
├── version.py               # Version management
├── test_suite.py            # Test suite
│
└── src/                     # Core modules
    ├── gateway/             # Bridge & tracking
    │   ├── rns_bridge.py    # Bidirectional bridge
    │   ├── node_tracker.py  # Unified node tracking
    │   └── config.py        # Gateway config
    │
    ├── diagnostics/         # Health & analysis
    │   ├── system_diagnostics.py
    │   └── signal_analysis.py
    │
    ├── config/              # Hardware & radio
    │   ├── hardware.py      # Device detection
    │   ├── radio.py         # Radio settings
    │   └── lora.py          # LoRa presets
    │
    ├── monitoring/          # Real-time status
    │   ├── node_monitor.py
    │   └── dashboard.py
    │
    └── utils/               # Shared utilities
        ├── logger.py
        ├── system.py
        └── config.py
```

### MeshForge Integration

This tool integrates with [MeshForge](https://github.com/Nursedude/meshforge). To sync upstream changes:

```bash
git remote add meshforge https://github.com/Nursedude/meshforge.git
git fetch meshforge
git merge meshforge/main --allow-unrelated-histories
```

---

## Contributing

Contributions welcome in the spirit of Aloha!

### How to Contribute

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Make your changes
4. Run tests (`python3 test_suite.py`)
5. Commit (`git commit -m 'Add my feature'`)
6. Push (`git push origin feature/my-feature`)
7. Open a Pull Request

### Code Style

- Follow PEP 8
- Add docstrings to functions and classes
- Include type hints
- Write tests for new features
- Keep security in mind

---

## License

This project is licensed under the GPL-3.0 License - see the [LICENSE](LICENSE) file for details.

---

## Acknowledgments

- [Meshtastic](https://meshtastic.org/) - LoRa mesh networking made accessible
- [Reticulum Network Stack](https://reticulum.network/) - Cryptographically secure networking
- [MeshForge](https://github.com/Nursedude/meshforge) - Core integration framework
- The ham radio and mesh networking communities worldwide

---

<div align="center">

**73 de WH6GXZ & the mesh networking community**

*Built with Aloha in Hawaii*

</div>
