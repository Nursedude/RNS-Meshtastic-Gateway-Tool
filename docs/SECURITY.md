# Security Review: RNS-Meshtastic Gateway Tool

**Latest review:** 2026-04-16 (v1.3)
**Previous reviews:** 2026-02-23 (v1.2), 2026-02-21 (v1.0 → v1.1)
**Scope:** Full codebase — all Python source, configuration files, templates, and dependencies.

---

## Findings Summary

| ID | Severity | Description | Status |
|----|----------|-------------|--------|
| S-01 | HIGH | Flask dashboard binds to 0.0.0.0 with no authentication | Remediated |
| S-02 | HIGH | Unpinned dependencies in requirements.txt | Remediated |
| S-03 | MEDIUM | Broad exception handlers swallow errors silently | Remediated |
| S-04 | MEDIUM | No config validation on loaded JSON | Remediated |
| S-05 | MEDIUM | TCP connection to meshtasticd is unencrypted | Documented |
| S-06 | MEDIUM | config.json not in .gitignore | Remediated |
| S-07 | MEDIUM | System info disclosure via web dashboard | Remediated |
| S-08 | LOW | No Python logging module — only print() | Remediated |
| S-09 | LOW | Flask dashboard runs without HTTPS | Noted |
| S-10 | LOW | No CSRF protection on Flask routes | Noted |
| S-11 | LOW | Unused imports in driver module | Remediated |
| S-22 | HIGH | MQTT broker connections without TLS or authentication | Remediated |
| S-23 | HIGH | XSS via innerHTML in dashboard template | Remediated |
| S-24 | HIGH | SSRF via unvalidated http_api_url config | Remediated |
| S-25 | MEDIUM | PID file TOCTOU race condition | Remediated |
| S-26 | MEDIUM | MQTT payload size not bounded (OOM risk) | Remediated |
| S-27 | MEDIUM | base64 decode missing binascii.Error handler | Remediated |
| S-28 | MEDIUM | MQTT topic injection via unsafe config values | Remediated |
| S-29 | MEDIUM | Sensitive data files world-readable | Remediated |
| S-30 | MEDIUM | Hostname validation missing null byte/newline checks | Remediated |
| S-31 | MEDIUM | Bare `except Exception` in event bus calls | Remediated |
| S-32 | LOW | Flask debug mode not explicitly disabled | Remediated |
| S-33 | LOW | MQTT raw payload forwarded to event bus | Remediated |
| S-34 | LOW | No env var support for MQTT credentials | Remediated |

---

## Detailed Findings

### S-01 — Unauthenticated Dashboard on All Interfaces (HIGH)

**Location:** `src/monitoring/web_dashboard.py:60-68`, `config.json.example:11`

**Description:** The example configuration bound the Flask web dashboard to `0.0.0.0` (all network interfaces) with no authentication. Anyone on the network could view system information including hostname, platform details, Python version, serial ports, and file paths.

**Remediation:**
- Changed default bind address from `0.0.0.0` to `127.0.0.1` in `config.json.example`.
- Enhanced security warning when users override to `0.0.0.0`.
- Removed filesystem path (`config_path`) from the HTML template error message.

---

### S-02 — Unpinned Dependencies (HIGH)

**Location:** `requirements.txt`

**Description:** All five dependencies were listed without version constraints (`rns`, `meshtastic`, `pyserial`, `flask`, `pytest`). This allows arbitrary future versions — including potentially compromised ones — to be installed via `pip install`.

**Remediation:** Pinned all dependencies to compatible version ranges (e.g., `rns>=0.7.4,<1.0`).

---

### S-03 — Broad Exception Handlers (MEDIUM)

**Location:** `src/Meshtastic_Interface.py:106, 200, 207`

**Description:** Three `except Exception: pass` blocks silently swallowed all errors, including security-relevant ones. This made debugging connection and configuration issues difficult and could hide unexpected failure modes.

**Remediation:** Narrowed each handler to the specific exception types that can reasonably occur:
- Config lookup: `(KeyError, TypeError, AttributeError)`
- Pub/sub unsubscribe: `(KeyError, ValueError, AttributeError)`
- Interface close: `(OSError, AttributeError)`

---

### S-04 — No Config Validation (MEDIUM)

**Location:** `src/utils/common.py:20-33`

**Description:** `load_config()` loaded and returned JSON without any structural or type validation. Malformed config values (wrong types, out-of-range ports, invalid connection types) were passed directly to the driver and Flask server.

