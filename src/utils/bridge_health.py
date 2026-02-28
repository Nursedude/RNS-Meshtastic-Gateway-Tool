"""
Bridge Health Monitor — tracks gateway reliability metrics.

Based on MeshForge's gateway/bridge_health.py, simplified for a
single-radio gateway (no MeshCore, no LXMF delivery tracking).

Monitors connection health, message flow, and error rates.  Provides
status summaries for the TUI dashboard and diagnostics.

Usage:
    from src.utils.bridge_health import BridgeHealthMonitor, BridgeStatus

    health = BridgeHealthMonitor()
    health.record_connection_event("meshtastic", "connected")
    health.record_message_sent("mesh_to_rns")
    print(health.get_summary())

    if health.get_bridge_status() == BridgeStatus.DEGRADED:
        print("Warning:", health.get_degraded_reason())
"""
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

log = logging.getLogger("bridge_health")


# ── Enums ────────────────────────────────────────────────────
class BridgeStatus(Enum):
    """Bridge operational status.

    HEALTHY:  Both networks connected, error rate acceptable.
    DEGRADED: One network down or high error rate.
    OFFLINE:  Both networks disconnected.
    """
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    OFFLINE = "offline"


# ── Error Classification ─────────────────────────────────────
PERMANENT_ERROR_PATTERNS = [
    "signal only works in main thread",
    "reinitialise",
    "already running",
    "permission denied",
    "no such device",
    "module not found",
    "import error",
]

TRANSIENT_ERROR_PATTERNS = [
    "connection reset",
    "connection refused",
    "broken pipe",
    "timeout",
    "timed out",
    "temporarily unavailable",
    "network unreachable",
    "no route to host",
    "address already in use",
    "serial port busy",
    "device disconnected",
    "usb disconnect",
    "resource temporarily unavailable",
]


def classify_error(error: Exception) -> str:
    """Classify an error as transient or permanent.

    Args:
        error: The exception to classify.

    Returns:
        "transient", "permanent", or "unknown".
    """
    msg = str(error).lower()

    for pattern in PERMANENT_ERROR_PATTERNS:
        if pattern in msg:
            return "permanent"

    for pattern in TRANSIENT_ERROR_PATTERNS:
        if pattern in msg:
            return "transient"

    if isinstance(error, (ConnectionError, BrokenPipeError,
                          ConnectionResetError, TimeoutError, OSError)):
        return "transient"

    return "unknown"


# ── Internal Event Dataclasses ───────────────────────────────
@dataclass
class ConnectionEvent:
    """A connection state change event."""
    timestamp: float
    service: str
    event: str
    detail: str = ""


@dataclass
class ErrorEvent:
    """A categorised error event."""
    timestamp: float
    service: str
    category: str
    message: str
    is_retriable: bool = True


