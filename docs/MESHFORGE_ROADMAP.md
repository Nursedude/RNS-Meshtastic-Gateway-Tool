# MeshForge → RNS-Meshtastic-Gateway-Tool: Feature & Reliability Roadmap

## Context

MeshForge (Nursedude/meshforge) has evolved significantly since the last round of improvements were ported to RNS-Meshtastic-Gateway-Tool. This roadmap tracks the porting of meaningful features and reliability patterns across 4 sessions, prioritized by impact and dependency order.

**Current state of Gateway Tool:** v1.5+ with circuit breaker, TX queue, reconnect strategy, slow-start recovery, bridge health monitor, active health probe, thread manager, structured logging, TUI, web dashboard, centralized timeouts, event bus, enhanced config validation, and comprehensive test suite (19 test files).

**Completed:** Session 1 — Foundation Layer (commit `dc1e7d7`)
**Remaining gaps vs MeshForge:** No persistent message queue, no daemon/systemd mode, no MQTT bridge mode, no node tracking.

---

## Session 1: Foundation Layer — COMPLETED

> Delivered in commit `dc1e7d7`. Quick-win infrastructure that later sessions depend on.

### What Was Delivered

- **Centralized Timeout Constants** (`src/utils/timeouts.py`) — Replaced scattered magic numbers with named constants (`HEALTH_CHECK_INTERVAL`, `SUBPROCESS_QUICK`, `SUBPROCESS_DEFAULT`, `TCP_CONNECT`, `TCP_PREFLIGHT`, `CIRCUIT_RECOVERY`, `CIRCUIT_FAILURE_THRESHOLD`, `RECONNECT_INITIAL_DELAY`, `RECONNECT_MAX_DELAY`, `SLOW_START_DURATION`, `THREAD_JOIN`, `THREAD_JOIN_LONG`, `TX_QUEUE_MAXSIZE`, `TX_QUEUE_POLL`, `DASHBOARD_REFRESH`). Updated imports in `circuit_breaker.py`, `health_probe.py`, `threads.py`, `tx_queue.py`, `service_check.py`, and `launcher.py`.
- **Event Bus System** (`src/utils/event_bus.py`) — Thread-safe pub/sub with bounded ThreadPoolExecutor (4 workers). `MessageEvent` and `ServiceEvent` types. Convenience functions: `emit_message()`, `emit_service_status()`. Wired into `Meshtastic_Interface.py` (RX/TX paths) and `launcher.py` (service status, clean shutdown).
- **Enhanced Config Validation** (`src/utils/common.py`) — `ConfigValidationError` dataclass with severity levels (error/warning/info). Structured `validate_config()` returning typed errors. Bitrate and feature-flag validation. Config templates: `template_serial()`, `template_tcp()`.
- **Tests** — 2 new test files (`test_timeouts.py`, `test_event_bus.py`), expanded `test_common.py`. 50+ new test cases. 19 test files total, all passing.

### Files Changed

| Action | File |
|--------|------|
| CREATE | `src/utils/timeouts.py` |
| CREATE | `src/utils/event_bus.py` |
| CREATE | `tests/test_timeouts.py` |
| CREATE | `tests/test_event_bus.py` |
| MODIFY | `src/utils/common.py` (enhanced validation) |
| MODIFY | `src/Meshtastic_Interface.py` (emit events) |
| MODIFY | `src/utils/circuit_breaker.py` (use timeout constants) |
| MODIFY | `src/utils/health_probe.py` (use timeout constants) |
| MODIFY | `src/utils/service_check.py` (use timeout constants) |
| MODIFY | `src/utils/threads.py` (use timeout constants) |
| MODIFY | `src/utils/tx_queue.py` (use timeout constants) |
| MODIFY | `launcher.py` (emit events, use timeouts) |
| MODIFY | `tests/test_common.py` (new validation tests) |

---

## Session 2: Persistent Message Queue + Daemon Mode (Next Session)

### 2a. Persistent Message Queue

**Why:** Messages currently lost on restart. No retry differentiation, no dead letter queue for debugging.

- Create `src/utils/message_queue.py` adapted from MeshForge's `src/gateway/message_queue.py`
- SQLite-backed persistence (survives restarts)
- Message lifecycle: PENDING → IN_PROGRESS → DELIVERED / FAILED → DEAD_LETTER
- Priority levels: NORMAL, HIGH
- Retry policy with error classification:
  - Transient (retriable): connection_reset, timeout, "not connected"
  - Permanent (non-retriable): permission_denied, invalid_destination
- Exponential backoff: 2s initial, 60s max
- Deduplication via content hash + time window
- Integration with TX queue: replace simple FIFO with persistent queue
- Emit events via event_bus on message state changes
- DB path: `~/.config/rns-gateway/message_queue.db`

### 2b. Daemon Mode

**Why:** Gateway Tool currently requires interactive session. No auto-recovery for embedded/Pi deployments.

- Create `src/daemon.py` adapted from MeshForge's `src/daemon.py`
- `DaemonService` protocol (start, stop, is_alive, get_status)
- `GatewayBridgeService` wrapping `launcher.py:start_gateway()`
- Thread watchdog: monitors service health, auto-restarts with backoff
- PID file management: prevents multiple instances
- Signal handling: SIGTERM (stop), SIGHUP (reload config)
- Status reporting: JSON output for systemd integration
- Systemd unit file: `scripts/meshgateway.service`
- CLI: `python src/daemon.py start|stop|status|restart`

