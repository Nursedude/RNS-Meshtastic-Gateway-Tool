# Security Review: RNS-Meshtastic Gateway Tool

**Latest review:** 2026-02-23 (v1.2)
**Previous review:** 2026-02-21 (v1.0 → v1.1)
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

## Recommendations for Future Work

1. ~~**Migrate to `logging` module**~~ — Done (v1.1, S-08).
2. ~~**Hostname/port validation**~~ — Done (v1.2, S-12/S-13).
3. ~~**Narrow exception handlers**~~ — Done (v1.2, S-17).
4. **Add type hints** — No type annotations exist in the codebase. Adding them improves IDE support and catches bugs.
5. **Expand test coverage** — `launcher.py`, `src/ui/menu.py`, and `src/monitoring/web_dashboard.py` have limited tests.
6. **Add authentication to web dashboard** — If the dashboard is ever exposed beyond localhost.
7. **Consider HTTPS** — For any non-localhost deployment, use TLS via reverse proxy or Flask-Talisman.
8. **Dependency auditing** — Run `pip-audit` or `safety check` periodically to detect known vulnerabilities.
9. **Pre-commit hooks** — Consider adding security linting (bandit/ruff S rules) as MeshForge does.
