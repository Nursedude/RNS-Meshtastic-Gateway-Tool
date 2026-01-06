# Supervisor NOC: RNS & Meshtastic Gateway
**Status:** Alpha / Functional
**Date:** 2026-01-05

## Overview
This tool bridges the **Reticulum Network Stack (RNS)** with **Meshtastic LoRa radios**. It allows RNS traffic ( LXMF messages, Sideband, etc.) to ride over LoRa hardware using the Meshtastic Python API.

## Architecture
* **Launcher (`launcher.py`):** The main entry point. Initializes RNS and loads drivers.
* **Driver (`src/Meshtastic_Interface.py`):** Custom driver that translates RNS packets into Meshtastic `sendData()` calls.
* **Config:** Uses standard `.reticulum` config files.

## How to Run
1.  **Connect Radio:** Ensure Meshtastic device is on `COM3` via USB.
2.  **Start Gateway:** Double-click `start_gateway.bat`.
3.  **Verify:** Look for `[Meshtastic Radio] Hardware Connected Successfully`.

## Troubleshooting
* **No Red LED?** Check `ingress_control` in driver.
* **Crash on Start?** Verify `RNS.Interfaces.Interface` inheritance.
* **Stuck on "Waiting"?** Run `python broadcast.py` to force a test packet.

## Roadmap
* [x] Basic Transmit (TX)
* [x] Basic Receive (RX)
* [ ] Multi-node testing
* [ ] Packet acknowledgement handling