**Remediation:** Added `validate_config()` function that checks:
- `connection_type` is `"serial"` or `"tcp"`
- Port numbers are integers in range 1–65535
- Bitrate is a positive number
- Prints warnings for each violation

---

### S-05 — TCP Connection Without TLS (MEDIUM)

**Location:** `src/Meshtastic_Interface.py:144-148`

**Description:** The TCP connection to meshtasticd uses plaintext. Packet data in transit is unencrypted, which could allow eavesdropping on a shared network.

**Status:** Documented. This is a limitation of the Meshtastic Python API — the meshtasticd TCP protocol does not support TLS. Users should restrict TCP mode to trusted/local networks.

---

### S-06 — config.json Not in .gitignore (MEDIUM)

**Location:** `.gitignore`

**Description:** `config.json` was not gitignored, risking accidental commit of configuration containing node names, network addresses, or other deployment-specific details.

**Remediation:** Added `config.json`, `*.env`, and `.env` to `.gitignore`.

---

### S-07 — System Info Disclosure (MEDIUM)

**Location:** `src/monitoring/web_dashboard.py:36-57`, `src/monitoring/templates/dashboard.html`

**Description:** The web dashboard exposed hostname, platform version, Python version, serial port paths, and the filesystem location of `config.json`. This information aids reconnaissance.

**Remediation:**
- Removed `config_path` from the template context.
- Replaced filesystem path in the HTML error message with a generic setup instruction.
- Default bind changed to localhost (see S-01).

---

### S-08 — No Logging Module (LOW)

**Location:** Entire codebase

**Description:** All diagnostic output uses `print()` statements. There is no persistent audit trail, no log levels, and no log rotation. Security events (connection failures, reconnect attempts, packet errors) are lost when stdout is not captured.

**Remediation:** Migrated all core modules to Python's `logging` module:
- Added `src/utils/log.py` with centralized `setup_logging()` — configures console output and optional `RotatingFileHandler`.
- Replaced `print()` with appropriate log levels (`debug`, `info`, `warning`, `error`, `critical`) in `launcher.py`, `src/Meshtastic_Interface.py`, `src/utils/common.py`, and `src/monitoring/web_dashboard.py`.
- TUI rendering files (`src/ui/menu.py`, `src/ui/dashboard.py`) retain `print()` for terminal display, which is not diagnostic logging.

---

### S-09 — Flask Without HTTPS (LOW)

**Location:** `src/monitoring/web_dashboard.py:68`

**Description:** The Flask development server runs over plain HTTP. Dashboard data could be intercepted in transit.

**Status:** Noted. Acceptable for localhost-only access. If exposed to a network, place behind a reverse proxy with TLS.

---

### S-10 — No CSRF Protection (LOW)

**Location:** `src/monitoring/web_dashboard.py`

**Description:** The Flask app has no CSRF middleware. Currently the dashboard is read-only (GET only), so the practical risk is minimal.

**Status:** Noted. If write operations (config changes, gateway control) are added, CSRF protection must be implemented.

---

### S-11 — Unused Imports (LOW)

**Location:** `src/Meshtastic_Interface.py:3,5`

**Description:** `random` and `time` were imported but never used. Unused imports increase the attack surface marginally and clutter the namespace.

**Remediation:** Removed both unused imports.

---

## Positive Findings

The following areas were reviewed and found to be secure:

- **No command injection:** All `subprocess` calls use list arguments (`shell=False`). No `os.system()`, `eval()`, or `exec()` usage anywhere.
- **No hardcoded credentials:** No API keys, tokens, passwords, or secrets found in source code.
- **No SQL or deserialization risks:** No database usage, no `pickle.load()`, no `yaml.load()` without SafeLoader.
- **Safe file path construction:** All paths use `os.path.join()` from known base directories. No user-controlled path components.
- **Bounded data structures:** `deque(maxlen=100)` prevents unbounded memory growth in packet frequency logging.
- **Subprocess timeouts:** All `subprocess.run()` calls include timeout parameters.

---

## v1.2 Security Hardening (2026-02-23)

Improvements adopted from MeshForge security patterns and a fresh review of the codebase.

### S-12 — Hostname/IP Validation (MEDIUM → Remediated)

**Location:** `src/utils/common.py`

**Description:** TCP host and dashboard host values from `config.json` were used without validation. A malicious config value starting with `-` could act as flag injection when passed to subprocess or network calls. Values with shell metacharacters (`; rm -rf /`) posed theoretical risk.

