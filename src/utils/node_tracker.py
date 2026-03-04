"""
Node Tracker — maintains a registry of known mesh network nodes.

Subscribes to the event bus 'message' events and extracts node metadata
(node_id, timestamps, SNR, hop_count).  Persists to JSON for survival
across restarts.

Usage:
    from src.utils.node_tracker import NodeTracker

    tracker = NodeTracker()
    tracker.start()  # subscribes to event bus
    nodes = tracker.get_all_nodes()
    tracker.stop()   # unsubscribes, persists
"""

import json
import logging
import os
import threading
import time
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional

from src.utils.event_bus import event_bus
from src.utils.timeouts import NODE_TRACKER_SAVE_INTERVAL, NODE_TRACKER_STALE_DAYS

log = logging.getLogger("node_tracker")


@dataclass
class NodeInfo:
    """Metadata for a known mesh node."""
    node_id: str
    last_seen: float
    first_seen: float
    message_count: int = 0
    snr: Optional[float] = None
    hop_count: Optional[int] = None
    node_name: Optional[str] = None
    rssi: Optional[int] = None


def _default_nodes_path() -> str:
    """Return default persistence path: ~/.config/rns-gateway/nodes.json."""
    from src.utils.common import get_real_user_home
    config_dir = os.path.join(get_real_user_home(), ".config", "rns-gateway")
    os.makedirs(config_dir, exist_ok=True)
    return os.path.join(config_dir, "nodes.json")


class NodeTracker:
    """Thread-safe node registry with event bus integration and JSON persistence.

    Args:
        persist_path: Path to JSON file for persistence.
                      Defaults to ~/.config/rns-gateway/nodes.json.
        save_interval: Seconds between auto-persist writes.
        stale_days: Remove nodes not seen within this many days.
    """

    def __init__(
        self,
        persist_path: Optional[str] = None,
        save_interval: float = NODE_TRACKER_SAVE_INTERVAL,
        stale_days: int = NODE_TRACKER_STALE_DAYS,
    ):
        self._path = persist_path or _default_nodes_path()
        self._save_interval = save_interval
        self._stale_days = stale_days
        self._nodes: Dict[str, NodeInfo] = {}
        self._lock = threading.RLock()
        self._last_save = 0.0
        self._started = False
        self._load()

    def _load(self) -> None:
        """Load nodes from JSON persistence file."""
        try:
            with open(self._path, 'r') as f:
                data = json.load(f)
            with self._lock:
                for node_id, info in data.items():
                    self._nodes[node_id] = NodeInfo(
                        node_id=info.get("node_id", node_id),
                        last_seen=info.get("last_seen", 0),
                        first_seen=info.get("first_seen", 0),
                        message_count=info.get("message_count", 0),
                        snr=info.get("snr"),
                        hop_count=info.get("hop_count"),
                        node_name=info.get("node_name"),
                        rssi=info.get("rssi"),
                    )
            log.info("Loaded %d known node(s) from %s", len(self._nodes), self._path)
        except FileNotFoundError:
            log.debug("No existing nodes file at %s", self._path)
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            log.warning("Failed to load nodes from %s: %s", self._path, e)

    def save(self) -> None:
        """Write current node registry to JSON file."""
        with self._lock:
            data = {
                node_id: asdict(info)
                for node_id, info in self._nodes.items()
            }
        try:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            with open(self._path, 'w') as f:
                json.dump(data, f, indent=2)
            self._last_save = time.time()
        except OSError as e:
            log.warning("Failed to persist nodes to %s: %s", self._path, e)

    def _maybe_save(self) -> None:
        """Persist if enough time has elapsed since last write."""
        if time.time() - self._last_save >= self._save_interval:
            self.save()

    def update_node(
        self,
        node_id: str,
        snr: Optional[float] = None,
        hop_count: Optional[int] = None,
        node_name: Optional[str] = None,
        rssi: Optional[int] = None,
    ) -> None:
        """Update or create a node entry."""
        if not node_id:
            return
        now = time.time()
        with self._lock:
            if node_id in self._nodes:
                node = self._nodes[node_id]
                node.last_seen = now
                node.message_count += 1
                if snr is not None:
                    node.snr = snr
                if hop_count is not None:
                    node.hop_count = hop_count
                if node_name is not None:
                    node.node_name = node_name
                if rssi is not None:
                    node.rssi = rssi
            else:
                self._nodes[node_id] = NodeInfo(
                    node_id=node_id,
                    last_seen=now,
                    first_seen=now,
                    message_count=1,
                    snr=snr,
                    hop_count=hop_count,
                    node_name=node_name,
                    rssi=rssi,
                )
        self._maybe_save()

    def cleanup_stale(self, max_age_days: Optional[int] = None) -> int:
        """Remove nodes not seen within max_age_days. Returns count removed."""
        days = max_age_days if max_age_days is not None else self._stale_days
        cutoff = time.time() - (days * 86400)
        removed = 0
        with self._lock:
            stale = [nid for nid, n in self._nodes.items() if n.last_seen < cutoff]
            for nid in stale:
                del self._nodes[nid]
                removed += 1
        if removed:
            log.info("Removed %d stale node(s) (not seen in %d days)", removed, days)
        return removed

    def _on_message(self, event) -> None:
        """Event bus callback: update node info from message events."""
        if event.direction != "rx":
            return
        if not event.node_id:
            return
        snr = None
        hop_count = None
        node_name = None
        rssi = None
        if event.raw_data and isinstance(event.raw_data, dict):
            snr = event.raw_data.get("snr")
            hop_start = event.raw_data.get("hopStart")
            hop_limit = event.raw_data.get("hopLimit")
            if hop_start is not None and hop_limit is not None:
                hop_count = hop_start - hop_limit
            elif hop_start is not None:
                hop_count = hop_start
            node_name = event.raw_data.get("fromName")
            rssi = event.raw_data.get("rssi")
        self.update_node(
            node_id=event.node_id,
            snr=snr,
            hop_count=hop_count,
            node_name=node_name,
            rssi=rssi,
        )

    def start(self) -> None:
        """Subscribe to event bus for automatic node tracking."""
        if self._started:
            return
        event_bus.subscribe("message", self._on_message)
        self._started = True
        log.info("Node tracker started (%d known nodes)", len(self._nodes))

    def stop(self) -> None:
        """Unsubscribe from event bus and persist."""
        if not self._started:
            return
        event_bus.unsubscribe("message", self._on_message)
        self._started = False
        self.save()
        log.info("Node tracker stopped (%d nodes persisted)", len(self._nodes))

    def get_all_nodes(self) -> List[Dict]:
        """Return all known nodes as a list of dicts (sorted by last_seen desc)."""
        with self._lock:
            nodes = [asdict(n) for n in self._nodes.values()]
        nodes.sort(key=lambda n: n.get("last_seen", 0), reverse=True)
        return nodes

    def get_node(self, node_id: str) -> Optional[Dict]:
        """Return info for a specific node, or None."""
        with self._lock:
            node = self._nodes.get(node_id)
            return asdict(node) if node else None

    @property
    def node_count(self) -> int:
        """Number of known nodes."""
        with self._lock:
            return len(self._nodes)
