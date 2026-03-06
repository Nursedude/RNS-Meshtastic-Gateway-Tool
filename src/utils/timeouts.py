"""
Centralized Timeout Constants — Single Source of Truth.

All timeout values used across the codebase should be imported from here.
Organized by context for easy discovery. Modeled on MeshForge's
utils/timeouts.py pattern.

Usage:
    from src.utils.timeouts import HEALTH_CHECK_INTERVAL, CIRCUIT_RECOVERY
"""

# =============================================================================
# Health Check
# =============================================================================

# Interval between active health probe checks
HEALTH_CHECK_INTERVAL = 30  # seconds

# =============================================================================
# Subprocess Timeouts
# =============================================================================

# Quick subprocess operations (systemctl is-active, pgrep, version checks)
SUBPROCESS_QUICK = 5  # seconds

# General subprocess timeout (CLI calls, systemctl commands)
SUBPROCESS_DEFAULT = 30  # seconds

# =============================================================================
# Network / TCP Timeouts
# =============================================================================

# TCP connection establishment (meshtasticd port 4403)
TCP_CONNECT = 10  # seconds

# TCP pre-flight probe (quick connectivity check)
TCP_PREFLIGHT = 2  # seconds

# =============================================================================
# Circuit Breaker
# =============================================================================

# Time before testing recovery from OPEN state
CIRCUIT_RECOVERY = 30.0  # seconds

# Default failure threshold before opening breaker
CIRCUIT_FAILURE_THRESHOLD = 5

# =============================================================================
# Reconnect Strategy
# =============================================================================

# Meshtastic radio reconnection defaults
RECONNECT_INITIAL_DELAY = 2.0  # seconds
RECONNECT_MAX_DELAY = 60.0  # seconds
RECONNECT_MULTIPLIER = 2.0
RECONNECT_JITTER = 0.15
RECONNECT_MAX_ATTEMPTS = 10

# Slow-start recovery duration after reconnect
SLOW_START_DURATION = 30.0  # seconds

# =============================================================================
# Thread Operations
# =============================================================================

# Default thread.join() timeout
THREAD_JOIN = 5.0  # seconds

# Thread join for threads with cleanup work
THREAD_JOIN_LONG = 15.0  # seconds

# =============================================================================
# TX Queue
# =============================================================================

# Maximum queued packets before backpressure
TX_QUEUE_MAXSIZE = 32

# Drain thread poll interval
TX_QUEUE_POLL = 0.5  # seconds

# =============================================================================
# TUI Menu
# =============================================================================

# Service status cache TTL (avoid shelling out on every menu redraw)
STATUS_CACHE_TTL = 10.0  # seconds

# =============================================================================
# Web Dashboard
# =============================================================================

# Dashboard auto-refresh interval
DASHBOARD_REFRESH = 30  # seconds

# =============================================================================
# Message Queue
# =============================================================================

# Dispatch loop poll interval (how often to check for PENDING messages)
MSG_QUEUE_POLL = 1.0  # seconds

# Maximum retry attempts before dead-lettering
MSG_QUEUE_MAX_RETRIES = 5

# Initial retry backoff delay
MSG_QUEUE_RETRY_INITIAL = 2.0  # seconds

# Maximum retry backoff delay
MSG_QUEUE_RETRY_MAX = 60.0  # seconds

# Retry backoff multiplier
MSG_QUEUE_RETRY_MULTIPLIER = 2.0

# Deduplication time window
MSG_QUEUE_DEDUP_WINDOW = 60.0  # seconds

# Dedup cleanup interval (purge expired hashes)
MSG_QUEUE_DEDUP_CLEANUP = 300.0  # seconds (every 5 min)

# =============================================================================
# Daemon / Watchdog
# =============================================================================

# Watchdog check interval
WATCHDOG_INTERVAL = 15.0  # seconds

# Consecutive failures before watchdog restarts service
WATCHDOG_FAILURES = 3

# Daemon stop timeout before SIGKILL
DAEMON_STOP_TIMEOUT = 10.0  # seconds

# =============================================================================
# MQTT Bridge
# =============================================================================

# MQTT broker connection timeout
MQTT_CONNECT_TIMEOUT = 10.0  # seconds

# MQTT auto-reconnect backoff bounds
MQTT_RECONNECT_MIN = 2.0  # seconds
MQTT_RECONNECT_MAX = 60.0  # seconds

# MQTT keepalive interval
MQTT_KEEPALIVE = 60  # seconds

# HTTP POST timeout for meshtasticd toradio API
HTTP_TORADIO_TIMEOUT = 10.0  # seconds

# Message deduplication time window
MQTT_DEDUP_WINDOW = 60.0  # seconds

# =============================================================================
# Node Tracker
# =============================================================================

# Auto-save interval for node persistence
NODE_TRACKER_SAVE_INTERVAL = 300.0  # seconds (every 5 min)

# Remove nodes not seen within this many days
NODE_TRACKER_STALE_DAYS = 7
