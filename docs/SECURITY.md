# Security Review: RNS-Meshtastic Gateway Tool

**Date:** 2026-02-21
**Version reviewed:** 1.0
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

## Recommendations for Future Work

1. ~~**Migrate to `logging` module**~~ — Done. See S-08 remediation.
2. **Add type hints** — No type annotations exist in the codebase. Adding them improves IDE support and catches bugs.
3. **Expand test coverage** — `launcher.py`, `src/ui/menu.py`, and `src/monitoring/web_dashboard.py` have no tests.
4. **Add authentication to web dashboard** — If the dashboard is ever exposed beyond localhost.
5. **Consider HTTPS** — For any non-localhost deployment, use TLS via reverse proxy or Flask-Talisman.
6. **Dependency auditing** — Run `pip-audit` or `safety check` periodically to detect known vulnerabilities.
