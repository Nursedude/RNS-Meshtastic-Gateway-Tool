# RNS-Meshtastic Gateway Tool: Persistent Issues & Session Memory

> **Purpose**: Durable context for Claude Code sessions. Read this first.
> **Last updated**: 2026-04-16

---

## Project Identity

- **Repo**: nursedude/rns-meshtastic-gateway-tool
- **Author**: WH6GXZ (Nursedude)
- **What it does**: Bridges Reticulum (RNS) with Meshtastic LoRa radios
- **Status**: Alpha, functional, under active testing
- **Relationship to MeshForge**: Standalone tool. MeshForge (`/opt/meshforge`) has its own integrated gateway. They share concepts but are independent codebases. Features proven here may be ported to MeshForge.

---

## Architecture Quick Reference

```
launcher.py          Entry point — selects direct or MQTT bridge mode
src/daemon.py        Daemon with PID locking (fcntl.flock), watchdog, systemd
src/Meshtastic_Interface.py   Direct serial/TCP driver (RNS Interface subclass)
src/mqtt_bridge.py   MQTT bridge mode (zero-interference with meshtasticd)
src/monitoring/web_dashboard.py   Flask dashboard (localhost only, no auth)
src/utils/
  common.py          Config loading, validation, path constants
  circuit_breaker.py 3-state breaker (CLOSED/OPEN/HALF_OPEN)
  health_probe.py    Active health probing with hysteresis
  bridge_health.py   Error classification, rolling event windows
  message_queue.py   SQLite-backed persistent queue with retry
  tx_queue.py        In-memory TX queue (simpler alternative)
  node_tracker.py    Mesh node registry with JSON persistence
  event_bus.py       Thread-safe pub/sub (bounded ThreadPoolExecutor)
  reconnect.py       Exponential backoff with jitter
  timeouts.py        ALL timeout constants (single source of truth)
  log.py             Centralized logging with rotation
  service_check.py   System service detection
  threads.py         Thread lifecycle manager
```

---

## Critical Rules (Do Not Violate)

### 1. No shell=True in subprocess
All subprocess calls MUST use list arguments. No `os.system()`. No `eval()`/`exec()`.

### 2. No bare `except Exception: pass`
Use specific exception types. Event bus calls use `except (ImportError, AttributeError)`.

### 3. Timeouts are centralized
ALL timeout values live in `src/utils/timeouts.py`. Never hardcode magic numbers.

### 4. Config validation before use
Always validate hostnames (`validate_hostname()`), ports (`validate_port()`), and
config structure (`validate_config()`) before using values from `config.json`.

### 5. File permissions
Data directory `~/.config/rns-gateway/` must be `0o700`.
PID file, nodes.json written with `0o600` via `os.open()`.

### 6. MQTT credentials via environment variables
Never require credentials in `config.json`. Support `GATEWAY_MQTT_USERNAME` and
`GATEWAY_MQTT_PASSWORD` env vars. Warn on non-localhost without TLS.

### 7. No innerHTML in dashboard
Dashboard JS uses DOM API (`createElement`/`textContent`) — never `innerHTML`.

---

## Known Gotchas

### Meshtastic single-client TCP limitation
meshtasticd only supports ONE TCP client at a time. If the gateway holds a TCP
connection, the Meshtastic web UI will disconnect. MQTT bridge mode (`bridge_mode: mqtt`)
avoids this entirely — it uses MQTT for RX and HTTP POST for TX.

### RNS Interface compliance
`MeshtasticInterface` and `MqttBridge` must expose all attributes that RNS core
reads: `owner`, `name`, `online`, `IN`, `OUT`, `bitrate`, `rxb`, `txb`,
`rx_packets`, `tx_packets`, `detached`, `ingress_control`, `held_announces`,
`rate_violation_occurred`, `clients`, `ia_freq_deque`, `oa_freq_deque`,
`announce_cap`, `ifac_identity`, `mode`. Removing ANY causes AttributeError at runtime.

### Circuit breaker resets on reconnect
When `reconnect()` is called, the circuit breaker is explicitly reset so the
fresh connection gets a clean slate. This is intentional.

### Message queue vs TX queue
`features.message_queue` (SQLite-backed, persistent, retry with backoff) subsumes
`features.tx_queue` (in-memory, no retry). Enabling both is redundant — config
validation warns about this.

### Serial port auto-detection
`_default_serial_port()` picks the first available serial port. On multi-radio
systems, this may pick the wrong device. Always set `gateway.port` explicitly.

### Flask dashboard is read-only
No write operations, no CSRF needed yet. If write ops are added, CSRF must be added.
Dashboard binds to `127.0.0.1` by default — warn loudly if overridden to `0.0.0.0`.

---

## Security Review History

35 findings tracked in `docs/SECURITY.md`:

| Version | Findings | Key improvements |
|---------|----------|-----------------|
| v1.0 | S-01 to S-11 | Basic hardening, dependency pinning |
| v1.2 | S-12 to S-21 | Input validation, hostname checks, MeshForge patterns |
| v1.3 | S-22 to S-35 | MQTT TLS/auth, XSS fix, SSRF prevention, PID locking, file permissions, supply-chain hash pinning |

---

## Test Suite

- **495 tests** across 23 test files
- Run: `python -m pytest tests/ -v --timeout=30`
- All tests must pass before committing
- Flask dashboard tests require `flask` to be installed (skip gracefully if missing)

---

## MeshForge Patterns Already Adopted

These patterns were ported from MeshForge and should be maintained:

1. **Circuit breaker** — 3-state with configurable threshold
2. **Health probe** — Hysteresis (3 consecutive failures before UNHEALTHY)
3. **Bridge health monitor** — Error classification (transient vs permanent)
4. **Reconnect strategy** — Exponential backoff with jitter
5. **Slow-start recovery** — Inter-packet delay after reconnect
6. **Event bus** — Bounded ThreadPoolExecutor (4 workers)
7. **Centralized timeouts** — Single source of truth
8. **Config validation** — Structured errors with severity levels
9. **Persistent message queue** — SQLite + WAL + dedup + dead letter
10. **Node tracker** — JSON persistence with stale cleanup

---

## Development Checklist

Before committing, verify:

- [ ] `python -m pytest tests/ -v --timeout=30` — all pass
- [ ] No `shell=True` in subprocess calls
- [ ] No bare `except Exception: pass`
- [ ] Timeouts from `src/utils/timeouts.py`, not hardcoded
- [ ] Config values validated before use
- [ ] Sensitive files written with restrictive permissions
- [ ] No `innerHTML` in dashboard JavaScript
- [ ] MQTT credentials support env vars, not just config
