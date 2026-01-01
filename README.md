# 🛰️ RNS & Meshtastic Gateway - Supervisor NOC
[![Version](https://img.shields.io/badge/version-1.2.0--Alpha-blue.svg)](https://github.com/Nursedude/RNS-Meshtastic-Gateway-Tool)
[![Platform](https://img.shields.io/badge/platform-Windows%2011%20%7C%20Raspberry%20Pi-green.svg)](#-installation)
[![License](https://img.shields.io/badge/license-MIT-orange.svg)](LICENSE)
[![Maintenance](https://img.shields.io/badge/contributions-Aloha-ff69b4.svg)](#-contributing-with-aloha)

The **Supervisor NOC** is an AI-augmented management suite designed to bridge **Reticulum Network Stack (RNS)** and **Meshtastic**.

---

## 🚀 Key Features
* **🤖 AI Diagnostics:** Real-time analysis of Signal-to-Noise Ratio (SNR).
* **🔄 Global Roadmap Sync:** Self-updating via `git_manager.py`.
* **🛠️ Modular Architecture:** Windows 11 & Raspberry Pi support.

---

## 📡 Hardware Compatibility

| Device | Connection | Support Status |
| :--- | :--- | :--- |
| **RAK4631** | USB Serial | ✅ Verified |
| **RAK13302** | SPI / GPIO | ✅ Verified |
| **T-Beam** | USB Serial | ✅ Verified |
| **Heltec V3** | USB Serial | ⚠️ Beta |

---

## 📦 Installation

### Option A: Windows 11
1. `git clone https://github.com/Nursedude/RNS-Meshtastic-Gateway-Tool.git`
2. `cd RNS-Meshtastic-Gateway-Tool`
3. `./install_win.ps1`
4. `python launcher.py`

### Option B: Raspberry Pi
1. `git clone https://github.com/Nursedude/RNS-Meshtastic-Gateway-Tool.git`
2. `chmod +x install_pi.sh`
3. `./install_pi.sh`
4. `python3 launcher.py`

---

## 🌺 Contributing with Aloha
We welcome contributions from the community in the spirit of Aloha!
