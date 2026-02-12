# Session Notes: Fix meshtasticd HTTP API Connections
**Date:** 2026-02-12
**Branch:** `claude/fix-meshtasticd-http-api-SFNki`
**Status:** Research & Analysis Complete — Ready for Implementation

---

## 1. Problem Statement

The RNS-Meshtastic-Gateway-Tool currently connects to Meshtastic hardware via **serial/USB only** (`meshtastic.serial_interface.SerialInterface`). It has no support for connecting through meshtasticd's HTTP API. This limits deployment to hosts with direct USB access to the radio.

The MeshForge repo (`Nursedude/MeshForge`) has solved this with a mature multi-path architecture. The task is to port the relevant HTTP API connection capability into this Gateway Tool.

## 2. Current Gateway Tool Architecture

**File:** `src/Meshtastic_Interface.py` (133 lines)
- Inherits from `RNS.Interfaces.Interface`
- Serial-only: `meshtastic.serial_interface.SerialInterface(self.port)`
- Pub/sub for RX: `meshtastic.pub.subscribe(self.on_receive, "meshtastic.receive.data")`
- Broadcast TX: `self.interface.sendData(data, destinationId='^all')`
- Config via `config.json` — only has `port` (COM3), `bitrate`, dashboard settings

**File:** `launcher.py` (54 lines)
- Initializes RNS, creates `MeshtasticInterface`, keeps alive

## 3. MeshForge HTTP API Architecture (What to Port)

### 3a. The Core Problem: meshtasticd Single-Client TCP Limitation
- meshtasticd's TCP port (4403) allows **only ONE client** at a time
- Firmware enforces: "Only one TCP client allowed at a time"
- Competing apps (CLI, web client, scripts) cause connection refusals, stuck messages, missing nodes

### 3b. MeshForge's Solution: Dual-Path Architecture
```
Path 1 (Exclusive): TCP:4403 → Gateway Bridge → RNS → WebSocket:5001
Path 2 (Multi-consumer): MQTT → mosquitto → multiple subscribers
```

### 3c. Key MeshForge Files Analyzed

| File | Purpose | Key Details |
|------|---------|-------------|
| `src/gateway/meshtastic_protobuf_client.py` | HTTP protobuf transport | PUT `/api/v1/toradio`, GET `/api/v1/fromradio` on port 9443; SSL support; session mgmt; async polling |
| `src/gateway/meshtastic_handler.py` | Connection management | Singleton connection manager; auto-reconnect with exponential backoff; pub/sub RX; CLI fallback TX |
| `src/gateway/mqtt_bridge_handler.py` | MQTT-based bridge (recommended) | RX via MQTT subscription; TX via HTTP `/api/v1/toradio`; zero TCP contention; deduplication |
| `src/gateway/meshtastic_api_proxy.py` | HTTP multiplexer (DEPRECATED v0.5.0) | Was: Browser(s) ↔ Proxy(:5000) ↔ meshtasticd(:9443); replaced by MQTT approach |
| `src/gateway/circuit_breaker.py` | Connection resilience | 3-state (CLOSED/OPEN/HALF_OPEN); per-destination; configurable thresholds |
| `src/gateway/config.py` | Configuration | `MeshtasticConfig` dataclass: host, port, channel, use_mqtt, mqtt_topic, preset |
| `.claude/research/meshtasticd_port_conflicts.md` | Issue documentation | Root cause analysis of TCP single-client problem |

### 3d. MeshForge's Recommended Pattern (v0.5.4+)
> "The gateway no longer holds a persistent TCP:4403 connection. It receives via MQTT subscription and sends via transient CLI commands."

**For our use case (RNS bridge), the simplest viable path is:**
- **RX**: Use `meshtastic.tcp_interface.TCPInterface` (like the existing serial path but over TCP)
- **TX**: Same interface, `sendData()` works identically
- **Alternative**: HTTP protobuf client for TX if TCP contention is an issue

## 4. Implementation Plan for Next Session

### Phase 1: Add TCP/HTTP Connection Mode (Minimum Viable)
1. **Modify `src/Meshtastic_Interface.py`** to support connection modes:
   - `serial` (current behavior, default)
   - `tcp` (connect via `meshtastic.tcp_interface.TCPInterface(hostname, portNumber)`)
   - Add conditional import for `meshtastic.tcp_interface`
2. **Update `config.json.example`** to include:
   ```json
   "gateway": {
       "connection_type": "serial",
       "port": "COM3",
       "host": "localhost",
       "tcp_port": 4403,
       "bitrate": 500
   }
   ```
3. **Update `launcher.py`** to pass config to the interface

### Phase 2: Add HTTP Protobuf Transport (Resilient TX)
4. Port `MeshtasticProtobufClient` concept for `/api/v1/toradio` endpoint
5. Use HTTP for TX to avoid TCP single-client contention
6. Keep TCP or MQTT for RX

### Phase 3: Connection Resilience
7. Add basic circuit breaker or retry logic
8. Auto-reconnect with exponential backoff
9. Graceful fallback: TCP → HTTP → CLI

### Phase 4: MQTT Bridge Mode (Full MeshForge Parity)
10. Add MQTT subscription for RX (zero-interference)
11. Add HTTP protobuf for TX
12. Full config support for MQTT topic, broker, auth

## 5. Key Risks & Decisions Needed

| Decision | Options | Recommendation |
|----------|---------|----------------|
| Minimum scope for this branch | TCP only vs TCP+HTTP vs full MQTT | Start with TCP mode (Phase 1) — smallest useful change |
| meshtasticd SSL certs | Verify vs skip verification | Skip verification for self-signed (match MeshForge) |
| Config format | Extend existing JSON vs new section | Extend existing `gateway` section |
| Backwards compatibility | Keep serial as default | Yes — `connection_type: "serial"` is default |

## 6. Files That Will Change

- `src/Meshtastic_Interface.py` — Add TCP/HTTP connection modes
- `config.json.example` — Add connection_type, host, tcp_port fields
- `launcher.py` — Load and pass expanded config
- `docs/KNOWLEDGE_BASE.md` — Document TCP single-client issue and workarounds
- `requirements.txt` — May need `requests` for HTTP protobuf path

## 7. Reference Links

- MeshForge repo: `https://github.com/Nursedude/MeshForge`
- Port conflicts research: `.claude/research/meshtasticd_port_conflicts.md` in MeshForge
- Architecture audit: `.claude/session_notes/2026-02-03_meshtasticd_architecture_audit.md` in MeshForge
- meshtasticd HTTP API: port 9443, endpoints `/api/v1/toradio` (PUT) and `/api/v1/fromradio` (GET)
- meshtasticd TCP API: port 4403 (single client only)

---
**Session Status:** Research complete. No code changes made. Branch is clean at `3b7908d` (same as origin/main).
**Next Session:** Begin Phase 1 implementation — add TCP connection mode to `Meshtastic_Interface.py`.
