"""Tests for the Node Tracker (Session 4)."""

import json
import time
import threading

import pytest

from src.utils.node_tracker import NodeTracker, NodeInfo
from src.utils.event_bus import EventBus, MessageEvent


# ── Fixtures ──────────────────────────────────────────────────

@pytest.fixture
def tracker(tmp_path):
    """Create a NodeTracker with temp persistence path."""
    path = str(tmp_path / "nodes.json")
    return NodeTracker(persist_path=path, save_interval=9999)


@pytest.fixture
def event_bus_isolated():
    """Create an isolated EventBus for testing."""
    return EventBus()


# ── NodeInfo Tests ────────────────────────────────────────────

class TestNodeInfo:
    def test_dataclass_defaults(self):
        info = NodeInfo(node_id="!abc", last_seen=1000, first_seen=900)
        assert info.node_id == "!abc"
        assert info.message_count == 0
        assert info.snr is None
        assert info.hop_count is None
        assert info.node_name is None
        assert info.rssi is None


# ── Init / Load Tests ─────────────────────────────────────────

class TestNodeTrackerInit:
    def test_empty_registry(self, tracker):
        assert tracker.node_count == 0
        assert tracker.get_all_nodes() == []

    def test_handles_missing_file(self, tmp_path):
        path = str(tmp_path / "nonexistent" / "nodes.json")
        t = NodeTracker(persist_path=path)
        assert t.node_count == 0

    def test_handles_corrupt_json(self, tmp_path):
        path = tmp_path / "nodes.json"
        path.write_text("{bad json!!")
        t = NodeTracker(persist_path=str(path))
        assert t.node_count == 0

    def test_loads_existing_nodes(self, tmp_path):
        path = tmp_path / "nodes.json"
        data = {
            "!node1": {
                "node_id": "!node1",
                "last_seen": time.time(),
                "first_seen": time.time() - 100,
                "message_count": 5,
                "snr": 7.5,
            }
        }
        path.write_text(json.dumps(data))
        t = NodeTracker(persist_path=str(path))
        assert t.node_count == 1
        node = t.get_node("!node1")
        assert node is not None
        assert node["message_count"] == 5
        assert node["snr"] == 7.5


# ── Update Tests ──────────────────────────────────────────────

class TestUpdateNode:
    def test_creates_new_node(self, tracker):
        tracker.update_node("!abc123", snr=8.0, hop_count=2)
        assert tracker.node_count == 1
        node = tracker.get_node("!abc123")
        assert node["snr"] == 8.0
        assert node["hop_count"] == 2
        assert node["message_count"] == 1

    def test_updates_existing_node(self, tracker):
        tracker.update_node("!abc123", snr=5.0)
        tracker.update_node("!abc123", snr=9.0, node_name="MyNode")
        assert tracker.node_count == 1
        node = tracker.get_node("!abc123")
        assert node["snr"] == 9.0
        assert node["node_name"] == "MyNode"
        assert node["message_count"] == 2

    def test_increments_message_count(self, tracker):
        for _ in range(10):
            tracker.update_node("!counter")
        assert tracker.get_node("!counter")["message_count"] == 10

    def test_preserves_first_seen(self, tracker):
        tracker.update_node("!abc")
        first = tracker.get_node("!abc")["first_seen"]
        time.sleep(0.01)
        tracker.update_node("!abc")
        assert tracker.get_node("!abc")["first_seen"] == first

    def test_empty_node_id_ignored(self, tracker):
        tracker.update_node("")
        assert tracker.node_count == 0

    def test_none_values_not_overwritten(self, tracker):
        tracker.update_node("!x", snr=5.0, rssi=-70)
        tracker.update_node("!x")  # no snr/rssi
        node = tracker.get_node("!x")
        assert node["snr"] == 5.0
        assert node["rssi"] == -70


# ── Persistence Tests ─────────────────────────────────────────

