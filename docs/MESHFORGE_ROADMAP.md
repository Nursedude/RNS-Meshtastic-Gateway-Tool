# MeshForge → RNS-Meshtastic-Gateway-Tool: Feature & Reliability Roadmap

## Context

MeshForge (Nursedude/meshforge) has evolved significantly since the last round of improvements were ported to RNS-Meshtastic-Gateway-Tool. This roadmap tracks the porting of meaningful features and reliability patterns across 4 sessions, prioritized by impact and dependency order.

**Current state of Gateway Tool:** v1.5+ with circuit breaker, TX queue, reconnect strategy, slow-start recovery, bridge health monitor, active health probe, thread manager, structured logging, TUI, web dashboard, centralized timeouts, event bus, enhanced config validation, persistent message queue, daemon/systemd mode, MQTT bridge mode, node tracker, dashboard API endpoints, and comprehensive test suite (23 test files).

**Completed:** All 4 sessions — Foundation Layer, Persistent Message Queue + Daemon Mode, MQTT Bridge Mode, Node Tracking + Dashboard Integration
**Remaining gaps vs MeshForge:** None — all sessions complete.

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

## Session 2: Persistent Message Queue + Daemon Mode — COMPLETED

### What Was Delivered

- **Persistent Message Queue** (`src/utils/message_queue.py`) — SQLite-backed message persistence with WAL mode. Message lifecycle state machine: PENDING → IN_PROGRESS → DELIVERED / DEAD_LETTER. Priority levels (NORMAL, HIGH). Retry policy with error classification via `classify_error()` from `bridge_health.py` (transient → retry with exponential backoff 2s–60s, permanent → dead letter). Content-hash deduplication (SHA-256, 60s window). Thread-local SQLite connections for thread safety. Event bus integration for status changes. DB path: `~/.config/rns-gateway/message_queue.db`.
- **TX Queue Callbacks** (`src/utils/tx_queue.py`) — Added optional `on_send_success` and `on_send_failure` callback parameters for delivery notification. Fully backward-compatible.
- **Meshtastic Interface Integration** (`src/Meshtastic_Interface.py`) — MessageQueue wired as drop-in replacement for TxQueue when `features.message_queue = true`. Routes through `process_incoming()` with priority support. Metrics include `message_queue_pending` and `message_queue_dead_letters`.
- **Daemon Mode** (`src/daemon.py`) — `DaemonService` protocol with PID file management (`~/.config/rns-gateway/gateway.pid`), `GatewayBridgeService` wrapping `launcher.start_gateway()` in a monitored thread, `Watchdog` with consecutive failure detection and exponential backoff restart. Signal handling: SIGTERM/SIGINT (stop), SIGHUP (config reload). CLI: `python src/daemon.py start|stop|status|restart`.
- **Systemd Integration** (`scripts/meshgateway.service`) — Type=simple unit file with security hardening (NoNewPrivileges, ProtectSystem=strict, PrivateTmp). ExecReload via SIGHUP. Restart=on-failure.
- **Config Validation** (`src/utils/common.py`) — Added `message_queue` feature flag validation. Mutual exclusivity warning when both `message_queue` and `tx_queue` are enabled.
- **Timeout Constants** (`src/utils/timeouts.py`) — Added `MSG_QUEUE_POLL`, `MSG_QUEUE_MAX_RETRIES`, `MSG_QUEUE_RETRY_INITIAL`, `MSG_QUEUE_RETRY_MAX`, `MSG_QUEUE_RETRY_MULTIPLIER`, `MSG_QUEUE_DEDUP_WINDOW`, `MSG_QUEUE_DEDUP_CLEANUP`, `WATCHDOG_INTERVAL`, `WATCHDOG_FAILURES`, `DAEMON_STOP_TIMEOUT`.
- **Tests** — 2 new test files (`test_message_queue.py` with 30 tests, `test_daemon.py` with 32 tests). 21 test files total, 363 tests passing.

### Files Changed

| Action | File |
|--------|------|
| CREATE | `src/utils/message_queue.py` |
| CREATE | `src/daemon.py` |
| CREATE | `scripts/meshgateway.service` |
| CREATE | `tests/test_message_queue.py` |
| CREATE | `tests/test_daemon.py` |
| MODIFY | `src/utils/timeouts.py` (message queue + daemon constants) |
| MODIFY | `src/utils/tx_queue.py` (delivery callbacks) |
| MODIFY | `src/Meshtastic_Interface.py` (message queue integration) |
| MODIFY | `src/utils/common.py` (feature flag validation) |
| MODIFY | `config.json.example` (message_queue flag) |
| MODIFY | `pyproject.toml` (S108 test ignore) |

---

## Session 3: MQTT Bridge Mode — COMPLETED

### What Was Delivered