### 2c. Tests

- `tests/test_message_queue.py` — persistence, retry, dedup, dead letter, lifecycle
- `tests/test_daemon.py` — service lifecycle, watchdog, PID management

---

## Session 3: MQTT Bridge Mode

### 3a. MQTT Bridge Handler

**Why:** TCP-based bridge blocks meshtasticd web client. MQTT mode operates without interference — the single most requested improvement.

- Create `src/mqtt_bridge.py` adapted from MeshForge's `src/gateway/mqtt_bridge_handler.py`
- RX via MQTT: subscribe to `msh/{region}/2/json/{channel}/#`
- TX via HTTP protobuf: POST to `http://localhost:9443/api/v1/toradio`
- Zero interference with meshtasticd web client
- paho-mqtt integration with auto-reconnect
- Circuit breaker integration
- Message deduplication (by message ID + time window)
- Add `paho-mqtt` to requirements.txt

### 3b. Bridge Mode Selection

- Extend `config.json` schema: `gateway.bridge_mode` ∈ {direct, mqtt}
  - `direct` — current TCP/serial mode (default, backward compatible)
  - `mqtt` — new MQTT bridge mode
- Update `launcher.py` to select bridge handler based on mode
- Update TUI menu to allow switching bridge mode

### 3c. Tests

- `tests/test_mqtt_bridge.py` — MQTT subscribe/publish, HTTP TX, dedup, reconnect
- Integration test with mock meshtasticd MQTT broker

---

## Session 4: Polish, Node Tracking, and Production Hardening

### 4a. Message Deduplication Improvements

- Three-layer dedup: circuit breaker level + routing level + queue level
- Configurable time window in config.json

### 4b. Node Tracker (Basic)

- Track known nodes with last-seen, SNR, hop count
- Display in TUI dashboard and web dashboard
- Persist to `~/.config/rns-gateway/nodes.json`

### 4c. Dashboard Integration

- Wire event bus subscribers into web dashboard (live message feed)
- Wire event bus into TUI dashboard (real-time status)
- Add message queue stats to both dashboards

### 4d. Production Hardening

- Subprocess timeout protection on all service_check calls
- Config drift detection (warn if gateway config path != rnsd config)
- Graceful degradation for missing optional deps (safe_import pattern)

---

## Files Modified/Created Per Session

### Session 1 (Completed — commit `dc1e7d7`)
| Action | File |
|--------|------|
| CREATE | `src/utils/timeouts.py` |
| CREATE | `src/utils/event_bus.py` |
| CREATE | `tests/test_timeouts.py` |
| CREATE | `tests/test_event_bus.py` |
| MODIFY | `src/utils/common.py` (enhanced validation) |
| MODIFY | `src/Meshtastic_Interface.py` (emit events) |
| MODIFY | `src/utils/circuit_breaker.py` (use timeout constants) |
| MODIFY | `src/utils/health_probe.py` (use timeout constants) |
| MODIFY | `src/utils/service_check.py` (use timeout constants) |
| MODIFY | `src/utils/threads.py` (use timeout constants) |
| MODIFY | `src/utils/tx_queue.py` (use timeout constants) |
| MODIFY | `launcher.py` (emit events, use timeouts) |
| MODIFY | `tests/test_common.py` (new validation tests) |

### Session 2
| Action | File |
|--------|------|
| CREATE | `src/utils/message_queue.py` |
| CREATE | `src/daemon.py` |
| CREATE | `scripts/meshgateway.service` |
| CREATE | `tests/test_message_queue.py` |
| CREATE | `tests/test_daemon.py` |
| MODIFY | `src/utils/tx_queue.py` (persistent queue integration) |
| MODIFY | `launcher.py` (daemon support) |
| MODIFY | `requirements.txt` (no new deps — sqlite3 is stdlib) |

### Session 3
| Action | File |
|--------|------|
| CREATE | `src/mqtt_bridge.py` |
| CREATE | `tests/test_mqtt_bridge.py` |
| MODIFY | `config.json.example` (mqtt bridge config) |
| MODIFY | `launcher.py` (bridge mode selection) |
| MODIFY | `src/ui/menu.py` (bridge mode switch) |
| MODIFY | `requirements.txt` (add paho-mqtt) |

### Session 4
| Action | File |
|--------|------|
| CREATE | `src/utils/node_tracker.py` |
| CREATE | `tests/test_node_tracker.py` |
| MODIFY | `src/monitoring/web_dashboard.py` (event bus, message feed) |
| MODIFY | `src/ui/dashboard.py` (event bus, live stats) |
| MODIFY | `src/utils/service_check.py` (subprocess timeouts) |

---

## Verification Strategy (All Sessions)

1. `python -m pytest tests/ -v --timeout=30` — all tests pass
2. `ruff check src/ launcher.py scripts/` — no lint errors
3. `python -m py_compile launcher.py` — syntax check
4. Manual: `python launcher.py --debug` starts without errors (hardware permitting)