**Remediation:** Added `validate_hostname()` function (adopted from MeshForge `_validate_hostname()` pattern):
- Rejects strings starting with `-` (flag injection prevention)
- Limits length to 253 characters (RFC 1035)
- Allows only alphanumeric, dots, hyphens, and colons
- Applied in `validate_config()`, `Meshtastic_Interface._init_tcp()`, and `web_dashboard.py` before Flask binding

### S-13 — Port Validation Enforcement (MEDIUM → Remediated)

**Location:** `src/utils/common.py`

**Description:** Port validation in v1.1 warned but did not enforce rejection at the point of use. `validate_port()` now provides a reusable check applied at connection time.

**Remediation:** Added `validate_port()` function that rejects non-integers (including booleans), out-of-range values, and type mismatches. Dashboard falls back to safe defaults on invalid port.

### S-14 — $EDITOR Environment Variable Injection (MEDIUM → Remediated)

**Location:** `src/ui/menu.py`

**Description:** `get_editor()` read `$EDITOR`/`$VISUAL` and passed the value directly to `subprocess.run()` without verifying it resolves to an actual executable. A crafted environment variable could execute arbitrary commands.

**Remediation:** Added `shutil.which()` validation — `$EDITOR` is only used if it resolves to a real executable on `$PATH`. Falls back to known safe editors otherwise.

### S-15 — Active UDP Port Probe TOCTOU (LOW → Remediated)

**Location:** `src/utils/service_check.py`

**Description:** `check_rns_udp_port()` actively bound a socket to test port availability, which is a classic TOCTOU (Time-of-Check-Time-of-Use) vulnerability and caused contention with rnsd on Raspberry Pi hardware.