- **MQTT Bridge Handler** (`src/mqtt_bridge.py`) — Zero-interference bridge to meshtasticd via MQTT. RX subscribes to `msh/{region}/2/json/{channel}/#`, TX via HTTP POST to `http://localhost:9443/api/v1/toradio`. Supports paho-mqtt v2.0 callback API, auto-reconnect with configurable backoff, circuit breaker integration, message deduplication by ID + time window, event bus integration, TX/message queue support. Presents same interface as `MeshtasticInterface` for transparent launcher swap.
- **Bridge Mode Selection** (`launcher.py`) — `gateway.bridge_mode` config field: `"direct"` (default, backward compatible) or `"mqtt"`. Launcher conditionally imports `MqttBridge` or `MeshtasticInterface`.
- **Config Validation** (`src/utils/common.py`) — Added `_VALID_BRIDGE_MODES`, MQTT field validation (`mqtt_host`, `mqtt_port`, `mqtt_topic_root`, `mqtt_region`, `http_api_port`) in both `validate_config()` and `validate_config_strict()`. Added `config_template_mqtt()`.
- **Timeout Constants** (`src/utils/timeouts.py`) — Added `MQTT_CONNECT_TIMEOUT`, `MQTT_RECONNECT_MIN`, `MQTT_RECONNECT_MAX`, `MQTT_KEEPALIVE`, `HTTP_TORADIO_TIMEOUT`, `MQTT_DEDUP_WINDOW`.
- **Tests** — `tests/test_mqtt_bridge.py` with MQTT connection, RX/TX, dedup, circuit breaker, health check, and metrics tests.

---

## Session 4: Node Tracking, Dashboard Integration — COMPLETED

### What Was Delivered

- **Node Tracker** (`src/utils/node_tracker.py`) — Thread-safe registry of known mesh nodes with `node_id`, `last_seen`, `first_seen`, `message_count`, `snr`, `hop_count`, `node_name`, `rssi`. Event bus integration for auto-update on RX messages. JSON persistence to `~/.config/rns-gateway/nodes.json` with configurable auto-save interval and stale node cleanup.
- **Web Dashboard API** (`src/monitoring/web_dashboard.py`) — Added `/api/messages` (recent 50 messages), `/api/health` (bridge health summary), `/api/nodes` (known nodes list). Event bus subscriber for live message buffering. Wiring functions `set_bridge_health()`, `set_node_tracker()`, `init_event_subscribers()`.
- **Web Dashboard UI** (`src/monitoring/templates/dashboard.html`) — Added Bridge Health card, Recent Messages card with auto-refresh (10s), Known Nodes card with auto-refresh (30s), bridge mode display.
- **TUI Dashboard** (`src/ui/dashboard.py`) — Added bridge mode display, MQTT broker info, Known Nodes panel with recent nodes and SNR.
- **Launcher Integration** — Node tracker wired into startup/shutdown sequence.
- **Timeout Constants** (`src/utils/timeouts.py`) — Added `NODE_TRACKER_SAVE_INTERVAL`, `NODE_TRACKER_STALE_DAYS`.
- **Tests** — `tests/test_node_tracker.py` with node tracking, persistence, event bus, stale cleanup tests.

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

### Session 2 (Completed)
| Action | File |
|--------|------|
| CREATE | `src/utils/message_queue.py` |
| CREATE | `src/daemon.py` |
| CREATE | `scripts/meshgateway.service` |
| CREATE | `tests/test_message_queue.py` |
| CREATE | `tests/test_daemon.py` |
| MODIFY | `src/utils/timeouts.py` (message queue + daemon constants) |
| MODIFY | `src/utils/tx_queue.py` (delivery callbacks) |
| MODIFY | `src/Meshtastic_Interface.py` (message queue integration) |
| MODIFY | `src/utils/common.py` (feature flag validation) |
| MODIFY | `config.json.example` (message_queue flag) |
| MODIFY | `pyproject.toml` (S108 test ignore) |

### Session 3 (Completed)
| Action | File |
|--------|------|
| CREATE | `src/mqtt_bridge.py` |
| CREATE | `tests/test_mqtt_bridge.py` |
| MODIFY | `src/utils/timeouts.py` (MQTT timeout constants) |
| MODIFY | `src/utils/common.py` (MQTT validation, template) |
| MODIFY | `config.json.example` (MQTT bridge config) |
| MODIFY | `launcher.py` (bridge mode selection) |
| MODIFY | `requirements.txt` (add paho-mqtt) |

### Session 4 (Completed)
| Action | File |
|--------|------|
| CREATE | `src/utils/node_tracker.py` |
| CREATE | `tests/test_node_tracker.py` |
| MODIFY | `src/utils/timeouts.py` (node tracker constants) |
| MODIFY | `src/monitoring/web_dashboard.py` (API endpoints, event bus) |
| MODIFY | `src/monitoring/templates/dashboard.html` (health, messages, nodes) |
| MODIFY | `src/ui/dashboard.py` (bridge mode, nodes panel) |
| MODIFY | `launcher.py` (node tracker wiring) |
| MODIFY | `docs/MESHFORGE_ROADMAP.md` (mark sessions complete) |

---

## Verification Strategy (All Sessions)

1. `python -m pytest tests/ -v --timeout=30` — all tests pass
2. `ruff check src/ launcher.py scripts/` — no lint errors
3. `python -m py_compile launcher.py` — syntax check
4. Manual: `python launcher.py --debug` starts without errors (hardware permitting)
