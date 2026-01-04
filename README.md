# RNS-Meshtastic Gateway Tool

[![Version](https://img.shields.io/badge/version-2.0.0--Alpha-blue.svg)](https://github.com/Nursedude/RNS-Meshtastic-Gateway-Tool)
[![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20Raspberry%20Pi%20%7C%20Windows-green.svg)](#installation)
[![License](https://img.shields.io/badge/license-GPL--3.0-orange.svg)](LICENSE)
[![MeshForge](https://img.shields.io/badge/MeshForge-Integrated-purple.svg)](https://github.com/Nursedude/meshforge)

A comprehensive network operations suite bridging **Reticulum Network Stack (RNS)** and **Meshtastic** mesh networks. Built with MeshForge integration for unified node tracking, AI-augmented diagnostics, and bidirectional message bridging.

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Usage](#usage)
- [Configuration](#configuration)
- [Hardware Compatibility](#hardware-compatibility)
- [Module Reference](#module-reference)
- [Security](#security)
- [Development](#development)
- [Contributing](#contributing)
- [License](#license)

---

## Overview

The RNS-Meshtastic Gateway Tool serves as a **Supervisor NOC (Network Operations Center)** for managing heterogeneous mesh networks. It bridges two powerful mesh networking systems:

- **Meshtastic**: LoRa-based mesh networking for long-range, low-power communication
- **Reticulum (RNS)**: Cryptographically secure, vendor-neutral networking stack

This tool enables:
- Bidirectional message bridging between networks
- Unified node tracking across both systems
- Real-time RF signal analysis and diagnostics
- Hardware auto-detection and configuration
- Comprehensive system health monitoring

---

## Features

### Core Capabilities

| Feature | Description |
|---------|-------------|
| **RNS-Meshtastic Bridge** | Bidirectional message routing with configurable rules |
| **Unified Node Tracker** | Track nodes across both networks with position/telemetry |
| **Signal Analysis** | AI-augmented SNR/RSSI analysis with recommendations |
| **System Diagnostics** | 18+ health checks (network, hardware, services) |
| **Hardware Detection** | Auto-detect LoRa devices (USB, SPI, I2C) |
| **LoRa Configuration** | Meshtastic-compatible presets with airtime calculations |
| **Real-time Dashboard** | Status monitoring with health scoring |
| **GeoJSON Export** | Export node positions for mapping |

### Signal Analysis

The signal analyzer classifies RF quality and provides actionable recommendations:

| Quality | SNR (dB) | RSSI (dBm) | Status |
|---------|----------|------------|--------|
| Excellent | ≥ 10 | ≥ -90 | Optimal performance |
| Good | ≥ 0 | ≥ -100 | Normal operation |
| Fair | ≥ -5 | ≥ -110 | Monitor for degradation |
| Poor | ≥ -10 | ≥ -120 | Consider improvements |
| Critical | < -10 | < -120 | Immediate attention needed |

### System Diagnostics

Comprehensive health checks include:
- Network: localhost, gateway, internet, DNS, Meshtastic API
- Hardware: SPI, I2C, GPIO, serial ports, LoRa detection
- Services: meshtasticd status, configuration validation
- Resources: CPU, memory, disk, temperature, throttling

---

## Architecture

```
RNS-Meshtastic-Gateway-Tool/
├── launcher.py              # Main entry point & CLI menu
├── version.py               # Version management
├── ai_methods.py            # Legacy diagnostic engine
├── git_manager.py           # Self-update functionality
├── requirements.txt         # Python dependencies
├── setup.py                 # Package installation
├── test_suite.py            # Comprehensive tests
│
└── src/                     # MeshForge integrated modules
    ├── __init__.py
    │
    ├── gateway/             # RNS-Meshtastic bridging
    │   ├── rns_bridge.py    # Bidirectional message bridge
    │   ├── node_tracker.py  # Unified node tracking
    │   └── config.py        # Gateway configuration
    │
    ├── diagnostics/         # System analysis
    │   ├── system_diagnostics.py  # Health checks
    │   └── signal_analysis.py     # RF signal analysis
    │
    ├── config/              # Hardware & radio settings
    │   ├── hardware.py      # Device detection
    │   ├── radio.py         # Radio configuration
    │   └── lora.py          # LoRa parameters & presets
    │
    ├── monitoring/          # Real-time monitoring
    │   ├── node_monitor.py  # Node status tracking
    │   └── dashboard.py     # Status dashboard
    │
    └── utils/               # Shared utilities
        ├── logger.py        # Logging system
        ├── system.py        # OS utilities
        └── config.py        # Configuration management
```

---

## Installation

### Prerequisites

- Python 3.9 or higher
- Git
- pip package manager

### Option A: Quick Install (Basic Mode)

Works without additional dependencies:

```bash
# Clone the repository
git clone https://github.com/Nursedude/RNS-Meshtastic-Gateway-Tool.git
cd RNS-Meshtastic-Gateway-Tool

# Run directly
python3 launcher.py
```

### Option B: Full Installation

Enables all features:

```bash
# Clone the repository
git clone https://github.com/Nursedude/RNS-Meshtastic-Gateway-Tool.git
cd RNS-Meshtastic-Gateway-Tool

# Install dependencies
pip3 install -r requirements.txt

# Run with full integration
python3 launcher.py
```

### Option C: Package Installation

```bash
# Clone and install as package
git clone https://github.com/Nursedude/RNS-Meshtastic-Gateway-Tool.git
cd RNS-Meshtastic-Gateway-Tool
pip3 install -e .

# Run via command
rns-gateway
```

### Platform-Specific

**Raspberry Pi:**
```bash
chmod +x install_pi.sh
./install_pi.sh
python3 launcher.py
```

**Windows:**
```powershell
.\install_win.ps1
python launcher.py
```

---

## Quick Start

### 1. Launch the Tool

```bash
python3 launcher.py
```

### 2. Main Menu

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
```

### 3. Run Diagnostics

Select option `2` to run comprehensive system diagnostics:

```
  Running comprehensive diagnostics...

  Results: 15/18 checks passed
  Health: 83%

  [+] Localhost Ping: Localhost responding
  [+] Gateway Ping: Gateway 192.168.1.1 responding
  [+] Internet Connectivity: Internet accessible
  [+] Meshtastic API: Connected to localhost:4403
  [+] SPI Interface: SPI enabled
  ...
```

---

## Usage

### Command Line Options

```bash
# Show version
python3 launcher.py --version

# Quick status check
python3 launcher.py --status

# Enable debug logging
python3 launcher.py --debug

# Run bridge in daemon mode
python3 launcher.py --daemon
```

### Signal Analysis

Analyze RF signal quality interactively:

```
  Enter signal measurements:

  SNR (dB) [-20 to +20]: -8
  RSSI (dBm) [-130 to -50]: -105

  Quality: POOR
  Diagnosis: WARNING: Elevated noise levels (SNR: -8.0dB) | RSSI: -105.0dBm (fair)

  Recommendations:
    - Check antenna connections and cabling for damage
    - Move antenna away from sources of RF interference
    - Consider using a bandpass filter to reduce noise
```

### Node Tracking

Track nodes across both networks:

```
  Tracked Nodes (5):
--------------------------------------------------
  meshtastic_!a1b2c3d4  Node-Alpha      [Online]
  meshtastic_!e5f6g7h8  Base-Station    [Online]
  rns_abc123def456      RNS-Gateway     [Online]
  meshtastic_!i9j0k1l2  Mobile-Unit     [Offline]
```

### Bridge Control

Start the bidirectional bridge:

```
  GATEWAY BRIDGE CONTROL
============================================================

  [1] Start Bridge
  [2] Stop Bridge
  [3] View Bridge Status
  [4] Configure Bridge
  [0] Back to Main Menu

  Bridge Status:
  Running: True
  Meshtastic: Connected
  RNS: Connected
  Messages Bridged: 47
  Uptime: 3600s
```

---

## Configuration

### Gateway Configuration

Configuration is stored in `~/.config/rns-meshtastic-gateway/gateway.json`:

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
      "name": "broadcast_to_rns",
      "direction": "meshtastic_to_rns",
      "pattern": ".*",
      "priority": 10,
      "enabled": true
    }
  ]
}
```

### LoRa Presets

Available Meshtastic-compatible presets:

| Preset | Bandwidth | SF | Data Rate | Range |
|--------|-----------|----|-----------| ------|
| LONG_FAST | 250 kHz | 11 | ~1.5 kbps | ~5 km |
| LONG_SLOW | 125 kHz | 12 | ~0.3 kbps | ~10 km |
| VERY_LONG_SLOW | 62.5 kHz | 12 | ~0.1 kbps | ~15 km |
| MEDIUM_FAST | 250 kHz | 10 | ~2.5 kbps | ~3 km |
| SHORT_TURBO | 500 kHz | 7 | ~12 kbps | ~1 km |

---

## Hardware Compatibility

### Verified Devices

| Device | Connection | Status | Notes |
|--------|------------|--------|-------|
| **RAK4631** | USB Serial | ✅ Verified | nRF52840 based |
| **RAK13302** | SPI/GPIO | ✅ Verified | Raspberry Pi HAT |
| **T-Beam** | USB Serial | ✅ Verified | ESP32 + GPS |
| **T-Beam S3** | USB Serial | ✅ Verified | ESP32-S3 |
| **Heltec V3** | USB Serial | ⚠️ Beta | ESP32-S3 |
| **T-LoRa** | USB Serial | ⚠️ Beta | ESP32 based |
| **Waveshare HAT** | SPI | ✅ Verified | Raspberry Pi HAT |

### Supported Platforms

| Platform | Status | Notes |
|----------|--------|-------|
| Raspberry Pi 4/5 | ✅ Full Support | Recommended |
| Raspberry Pi 3 | ✅ Supported | 32-bit or 64-bit |
| Raspberry Pi Zero 2W | ⚠️ Beta | Limited resources |
| Ubuntu/Debian | ✅ Full Support | x86_64 or ARM |
| Windows 10/11 | ✅ Supported | USB devices only |

---

## Module Reference

### Gateway Module

```python
from src.gateway import RNSMeshtasticBridge, UnifiedNodeTracker, GatewayConfig

# Load configuration
config = GatewayConfig.load()

# Create node tracker
tracker = UnifiedNodeTracker()

# Create and start bridge
bridge = RNSMeshtasticBridge(config=config, node_tracker=tracker)
bridge.start()

# Send a message
bridge.send_message("Hello mesh!", destination_network="meshtastic")

# Get status
status = bridge.get_status()
print(f"Messages bridged: {status['messages_bridged']}")

# Stop bridge
bridge.stop()
```

### Diagnostics Module

```python
from src.diagnostics import SystemDiagnostics, SignalAnalyzer

# Run system diagnostics
diag = SystemDiagnostics()
report = diag.run_full_diagnostics()
print(f"Health: {report['summary']['health_percentage']:.0f}%")

# Analyze signal
analyzer = SignalAnalyzer()
result = analyzer.analyze(snr=-5, rssi=-95)
print(f"Quality: {result.quality.value}")
print(f"Diagnosis: {result.diagnosis}")
for rec in result.recommendations:
    print(f"  - {rec}")
```

### Configuration Module

```python
from src.config import HardwareDetector, LoRaConfig, RadioConfig

# Detect hardware
detector = HardwareDetector()
summary = detector.get_device_summary()
print(f"Devices found: {summary['total_devices']}")

# Load LoRa preset
lora = LoRaConfig.from_preset("LONG_FAST")
print(f"Data rate: {lora.data_rate_bps:.0f} bps")
print(f"Estimated range: {lora.estimate_range_km('rural'):.1f} km")
print(f"Airtime (32 bytes): {lora.calculate_airtime_ms(32):.1f} ms")
```

---

## Security

### Design Principles

- **No shell injection**: All subprocess calls use `shell=False` with argument lists
- **Input validation**: Host names, service names, and paths are validated
- **Secure defaults**: Configuration files created with restrictive permissions (0600)
- **No hardcoded secrets**: Credentials stored in user config directory

### Security Review

The codebase has undergone security review covering:
- Command injection prevention
- Path traversal protection
- Input sanitization
- Secure file operations

---

## Development

### Running Tests

```bash
# Run full test suite
python3 test_suite.py

# Expected output
============================================================
  RNS-MESHTASTIC GATEWAY TOOL - TEST SUITE
============================================================
  RESULTS: 14/14 tests passed
============================================================
```

### Project Structure

```
Tests cover:
- Basic imports and version
- AI diagnostic engine
- Signal analyzer classification
- Node tracker operations
- Gateway configuration
- LoRa/Radio configuration
- Security validation (input sanitization)
```

### MeshForge Sync

This tool integrates with [MeshForge](https://github.com/Nursedude/meshforge). To sync updates:

```bash
# Add MeshForge as upstream
git remote add meshforge https://github.com/Nursedude/meshforge.git

# Fetch and merge updates
git fetch meshforge
git merge meshforge/main --allow-unrelated-histories
```

---

## Contributing

Contributions welcome in the spirit of Aloha!

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Code Style

- Follow PEP 8 guidelines
- Add docstrings to functions and classes
- Include type hints
- Write tests for new features

---

## License

This project is licensed under the GPL-3.0 License - see the [LICENSE](LICENSE) file for details.

---

## Acknowledgments

- [Meshtastic](https://meshtastic.org/) - LoRa mesh networking
- [Reticulum Network Stack](https://reticulum.network/) - Cryptographic networking
- [MeshForge](https://github.com/Nursedude/meshforge) - Core integration framework

---

**73 de the mesh networking community**