**Remediation:** Replaced with passive `/proc/net/udp` scanning on Linux (adopted from MeshForge PR #920-922). Falls back to socket probe on non-Linux platforms.

### S-16 — Config File Permission Warning (LOW → Remediated)

**Location:** `src/utils/common.py`

**Description:** `config.json` permissions were not checked. A world-readable or world-writable config could expose gateway settings to other users on shared systems.

**Remediation:** Added `check_config_permissions()` that warns on world-readable (`o+r`) or world-writable (`o+w`) config files on POSIX systems. Called automatically by `load_config()`.

### S-17 — Broad Exception Handlers in Driver (MEDIUM → Remediated)

**Location:** `src/Meshtastic_Interface.py`

**Description:** Four remaining `except Exception` blocks in the driver (serial init, TCP init, transmit, detach) could mask security-relevant exceptions.

**Remediation:** Narrowed to specific exception types:
- Serial/TCP init: `(OSError, ConnectionError, ValueError)`
- Transmit: `(OSError, AttributeError, TypeError)`
- Detach: `(OSError, AttributeError)`

### S-18 — Missing Subprocess Timeout (LOW → Remediated)

**Location:** `src/ui/menu.py:25`

**Description:** `clear_screen()` on Windows called `subprocess.run(['cmd', '/c', 'cls'])` without a timeout parameter.

**Remediation:** Added `timeout=5` to the subprocess call.

### S-19 — Menu Loop Not Exception-Protected (LOW → Remediated)

**Location:** `src/ui/menu.py`

**Description:** The `main_menu()` while loop had no exception handling. Any unhandled exception in a menu operation would crash the entire TUI, requiring a restart.

**Remediation:** Wrapped the loop body in try/except (adopted from MeshForge `_safe_call` pattern). Handles `KeyboardInterrupt` for clean exit and logs generic exceptions before continuing.

### S-20 — Crash Traceback Not Logged (LOW → Remediated)

**Location:** `launcher.py`

**Description:** The outer `except Exception` handler logged the error message but not the full traceback, making crash diagnosis difficult.

**Remediation:** Added `exc_info=True` to `log.critical()` to capture the full stack trace.

### S-21 — Handler-Level Log Filtering (LOW → Remediated)

**Location:** `src/utils/log.py`

**Description:** Logging configuration used a single level for all handlers. This prevented the common pattern of keeping console output quiet while capturing full detail to log files.

**Remediation:** Added `console_level` parameter to `setup_logging()` (adopted from MeshForge handler-level filtering). Console and file handlers can now operate at independent levels.

---

## v1.3 Security Hardening (2026-04-16)

Comprehensive security review with diff analysis against MeshForge gateway patterns.
Focus areas: MQTT security, XSS prevention, file permission hardening, input validation.

### S-22 — MQTT Without TLS or Authentication (HIGH → Remediated)

**Location:** `src/mqtt_bridge.py:158-179`

**Description:** MQTT broker connections were established without TLS encryption or username/password authentication. Any network observer could intercept mesh traffic, and unauthenticated brokers allowed message injection.

**Remediation:**
- Added `mqtt_tls` config option with `ssl.CERT_REQUIRED` and `PROTOCOL_TLS_CLIENT`
- Added `mqtt_username`/`mqtt_password` config options with `paho.username_pw_set()`
- Added environment variable fallback: `GATEWAY_MQTT_USERNAME`, `GATEWAY_MQTT_PASSWORD`
- Logs warnings when connecting to non-localhost brokers without TLS or auth
- Catches `ssl.SSLError` in connection handler

### S-23 — XSS via innerHTML in Dashboard (HIGH → Remediated)

**Location:** `src/monitoring/templates/dashboard.html:122-146`

**Description:** Dashboard JavaScript built HTML strings via concatenation and injected them with `innerHTML`. Message content and node IDs from API responses were not escaped, enabling stored XSS if malicious content entered the mesh network.

**Remediation:** Replaced all `innerHTML` string concatenation with safe DOM API:
- `document.createElement()` + `appendChild()` for element creation
- `textContent` for all user-controlled data (auto-escapes HTML entities)
- Unicode arrows (`\u2190`/`\u2192`) instead of HTML entities

### S-24 — SSRF via Unvalidated http_api_url (HIGH → Remediated)

**Location:** `src/mqtt_bridge.py:100-103`

**Description:** The `http_api_url` config field was used directly in `urllib.request.Request()` without validation. A crafted config could redirect HTTP POST requests to arbitrary internal services (file://, ftp://, or internal HTTP endpoints).

**Remediation:** Added `_validate_http_api_url()` static method:
- Only allows `http://` and `https://` schemes
- Rejects URLs without a hostname
- Strips embedded credentials from URLs
- Falls back to `http://localhost:{port}/api/v1/toradio` on any validation failure

### S-25 — PID File Race Condition (MEDIUM → Remediated)

**Location:** `src/daemon.py:106-112`

**Description:** `PidFile.acquire()` used a check-then-act pattern: read PID → check if running → write new PID. Two processes starting simultaneously could both pass the check and overwrite each other.

**Remediation:**
- Added `fcntl.flock(LOCK_EX | LOCK_NB)` for atomic lock acquisition on POSIX
- Lock held via file descriptor for the daemon's lifetime
- Graceful fallback to check-then-write on non-POSIX (Windows)
- PID file now created with `0o600` permissions via `os.open()`

### S-26 — Unbounded MQTT Payload Size (MEDIUM → Remediated)

**Location:** `src/mqtt_bridge.py:224-227`

**Description:** Inbound MQTT messages were parsed without size limits. A malicious or compromised MQTT broker could send oversized JSON payloads causing memory exhaustion (OOM).

**Remediation:** Added `MQTT_MAX_PAYLOAD_SIZE = 4096` constant. Messages exceeding this limit are dropped with a warning log before any JSON parsing occurs.

### S-27 — Missing binascii.Error in Base64 Handler (MEDIUM → Remediated)

**Location:** `src/mqtt_bridge.py:244, 280`

**Description:** `base64.b64decode()` raises `binascii.Error` on invalid input, but the exception handler only caught `(KeyError, TypeError, ValueError)`. Malformed base64 from MQTT could crash the message handler.

**Remediation:** Added `import binascii` and included `binascii.Error` in the exception tuple. Also added JSON type validation (`isinstance(data, dict)`) before field access.

### S-28 — MQTT Topic Injection (MEDIUM → Remediated)

**Location:** `src/mqtt_bridge.py:106`

**Description:** MQTT topic components (`mqtt_topic_root`, `mqtt_region`) from config were concatenated directly into the subscribe topic without validation. Control characters, wildcards, or encoded values could alter subscription behavior.

**Remediation:** Added `_build_subscribe_topic()` with regex validation (`^[a-zA-Z0-9/_\-\.]+$`). Rejects topic components containing unsafe characters with a clear error message.

### S-29 — World-Readable Data Files (MEDIUM → Remediated)

**Location:** `src/daemon.py:74-78`, `src/utils/message_queue.py:79-84`, `src/utils/node_tracker.py:100-113`

**Description:** PID file, message queue SQLite database, and nodes.json were created with default umask permissions (typically `0o644` or `0o666`). On shared systems, other users could read daemon status, queued messages, and mesh node metadata.

**Remediation:**
- Config directory `~/.config/rns-gateway/` created with `mode=0o700`
- PID file written via `os.open()` with explicit `0o600` mode
- Node tracker uses atomic write (write to `.tmp` then `os.replace()`) with `0o600`
- Message queue directory permissions enforced on startup

### S-30 — Hostname Null Byte/Newline Injection (MEDIUM → Remediated)

**Location:** `src/utils/common.py:68-85`

**Description:** `validate_hostname()` allowed null bytes (`\x00`) and newlines (`\n`, `\r`) in hostname strings. While the regex would catch most cases, these characters could bypass validation in edge cases and enable header injection or log forging.

**Remediation:** Added explicit checks for `\x00`, `\n`, and `\r` before the regex match, with a clear rejection message.

### S-31 — Bare `except Exception` in Event Bus Calls (MEDIUM → Remediated)

**Location:** `src/mqtt_bridge.py:200,219,269,320`, `src/Meshtastic_Interface.py:303,364`

**Description:** Event bus emit calls used `except Exception: pass` (with `# noqa: S110` suppression). These broad handlers could silently swallow security-relevant exceptions like `MemoryError` or `SystemExit`.

**Remediation:** Narrowed all event bus exception handlers to `except (ImportError, AttributeError)` — the only exceptions that can reasonably occur when the event bus module is optional.

### S-32 — Flask Debug Mode Not Explicitly Disabled (LOW → Remediated)

**Location:** `src/monitoring/web_dashboard.py:168`

**Description:** `app.run()` was called without explicit `debug=False`. While Flask defaults to False, explicit is better for security-critical code.

**Remediation:** Added `debug=False` to `app.run()`. Also added `frame-ancestors 'none'` to CSP header.

### S-33 — MQTT Raw Payload Forwarded to Event Bus (LOW → Remediated)

**Location:** `src/mqtt_bridge.py:260-268`

**Description:** The full MQTT JSON payload (`raw_data=data`) was forwarded to the event bus, which feeds into the dashboard API and node tracker. This could expose sensitive metadata, authentication tokens, or PII from the mesh network.

**Remediation:** Added a whitelist of safe metadata fields (`id`, `from`, `to`, `channel`, `type`, `snr`, `rssi`, `hopStart`, `hopLimit`, `fromName`). Only these fields are forwarded via the event bus.

### S-34 — No Environment Variable Support for MQTT Credentials (LOW → Remediated)

**Location:** `src/mqtt_bridge.py:94-103`

**Description:** MQTT credentials could only be set in `config.json`, which is a file on disk. No support for environment variables meant credentials had to be stored in plaintext alongside non-sensitive configuration.

**Remediation:** Added environment variable fallback for sensitive fields:
- `GATEWAY_MQTT_USERNAME` → `mqtt_username`
- `GATEWAY_MQTT_PASSWORD` → `mqtt_password`
- Environment variables take precedence when config values are null
- Documented in module docstring

---

## Recommendations for Future Work

1. ~~**Migrate to `logging` module**~~ — Done (v1.1, S-08).
2. ~~**Hostname/port validation**~~ — Done (v1.2, S-12/S-13).
3. ~~**Narrow exception handlers**~~ — Done (v1.2, S-17).
4. ~~**MQTT TLS/authentication**~~ — Done (v1.3, S-22).
5. ~~**XSS prevention**~~ — Done (v1.3, S-23).
6. ~~**File permissions hardening**~~ — Done (v1.3, S-29).
7. **Add type hints** — No type annotations exist in the codebase. Adding them improves IDE support and catches bugs.
8. **Expand test coverage** — `launcher.py`, `src/ui/menu.py`, and `src/monitoring/web_dashboard.py` have limited tests.
9. **Add authentication to web dashboard** — If the dashboard is ever exposed beyond localhost.
10. **Consider HTTPS** — For any non-localhost deployment, use TLS via reverse proxy or Flask-Talisman.
11. **Dependency auditing** — Run `pip-audit` or `safety check` periodically to detect known vulnerabilities.
12. **Pre-commit hooks** — Consider adding security linting (bandit/ruff S rules) as MeshForge does.
13. **SQLite encryption** — Consider sqlcipher for message queue encryption at rest.
14. **Rate limiting** — Add token bucket rate limiter on MQTT RX and dashboard API endpoints.
15. **Audit logging** — Add separate audit log stream for security events (connections, auth failures, access).
