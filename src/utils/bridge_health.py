"""
Bridge Health Monitor — tracks gateway reliability metrics.

Based on MeshForge's gateway/bridge_health.py, adapted for a
single-radio gateway.

Monitors connection health, message flow, error rates, and delivery
confirmations.  Provides status summaries for the TUI dashboard and
diagnostics.

Key additions from MeshForge PRs:
- SubsystemState: granular per-subsystem health (healthy/degraded/
  disconnected/disabled) beyond a simple boolean.
- DeliveryTracker: tracks message delivery confirmations with bounded
  history and timeout detection.
- Zero-traffic anomaly detection: flags interfaces marked UP but with
  no messages flowing (green-but-dead pattern from MeshForge PR #1144).

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
import uuid
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


class SubsystemState(Enum):
    """Granular subsystem health (MeshForge pattern).

    More expressive than a simple connected boolean — distinguishes
    between actively healthy, degraded-but-working, disconnected,
    and administratively disabled subsystems.
    """
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DISCONNECTED = "disconnected"
    DISABLED = "disabled"


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

    # ── Subsystem State (MeshForge pattern) ─────────────────
    def get_subsystem_state(self, service: str) -> SubsystemState:
        """Return granular subsystem health beyond connected/disconnected.

        Considers connection state, error rate, and traffic flow to
        distinguish HEALTHY, DEGRADED, DISCONNECTED, and DISABLED.
        """
        with self._lock:
            connected = self._connected.get(service, False)

        if not connected:
            return SubsystemState.DISCONNECTED

        # Connected but high error rate → DEGRADED
        errors = self.get_error_rate(window_seconds=60)
        if sum(errors.values()) >= 5:
            return SubsystemState.DEGRADED

        return SubsystemState.HEALTHY

    # ── Zero-Traffic Detection (MeshForge PR #1144) ──────────
    def check_zero_traffic(self, min_uptime: float = 120.0) -> List[str]:
        """Detect green-but-dead interfaces: UP with no traffic.

        MeshForge PR #1144 pattern: interfaces appearing healthy but
        with zero messages flowing are often silently broken.

        Args:
            min_uptime: Minimum seconds connected before flagging.

        Returns:
            List of service names that are connected but have zero traffic.
        """
        now = time.time()
        zero_traffic: List[str] = []
        with self._lock:
            for service, connected in self._connected.items():
                if not connected:
                    continue
                connected_at = self._last_connected.get(service, now)
                uptime = now - connected_at
                if uptime < min_uptime:
                    continue
                # Check if any messages have flowed
                total_msgs = sum(self._messages_sent.values())
                if total_msgs == 0:
                    zero_traffic.append(service)
                    log.warning(
                        "Zero-traffic detected: %s is UP (%.0fs) but no "
                        "messages have been bridged — possible silent failure",
                        service, uptime,
                    )
        return zero_traffic

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
                        "subsystem_state": self.get_subsystem_state("meshtastic").value,
                        "uptime_percent": self.get_uptime_percent("meshtastic"),
                        "reconnect_count": self._connection_count.get("meshtastic", 0),
                        "last_connected": self._last_connected.get("meshtastic"),
                        "last_disconnected": self._last_disconnected.get("meshtastic"),
                    },
                    "rns": {
                        "connected": self._connected.get("rns", False),
                        "subsystem_state": self.get_subsystem_state("rns").value,
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
                "zero_traffic_services": self.check_zero_traffic(),
            }


# ── Delivery Tracker (MeshForge pattern) ────────────────────
@dataclass
class DeliveryRecord:
    """Tracks a single message delivery attempt."""
    delivery_id: str
    direction: str
    created_at: float
    status: str = "pending"  # pending, confirmed, failed, timed_out
    confirmed_at: Optional[float] = None
    error: Optional[str] = None


class DeliveryTracker:
    """Tracks message delivery confirmations with bounded history.

    MeshForge pattern: registers pending deliveries, updates on
    callbacks, and enforces timeout thresholds.  Maintains a bounded
    history to prevent memory overflow.

    Usage::

        tracker = DeliveryTracker(timeout=30.0)
        did = tracker.register("rns_to_mesh")
        # ... later, on confirmation callback:
        tracker.confirm(did)
        # ... or on failure:
        tracker.fail(did, "radio timeout")
        # Check stats:
        stats = tracker.get_stats()
    """

    def __init__(self, timeout: float = 30.0, max_history: int = 500):
        self._timeout = timeout
        self._max_history = max_history
        self._pending: Dict[str, DeliveryRecord] = {}
        self._history: deque = deque(maxlen=max_history)
        self._lock = threading.RLock()
        self._confirmed = 0
        self._failed = 0
        self._timed_out = 0

    def register(self, direction: str = "rns_to_mesh") -> str:
        """Register a new pending delivery. Returns a delivery ID."""
        delivery_id = uuid.uuid4().hex[:12]
        now = time.time()
        record = DeliveryRecord(
            delivery_id=delivery_id,
            direction=direction,
            created_at=now,
        )
        with self._lock:
            self._pending[delivery_id] = record
        return delivery_id

    def confirm(self, delivery_id: str) -> bool:
        """Mark a delivery as confirmed. Returns True if found."""
        now = time.time()
        with self._lock:
            record = self._pending.pop(delivery_id, None)
            if record is None:
                return False
            record.status = "confirmed"
            record.confirmed_at = now
            self._history.append(record)
            self._confirmed += 1
        return True

    def fail(self, delivery_id: str, error: str = "") -> bool:
        """Mark a delivery as failed. Returns True if found."""
        with self._lock:
            record = self._pending.pop(delivery_id, None)
            if record is None:
                return False
            record.status = "failed"
            record.error = error
            self._history.append(record)
            self._failed += 1
        return True

    def sweep_timeouts(self) -> int:
        """Move timed-out pending deliveries to history. Returns count."""
        now = time.time()
        timed_out = 0
        with self._lock:
            expired = [
                did for did, rec in self._pending.items()
                if now - rec.created_at > self._timeout
            ]
            for did in expired:
                record = self._pending.pop(did)
                record.status = "timed_out"
                self._history.append(record)
                self._timed_out += 1
                timed_out += 1
        if timed_out:
            log.debug("Delivery tracker: %d deliveries timed out", timed_out)
        return timed_out

    def get_stats(self) -> Dict[str, Any]:
        """Return delivery statistics snapshot."""
        self.sweep_timeouts()
        with self._lock:
            return {
                "pending": len(self._pending),
                "confirmed": self._confirmed,
                "failed": self._failed,
                "timed_out": self._timed_out,
                "total": self._confirmed + self._failed + self._timed_out,
                "confirmation_rate": (
                    self._confirmed / max(1, self._confirmed + self._failed + self._timed_out)
                ) * 100,
            }

    def get_recent(self, count: int = 10) -> List[Dict[str, Any]]:
        """Return recent delivery records."""
        with self._lock:
            records = list(self._history)[-count:]
        return [
            {
                "id": r.delivery_id,
                "direction": r.direction,
                "status": r.status,
                "created_at": r.created_at,
                "confirmed_at": r.confirmed_at,
                "error": r.error,
            }
            for r in records
        ]