# ── Bridge Health Monitor ────────────────────────────────────
class BridgeHealthMonitor:
    """Monitors bridge health and collects operational metrics.

    Thread-safe.  Maintains rolling windows of events for analysis
    without unbounded memory growth.
    """

    def __init__(self, window_size: int = 1000):
        self._lock = threading.RLock()
        self._window_size = window_size

        # Connection state
        self._connected: Dict[str, bool] = {
            "meshtastic": False,
            "rns": False,
        }
        self._last_connected: Dict[str, float] = {}
        self._last_disconnected: Dict[str, float] = {}
        self._connection_count: Dict[str, int] = {
            "meshtastic": 0,
            "rns": 0,
        }

        # Message counters
        self._messages_sent: Dict[str, int] = {
            "mesh_to_rns": 0,
            "rns_to_mesh": 0,
        }
        self._messages_failed: Dict[str, int] = {
            "mesh_to_rns": 0,
            "rns_to_mesh": 0,
        }
        self._messages_requeued: int = 0

        # Rolling event windows
        self._connection_events: deque = deque(maxlen=window_size)
        self._error_events: deque = deque(maxlen=window_size)
        self._message_timestamps: deque = deque(maxlen=window_size)

        # Timing
        self._start_time: float = time.time()
        self._uptime_seconds: Dict[str, float] = {
            "meshtastic": 0.0,
            "rns": 0.0,
        }

    # ── Connection Events ────────────────────────────────────
    def record_connection_event(
        self, service: str, event: str, detail: str = "",
    ) -> None:
        """Record a connection state change.

        Args:
            service: "meshtastic" or "rns".
            event:   "connected", "disconnected", "error", "retry".
            detail:  Optional detail message.
        """
        now = time.time()
        with self._lock:
            self._connection_events.append(
                ConnectionEvent(timestamp=now, service=service,
                                event=event, detail=detail)
            )

            if event == "connected":
                if not self._connected.get(service, False):
                    self._connected[service] = True
                    self._last_connected[service] = now
                    self._connection_count[service] = (
                        self._connection_count.get(service, 0) + 1
                    )
            elif event in ("disconnected", "error"):
                if self._connected.get(service, False):
                    connected_at = self._last_connected.get(service, now)
                    svc_uptime = self._uptime_seconds.get(service, 0.0)
                    self._uptime_seconds[service] = svc_uptime + (now - connected_at)
                self._connected[service] = False
                self._last_disconnected[service] = now

    # ── Message Tracking ─────────────────────────────────────
    def record_message_sent(self, direction: str) -> None:
        """Record a successfully bridged message.

        Args:
            direction: "mesh_to_rns" or "rns_to_mesh".
        """
        now = time.time()
        with self._lock:
            self._messages_sent[direction] = (
                self._messages_sent.get(direction, 0) + 1
            )
            self._message_timestamps.append(now)

    def record_message_failed(
        self, direction: str, requeued: bool = False,
    ) -> None:
        """Record a failed message send.

        Args:
            direction: "mesh_to_rns" or "rns_to_mesh".
            requeued:  Whether the message was saved for later retry.
        """
        with self._lock:
            self._messages_failed[direction] = (
                self._messages_failed.get(direction, 0) + 1
            )
            if requeued:
                self._messages_requeued += 1

    # ── Error Recording ──────────────────────────────────────
    def record_error(self, service: str, error: Exception) -> str:
        """Record and classify an error.

        Args:
            service: "meshtastic" or "rns".
            error:   The exception that occurred.

        Returns:
            The error category ("transient", "permanent", "unknown").
        """
        category = classify_error(error)
        now = time.time()
        with self._lock:
            self._error_events.append(ErrorEvent(
                timestamp=now,
                service=service,
                category=category,
                message=str(error)[:200],
                is_retriable=(category == "transient"),
            ))
        return category

    # ── Rate Calculations ────────────────────────────────────
    def get_message_rate(self, window_seconds: int = 300) -> float:
        """Messages per minute over a time window."""
        now = time.time()
        cutoff = now - window_seconds
        with self._lock:
            recent = sum(1 for t in self._message_timestamps if t >= cutoff)
        return (recent / window_seconds) * 60 if window_seconds > 0 else 0

    def get_error_rate(self, window_seconds: int = 300) -> Dict[str, int]:
        """Error counts by category in a time window."""
        now = time.time()
        cutoff = now - window_seconds
        counts: Dict[str, int] = {"transient": 0, "permanent": 0, "unknown": 0}
        with self._lock:
            for ev in self._error_events:
                if ev.timestamp >= cutoff:
                    counts[ev.category] = counts.get(ev.category, 0) + 1
        return counts

    # ── Uptime ───────────────────────────────────────────────
    def get_uptime_percent(self, service: str) -> float:
        """Connection uptime percentage for a service (0–100)."""
        now = time.time()
        total_time = now - self._start_time
        if total_time <= 0:
            return 0.0

        with self._lock:
            uptime = self._uptime_seconds.get(service, 0.0)
            if self._connected.get(service, False):
                connected_at = self._last_connected.get(service, now)
                uptime += now - connected_at

        return min(100.0, (uptime / total_time) * 100)

    # ── Bridge Status ────────────────────────────────────────
    def get_bridge_status(self) -> BridgeStatus:
        """Cross-network health assessment.

        HEALTHY:  Both networks connected, error rate < 10/min.
        DEGRADED: One network down or high error rate.
        OFFLINE:  Both networks disconnected.
        """
        with self._lock:
            connected_count = sum(
                1 for v in self._connected.values() if v
            )

        if connected_count == 0:
            return BridgeStatus.OFFLINE

        errors = self.get_error_rate(window_seconds=60)
        high_error_rate = sum(errors.values()) >= 10

        if connected_count == len(self._connected) and not high_error_rate:
            return BridgeStatus.HEALTHY

        return BridgeStatus.DEGRADED

    def get_degraded_reason(self) -> Optional[str]:
        """Human-readable reason if bridge is not fully healthy."""
        with self._lock:
            mesh_up = self._connected.get("meshtastic", False)
            rns_up = self._connected.get("rns", False)

        errors = self.get_error_rate(window_seconds=60)
        error_count = sum(errors.values())

        reasons: List[str] = []
        if not mesh_up:
            reasons.append("Meshtastic disconnected")
        if not rns_up:
            reasons.append("RNS disconnected")
        if error_count >= 10:
            reasons.append("High error rate (%d/min)" % error_count)

        return "; ".join(reasons) if reasons else None

    # ── Quick Checks ─────────────────────────────────────────
    def is_healthy(self) -> bool:
        """Quick health check: at least one connection active, low errors."""
        with self._lock:
            any_connected = any(self._connected.values())
        errors = self.get_error_rate(window_seconds=60)
        return any_connected and sum(errors.values()) < 10

    def should_pause_bridging(self) -> bool:
        """True if bridging should be paused (both offline or critical errors)."""
        if self.get_bridge_status() == BridgeStatus.OFFLINE:
            return True
        errors = self.get_error_rate(window_seconds=60)
        return sum(errors.values()) > 20

    # ── Summary ──────────────────────────────────────────────
    def get_summary(self) -> Dict[str, Any]:
        """Comprehensive health summary for dashboards/API."""
        now = time.time()
        with self._lock:
            return {
                "uptime_seconds": now - self._start_time,
                "connections": {
                    "meshtastic": {
                        "connected": self._connected.get("meshtastic", False),
                        "uptime_percent": self.get_uptime_percent("meshtastic"),
                        "reconnect_count": self._connection_count.get("meshtastic", 0),
                        "last_connected": self._last_connected.get("meshtastic"),
                        "last_disconnected": self._last_disconnected.get("meshtastic"),
                    },
                    "rns": {
                        "connected": self._connected.get("rns", False),
                        "uptime_percent": self.get_uptime_percent("rns"),
                        "reconnect_count": self._connection_count.get("rns", 0),
                        "last_connected": self._last_connected.get("rns"),
                        "last_disconnected": self._last_disconnected.get("rns"),
                    },
                },
                "messages": {
                    "mesh_to_rns": self._messages_sent.get("mesh_to_rns", 0),
                    "rns_to_mesh": self._messages_sent.get("rns_to_mesh", 0),
                    "failed_mesh_to_rns": self._messages_failed.get("mesh_to_rns", 0),
                    "failed_rns_to_mesh": self._messages_failed.get("rns_to_mesh", 0),
                    "requeued": self._messages_requeued,
                    "rate_per_min": self.get_message_rate(),
                },
                "errors": self.get_error_rate(),
                "bridge_status": self.get_bridge_status().value,
            }
