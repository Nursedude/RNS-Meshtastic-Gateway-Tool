# RNS-Meshtastic Gateway Tool: Persistent Issues & Session Memory

> **Purpose**: Durable context for Claude Code sessions. Read this first.
> **Last updated**: 2026-04-16 (after tracker security follow-ups branch)

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

### 8. TUI dashboard is a separate process
`src/ui/dashboard.py` is launched as a subprocess by `src/ui/menu.py`. It CANNOT
share in-memory state (singletons, module globals) with the daemon. Any state
the dashboard needs must round-trip through disk. Established pattern: atomic
tmp+rename with 0o600 — see `node_tracker.save()` and `health_probe.save_snapshot()`
/ `load_snapshot()`. Readers should enforce a TTL so a dead daemon can't leave
phantom state displayed.

### 9. Stats APIs use wall-clock, not monotonic
Any timestamp exposed via `get_stats()`, dashboards, or an HTTP API must be
`time.time()` (Unix epoch). Reserve `time.monotonic()` for interval math
internal to the class (e.g., recovery-timeout computations). Mixing the two
within the same API has bitten us (circuit_breaker get_stats regression).

### 10. Forked-PR GitHub tokens are read-only
A base repo cannot grant `pull-requests: write` to a forked-PR workflow run —
the token is always read-only. Any CI step that posts comments / status on PRs
must detect `pr.head.repo.full_name !== repository.full_name` and skip, and
wrap the API call in try/catch with `core.warning`. Otherwise the workflow
fails for every external contributor PR.

### 11. Event-bus calls: broad-except + log.debug
Event-bus emits (`src/utils/event_bus.emit_*`) are optional — they must never
block TX/RX or connection handlers. The right pattern is:

```python
try:
    from src.utils.event_bus import emit_message
    emit_message(...)
except Exception as e:
    log.debug("event bus emit failed: %s", e)
```

Narrower tuples like `(ImportError, AttributeError)` are too tight — a
saturated `ThreadPoolExecutor` or `QueueFull` raises `RuntimeError`, which
would propagate and drop a packet. `except Exception` still lets
`SystemExit`/`KeyboardInterrupt` through (they're `BaseException` subclasses),
and the explicit `log.debug` avoids the silent-swallow anti-pattern.

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

- **506 tests** across 23 test files (as of 2026-04-16, after PR #34)
- Run: `python -m pytest tests/ -v --timeout=30`
- All tests must pass before committing
- Flask dashboard tests require `flask` to be installed (skip gracefully if missing)

### Singleton test hygiene

When a module uses a singleton (e.g. `_health_probe` in `src/utils/health_probe.py`),
tests that instantiate it leak state across the session unless explicitly reset.
Use `setup_method` / `teardown_method` setting `_hp_mod._health_probe = None`.
`tests/test_launcher.py::_import_launcher` does this too so hysteresis counters
stay deterministic when the launcher is imported repeatedly.

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

## Recent Review Cycle (PRs #27-#34)

Delivered between 2026-04-16 in a single review-and-followup session:

| PR | Summary | Merge sha |
|----|---------|-----------|
| #27 | README Mermaid diagrams | db74793 |
| #28 | MeshForge diagnostics, delivery tracking, resilience | 38f01e9 |
| #29 | Security hardening (MQTT TLS/auth, XSS, SSRF, file perms, S-22..S-34) | e391478 |
| #30 | Supply-chain lockfile + `.claude/` session memory | 33599cf |
| #31 | CI pytest-log tee + failure summary comment | 256e942 |
| #32 | Review follow-ups: singleton wiring, stats clock, CI fork guard | 7cbabc0 |
| #33 | Snapshot persistence for dashboard ↔ daemon state | b8ba288 |
| #34 | Event-bus resilience + per-service zero-traffic detection | bf7dda7 |

---

## Outstanding Review Findings (not yet fixed)

Items from the PR #27-#31 security review that remain open. PR #32/#34 cleared
the biggest correctness / resilience concerns (singleton, stats clock, CI
fork, event-bus `except`, zero-traffic per-service). The
`claude/fix-tracker-security-issues-BHt9w` branch closes the rest:

- DeliveryTracker IDs widened to full 128-bit UUID hex.
- MQTT `_seen_ids` cleanup verified + hard cap (`MQTT_DEDUP_MAX_ENTRIES`)
  added; tested in `tests/test_mqtt_bridge.py::TestMqttDedup`.
- SSRF blocklist for cloud-metadata hosts/IPs (169.254.169.254,
  metadata.google.internal, fd00:ec2::254, 100.100.100.200, link-local
  ranges) added to `_validate_http_api_url`.
- RNS `PanicException` (BaseException subclass) at import time is now
  caught by name with a `BaseException` re-raise for `KeyboardInterrupt` /
  `SystemExit`.
- Flask `/api/*` endpoints have a per-IP, per-route fixed-window rate
  limit (`rate_limited` decorator).
- SQLite `journal_mode=WAL` was already enabled at first commit; the
  branch adds a regression test (`test_journal_mode_is_wal`).

### CI / tooling

- **Pre-existing unused imports.** `threading`, `pytest` in
  `tests/test_health_probe.py`; `signal` in `tests/test_launcher.py`.
  Safe to remove but outside the current review scope.

---

## Development Checklist

Before committing, verify:

- [ ] `python -m pytest tests/ -v --timeout=30` — all pass
- [ ] `ruff check src/ launcher.py scripts/` clean
- [ ] No `shell=True` in subprocess calls
- [ ] No bare `except Exception: pass` (narrow or `log.debug` instead)
- [ ] Timeouts from `src/utils/timeouts.py`, not hardcoded
- [ ] Config values validated before use
- [ ] Sensitive files written with restrictive permissions (`0o600`)
- [ ] No `innerHTML` in dashboard JavaScript
- [ ] MQTT credentials support env vars, not just config
- [ ] Dashboard ↔ daemon state goes through disk (atomic tmp+rename), not singletons
- [ ] Stats/API timestamps are wall-clock (`time.time()`), not `time.monotonic()`
- [ ] Event-bus emits use `except Exception as e: log.debug(...)` (never a narrow tuple)
- [ ] CI steps that post PR comments check for fork PRs + wrap in try/catch
