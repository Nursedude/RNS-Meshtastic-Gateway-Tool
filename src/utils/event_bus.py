"""
Event Bus — Thread-safe pub/sub for decoupled component communication.

Adapted from MeshForge's utils/event_bus.py. Primary use case: gateway
RX/TX messages → UI panel updates without tight coupling.

Usage:
    from src.utils.event_bus import event_bus, MessageEvent

    # Publisher (in gateway driver):
    event_bus.emit('message', MessageEvent(
        direction='rx', content='Hello from mesh', node_id='!abc123',
    ))

    # Subscriber (in dashboard):
    def on_message(event):
        display(event)
    event_bus.subscribe('message', on_message)

    # Cleanup:
    event_bus.unsubscribe('message', on_message)
"""

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

log = logging.getLogger(__name__)


@dataclass
class MessageEvent:
    """Event representing a mesh network message (TX or RX)."""
    direction: str  # 'tx' or 'rx'
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    node_id: str = ""
    channel: int = 0
    network: str = ""  # 'meshtastic', 'rns', or 'bridge'
    raw_data: Optional[Dict] = None

    def __str__(self):
        arrow = "\u2190" if self.direction == "rx" else "\u2192"
        source = self.node_id or "unknown"
        time_str = self.timestamp.strftime("%H:%M:%S")
        return f"[{time_str}] {arrow} {source}: {self.content[:50]}"


@dataclass
class ServiceEvent:
    """Event representing a service status change."""
    service_name: str
    available: bool
    message: str
    timestamp: datetime = field(default_factory=datetime.now)


class EventBus:
    """Thread-safe event bus with bounded thread pool dispatch.

    Subscribers are called in worker threads to avoid blocking publishers.
    Uses a bounded ThreadPoolExecutor (4 workers) to prevent thread explosion.
    """

    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = {}
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(
            max_workers=4, thread_name_prefix="eventbus",
        )

    def subscribe(self, event_type: str, callback: Callable) -> None:
        """Subscribe to an event type."""
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            if callback not in self._subscribers[event_type]:
                self._subscribers[event_type].append(callback)

    def unsubscribe(self, event_type: str, callback: Callable) -> None:
        """Unsubscribe from an event type."""
        with self._lock:
            if event_type in self._subscribers:
                try:
                    self._subscribers[event_type].remove(callback)
                except ValueError:
                    pass

    def emit(self, event_type: str, event: Any) -> None:
        """Emit an event to all subscribers (non-blocking via thread pool)."""
        with self._lock:
            subscribers = self._subscribers.get(event_type, []).copy()

        if not subscribers:
            return

        for callback in subscribers:
            try:
                self._executor.submit(self._safe_call, callback, event)
            except RuntimeError:
                # Executor shut down during cleanup
                pass

    def emit_sync(self, event_type: str, event: Any) -> None:
        """Emit an event synchronously (for testing or simple cases)."""
        with self._lock:
            subscribers = self._subscribers.get(event_type, []).copy()

        for callback in subscribers:
            self._safe_call(callback, event)

    def _safe_call(self, callback: Callable, event: Any) -> None:
        """Call a callback with exception handling."""
        try:
            callback(event)
        except Exception as exc:
            log.error("Error in event callback %s: %s", callback.__name__, exc)

    def clear_subscribers(self, event_type: Optional[str] = None) -> None:
        """Clear subscribers for an event type, or all subscribers."""
        with self._lock:
            if event_type:
                self._subscribers[event_type] = []
            else:
                self._subscribers.clear()

    def get_subscriber_count(self, event_type: str) -> int:
        """Get the number of subscribers for an event type."""
        with self._lock:
            return len(self._subscribers.get(event_type, []))

    def shutdown(self) -> None:
        """Shut down the thread pool executor.

        Call during gateway cleanup to release thread pool resources.
        """
        with self._lock:
            self._subscribers.clear()
        self._executor.shutdown(wait=True, cancel_futures=True)


# Global singleton
event_bus = EventBus()


# =============================================================================
# Convenience functions
# =============================================================================

def emit_message(
    direction: str,
    content: str,
    node_id: str = "",
    channel: int = 0,
    network: str = "",
    raw_data: Optional[Dict] = None,
) -> None:
    """Emit a message event (TX or RX)."""
    event = MessageEvent(
        direction=direction,
        content=content,
        node_id=node_id,
        channel=channel,
        network=network,
        raw_data=raw_data,
    )
    event_bus.emit('message', event)


def emit_service_status(
    service_name: str,
    available: bool,
    message: str,
) -> None:
    """Emit a service status event."""
    event = ServiceEvent(
        service_name=service_name,
        available=available,
        message=message,
    )
    event_bus.emit('service', event)
