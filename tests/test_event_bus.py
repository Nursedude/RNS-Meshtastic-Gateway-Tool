"""Tests for src/utils/event_bus.py — thread-safe pub/sub system."""

import threading
import time

from src.utils.event_bus import (
    EventBus,
    MessageEvent,
    ServiceEvent,
    emit_message,
    emit_service_status,
    event_bus,
)


class TestEventBus:
    """Core EventBus functionality."""

    def test_subscribe_and_emit_sync(self):
        bus = EventBus()
        received = []
        bus.subscribe("test", lambda e: received.append(e))
        bus.emit_sync("test", "hello")
        assert received == ["hello"]

    def test_unsubscribe(self):
        bus = EventBus()
        received = []
        cb = lambda e: received.append(e)  # noqa: E731
        bus.subscribe("test", cb)
        bus.unsubscribe("test", cb)
        bus.emit_sync("test", "hello")
        assert received == []

    def test_unsubscribe_nonexistent_is_noop(self):
        bus = EventBus()
        bus.unsubscribe("test", lambda e: None)  # no error

    def test_emit_no_subscribers(self):
        bus = EventBus()
        bus.emit_sync("test", "hello")  # no error

    def test_multiple_subscribers(self):
        bus = EventBus()
        results = []
        bus.subscribe("test", lambda e: results.append("a"))
        bus.subscribe("test", lambda e: results.append("b"))
        bus.emit_sync("test", "data")
        assert sorted(results) == ["a", "b"]

    def test_duplicate_subscribe_ignored(self):
        bus = EventBus()
        received = []
        cb = lambda e: received.append(e)  # noqa: E731
        bus.subscribe("test", cb)
        bus.subscribe("test", cb)
        assert bus.get_subscriber_count("test") == 1

    def test_different_event_types(self):
        bus = EventBus()
        type_a = []
        type_b = []
        bus.subscribe("a", lambda e: type_a.append(e))
        bus.subscribe("b", lambda e: type_b.append(e))
        bus.emit_sync("a", "hello")
        assert type_a == ["hello"]
        assert type_b == []

    def test_clear_subscribers_specific(self):
        bus = EventBus()
        bus.subscribe("a", lambda e: None)
        bus.subscribe("b", lambda e: None)
        bus.clear_subscribers("a")
        assert bus.get_subscriber_count("a") == 0
        assert bus.get_subscriber_count("b") == 1

    def test_clear_subscribers_all(self):
        bus = EventBus()
        bus.subscribe("a", lambda e: None)
        bus.subscribe("b", lambda e: None)
        bus.clear_subscribers()
        assert bus.get_subscriber_count("a") == 0
        assert bus.get_subscriber_count("b") == 0

    def test_get_subscriber_count_empty(self):
        bus = EventBus()
        assert bus.get_subscriber_count("nonexistent") == 0

    def test_callback_exception_does_not_crash(self):
        bus = EventBus()
        bus.subscribe("test", lambda e: 1 / 0)
        bus.emit_sync("test", "data")  # should not raise

    def test_async_emit(self):
        bus = EventBus()
        received = threading.Event()
        bus.subscribe("test", lambda e: received.set())
        bus.emit("test", "data")
        assert received.wait(timeout=2.0)

    def test_shutdown(self):
        bus = EventBus()
        bus.subscribe("test", lambda e: None)
        bus.shutdown()
        assert bus.get_subscriber_count("test") == 0
        # emit after shutdown should not raise
        bus.emit("test", "data")


class TestMessageEvent:
    def test_str_rx(self):
        event = MessageEvent(direction="rx", content="Hello world", node_id="!abc123")
        s = str(event)
        assert "abc123" in s
        assert "Hello" in s

    def test_str_tx(self):
        event = MessageEvent(direction="tx", content="Outbound")
        s = str(event)
        assert "Outbound" in s

    def test_defaults(self):
        event = MessageEvent(direction="rx", content="test")
        assert event.node_id == ""
        assert event.channel == 0
        assert event.network == ""
        assert event.raw_data is None


class TestServiceEvent:
    def test_creation(self):
        event = ServiceEvent(service_name="meshtastic", available=True, message="connected")
        assert event.service_name == "meshtastic"
        assert event.available is True
        assert event.message == "connected"


class TestConvenienceFunctions:
    def test_emit_message(self):
        received = []
        event_bus.subscribe("message", lambda e: received.append(e))
        try:
            emit_message(direction="tx", content="test_msg", network="meshtastic")
            time.sleep(0.2)
            assert len(received) == 1
            assert received[0].direction == "tx"
            assert received[0].content == "test_msg"
        finally:
            event_bus.clear_subscribers("message")

    def test_emit_service_status(self):
        received = []
        event_bus.subscribe("service", lambda e: received.append(e))
        try:
            emit_service_status("rns", True, "running")
            time.sleep(0.2)
            assert len(received) == 1
            assert received[0].service_name == "rns"
            assert received[0].available is True
        finally:
            event_bus.clear_subscribers("service")