class TestPersistence:
    def test_save_writes_json(self, tracker, tmp_path):
        tracker.update_node("!saved", snr=3.0)
        tracker.save()
        path = tmp_path / "nodes.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert "!saved" in data
        assert data["!saved"]["snr"] == 3.0

    def test_survives_restart(self, tmp_path):
        path = str(tmp_path / "nodes.json")
        t1 = NodeTracker(persist_path=path)
        t1.update_node("!persist", node_name="TestNode")
        t1.save()

        t2 = NodeTracker(persist_path=path)
        assert t2.node_count == 1
        node = t2.get_node("!persist")
        assert node["node_name"] == "TestNode"


# ── Get Nodes Tests ───────────────────────────────────────────

class TestGetNodes:
    def test_get_all_sorted_by_last_seen(self, tracker):
        tracker.update_node("!old")
        time.sleep(0.01)
        tracker.update_node("!new")
        nodes = tracker.get_all_nodes()
        assert nodes[0]["node_id"] == "!new"
        assert nodes[1]["node_id"] == "!old"

    def test_get_node_unknown_returns_none(self, tracker):
        assert tracker.get_node("!nonexistent") is None

    def test_node_count(self, tracker):
        tracker.update_node("!a")
        tracker.update_node("!b")
        tracker.update_node("!c")
        assert tracker.node_count == 3


# ── Stale Cleanup Tests ──────────────────────────────────────

class TestCleanupStale:
    def test_removes_old_nodes(self, tracker):
        tracker.update_node("!recent")
        # Manually set old timestamp
        tracker._nodes["!old"] = NodeInfo(
            node_id="!old",
            last_seen=time.time() - (10 * 86400),  # 10 days ago
            first_seen=time.time() - (10 * 86400),
        )
        removed = tracker.cleanup_stale(max_age_days=7)
        assert removed == 1
        assert tracker.get_node("!old") is None
        assert tracker.get_node("!recent") is not None

    def test_keeps_recent_nodes(self, tracker):
        tracker.update_node("!keep")
        removed = tracker.cleanup_stale(max_age_days=7)
        assert removed == 0
        assert tracker.node_count == 1


# ── Event Bus Integration Tests ───────────────────────────────

class TestEventBusIntegration:
    def test_rx_message_updates_node(self, tracker):
        # Manually call _on_message with a MessageEvent
        event = MessageEvent(
            direction="rx",
            content="test",
            node_id="!mesh01",
            network="meshtastic",
            raw_data={"snr": 6.5, "rssi": -80, "fromName": "Node1"},
        )
        tracker._on_message(event)
        node = tracker.get_node("!mesh01")
        assert node is not None
        assert node["snr"] == 6.5
        assert node["rssi"] == -80
        assert node["node_name"] == "Node1"

    def test_tx_message_ignored(self, tracker):
        event = MessageEvent(
            direction="tx",
            content="outgoing",
            node_id="!outgoing",
        )
        tracker._on_message(event)
        assert tracker.node_count == 0

    def test_empty_node_id_ignored(self, tracker):
        event = MessageEvent(
            direction="rx",
            content="test",
            node_id="",
        )
        tracker._on_message(event)
        assert tracker.node_count == 0

    def test_hop_count_from_raw_data(self, tracker):
        event = MessageEvent(
            direction="rx",
            content="test",
            node_id="!hopper",
            raw_data={"hopStart": 3, "hopLimit": 1},
        )
        tracker._on_message(event)
        node = tracker.get_node("!hopper")
        assert node["hop_count"] == 2  # 3 - 1

    def test_start_stop(self, tracker):
        tracker.start()
        assert tracker._started is True
        tracker.stop()
        assert tracker._started is False

    def test_start_idempotent(self, tracker):
        tracker.start()
        tracker.start()  # should not raise
        assert tracker._started is True
        tracker.stop()

    def test_stop_idempotent(self, tracker):
        tracker.stop()  # not started, should not raise
        assert tracker._started is False


# ── Thread Safety Tests ───────────────────────────────────────

class TestThreadSafety:
    def test_concurrent_updates(self, tracker):
        errors = []

        def update_batch(prefix, count):
            try:
                for i in range(count):
                    tracker.update_node(f"{prefix}_{i}", snr=float(i))
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=update_batch, args=(f"t{t}", 20))
            for t in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors
        assert tracker.node_count == 100  # 5 threads x 20 nodes
