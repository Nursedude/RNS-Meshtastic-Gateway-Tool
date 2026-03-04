# MeshForge → RNS-Meshtastic-Gateway-Tool: Feature & Reliability Roadmap

## Context

MeshForge (Nursedude/meshforge) has evolved significantly since the last round of improvements were ported to RNS-Meshtastic-Gateway-Tool. This plan identifies meaningful features and reliability patterns to port across 4 sessions, prioritized by impact and dependency order.

**Current state of Gateway Tool:** v1.5 with circuit breaker, TX queue, reconnect strategy, slow-start recovery, bridge health monitor, active health probe, thread manager, structured logging, TUI, web dashboard, and comprehensive test suite (17 test files).

**Key gaps vs MeshForge:** No persistent message queue, no event bus, no centralized timeouts, no daemon/systemd mode, no MQTT bridge mode, limited config validation.

---

## Session 1: Foundation Layer (This Session)

Quick-win infrastructure that later sessions depend on.

### 1a. Centralized Timeout Constants (~30 min)

**Why:** Magic numbers scattered across codebase make tuning difficult. Every subsequent feature (daemon, message queue) needs defined timeouts.

- Create `src/utils/timeouts.py` modeled on `/tmp/meshforge/src/utils/timeouts.py`
- Extract existing timeouts from:
  - `launcher.py:33` → `HEALTH_CHECK_INTERVAL = 30`
  - `src/utils/circuit_breaker.py` → recovery_timeout (30.0)
  - `src/utils/reconnect.py` → initial_delay (2.0), max_delay (60.0)
  - `src/utils/health_probe.py` → interval (30)
  - `src/utils/threads.py` → join timeout (5.0)
  - `src/utils/tx_queue.py` → inter-packet delays
- Add Gateway-Tool-relevant constants:
  - `SUBPROCESS_QUICK`, `SUBPROCESS_DEFAULT` for service_check calls
  - `TCP_CONNECT` for meshtasticd connection
  - `THREAD_JOIN`, `THREAD_JOIN_LONG`
  - `CIRCUIT_RECOVERY`
  - `HEALTH_CHECK_INTERVAL`
- Update imports in existing modules to reference `timeouts.py`

### 1b. Event Bus System (~1.5 hours)

**Why:** Enables real-time dashboard updates and decoupled component communication. Foundation for persistent message queue integration.

- Create `src/utils/event_bus.py` adapted from `/tmp/meshforge/src/utils/event_bus.py`
- Include: `EventBus` class with thread-safe pub/sub, bounded ThreadPoolExecutor (4 workers)
- Event types for Gateway Tool scope:
  - `MessageEvent` — TX/RX messages (direction, content, node_id, network)
  - `ServiceEvent` — service availability changes
- Include convenience functions: `emit_message()`, `emit_service_status()`
- Drop MeshForge-specific types not applicable here (TacticalEvent, NodeEvent)
- Wire into `Meshtastic_Interface.py`:
  - `on_receive()` → emit RX message event
  - `_do_send()` → emit TX message event
- Wire into `launcher.py`:
  - Service status changes → emit service events
- Add `event_bus.shutdown()` to launcher's clean shutdown path

### 1c. Enhanced Config Validation (~1.5 hours)

**Why:** Configuration errors currently cascade into cryptic runtime failures. Templates give new users a working starting point.

- Enhance `src/utils/common.py`:
  - Add `ConfigValidationError` dataclass with severity levels (error, warning, info)
  - Add `validate_config()` returning structured errors instead of string list
  - Add bitrate-specific validation (warn if unusually low/high for LoRa)
  - Add feature flag validation (circuit_breaker, tx_queue must be bool)
- Add config templates as class methods or factory functions:
  - `template_serial()` — Serial/USB connection (most common)
  - `template_tcp()` — TCP to meshtasticd
- Update `config.json.example` with inline comments for all fields

### 1d. Tests for all Session 1 additions (~1 hour)

- `tests/test_timeouts.py` — verify constants exist and have sane values
- `tests/test_event_bus.py` — subscribe/emit/unsubscribe, thread safety, shutdown
- Update `tests/test_common.py` — new validation rules, templates, severity

### 1e. Verification

- Run `python -m pytest tests/ -v` — all tests pass
- Run `ruff check src/ launcher.py` — no lint errors
- Verify `python -c "from src.utils.timeouts import *; print('OK')"` works
- Verify `python -c "from src.utils.event_bus import event_bus; print('OK')"` works

---

## Session 2: Persistent Message Queue + Daemon Mode

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

### Session 1 (This Session)
| Action | File |
|--------|------|
| CREATE | `src/utils/timeouts.py` |
| CREATE | `src/utils/event_bus.py` |
| CREATE | `tests/test_timeouts.py` |
| CREATE | `tests/test_event_bus.py` |
| MODIFY | `src/utils/common.py` (enhanced validation) |
| MODIFY | `src/Meshtastic_Interface.py` (emit events) |
| MODIFY | `src/utils/circuit_breaker.py` (use timeout constants) |
| MODIFY | `src/utils/reconnect.py` (use timeout constants) |
| MODIFY | `src/utils/health_probe.py` (use timeout constants) |
| MODIFY | `src/utils/threads.py` (use timeout constants) |
| MODIFY | `launcher.py` (emit events, use timeouts) |
| MODIFY | `config.json.example` (updated template) |
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
