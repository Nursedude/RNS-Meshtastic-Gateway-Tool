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
# Web Dashboard
# =============================================================================

# Dashboard auto-refresh interval
DASHBOARD_REFRESH = 30  # seconds
