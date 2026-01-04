"""
Unified node tracking for RNS and Meshtastic networks.

Provides a unified view of nodes across both networks with
position, telemetry, and status tracking.
"""

import json
import threading
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Callable, Any

# Default cache directory
DEFAULT_CACHE_DIR = Path.home() / ".config" / "rns-meshtastic-gateway"


@dataclass
class Position:
    """Geographic position with validation."""

    latitude: float = 0.0
    longitude: float = 0.0
    altitude: float = 0.0
    timestamp: float = field(default_factory=time.time)
    precision: int = 6

    def __post_init__(self):
        """Validate coordinates."""
        if not -90 <= self.latitude <= 90:
            self.latitude = max(-90, min(90, self.latitude))
        if not -180 <= self.longitude <= 180:
            self.longitude = max(-180, min(180, self.longitude))

    def is_valid(self) -> bool:
        """Check if position has valid non-zero coordinates."""
        return not (self.latitude == 0.0 and self.longitude == 0.0)

    def to_geojson(self) -> Dict[str, Any]:
        """Convert to GeoJSON point feature."""
        return {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [
                    round(self.longitude, self.precision),
                    round(self.latitude, self.precision),
                    round(self.altitude, 1)
                ]
            },
            "properties": {
                "timestamp": self.timestamp
            }
        }


@dataclass
class Telemetry:
    """Device telemetry data."""

    battery_level: Optional[float] = None  # Percentage
    voltage: Optional[float] = None  # Volts
    temperature: Optional[float] = None  # Celsius
    humidity: Optional[float] = None  # Percentage
    pressure: Optional[float] = None  # hPa
    uptime: Optional[int] = None  # Seconds
    channel_utilization: Optional[float] = None  # Percentage
    air_util_tx: Optional[float] = None  # Percentage
    timestamp: float = field(default_factory=time.time)


@dataclass
class UnifiedNode:
    """
    Represents a node from either RNS or Meshtastic network.

    Tracks identity, position, telemetry, and network-specific IDs.
    """

    # Identity
    unified_id: str  # Unique ID across both networks
    short_name: str = ""
    long_name: str = ""

    # Network-specific IDs
    meshtastic_id: Optional[str] = None  # !hexid format
    rns_address: Optional[str] = None  # RNS hash

    # Source network
    network: str = "unknown"  # "meshtastic", "rns", "both"

    # Position and telemetry
    position: Optional[Position] = None
    telemetry: Optional[Telemetry] = None

    # Radio metrics
    snr: Optional[float] = None
    rssi: Optional[float] = None
    hops: Optional[int] = None

    # Hardware info
    hardware_model: Optional[str] = None
    firmware_version: Optional[str] = None

    # Status
    is_online: bool = True
    is_gateway: bool = False
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)

    def update_last_seen(self) -> None:
        """Update the last seen timestamp."""
        self.last_seen = time.time()

    def mark_offline(self) -> None:
        """Mark the node as offline."""
        self.is_online = False

    def get_age(self) -> str:
        """Get human-readable age since last seen."""
        age_seconds = time.time() - self.last_seen

        if age_seconds < 60:
            return f"{int(age_seconds)}s ago"
        elif age_seconds < 3600:
            return f"{int(age_seconds / 60)}m ago"
        elif age_seconds < 86400:
            return f"{int(age_seconds / 3600)}h ago"
        else:
            return f"{int(age_seconds / 86400)}d ago"

    def has_position(self) -> bool:
        """Check if node has a valid position."""
        return self.position is not None and self.position.is_valid()

    def merge_from(self, other: "UnifiedNode") -> None:
        """Merge data from another node representation."""
        # Update IDs if we have new ones
        if other.meshtastic_id and not self.meshtastic_id:
            self.meshtastic_id = other.meshtastic_id
        if other.rns_address and not self.rns_address:
            self.rns_address = other.rns_address

        # Update network status
        if other.network != "unknown":
            if self.network == "unknown":
                self.network = other.network
            elif self.network != other.network:
                self.network = "both"

        # Update position if newer
        if other.position and other.position.is_valid():
            if not self.position or other.position.timestamp > self.position.timestamp:
                self.position = other.position

        # Update telemetry if newer
        if other.telemetry:
            if not self.telemetry or other.telemetry.timestamp > self.telemetry.timestamp:
                self.telemetry = other.telemetry

        # Update metrics
        if other.snr is not None:
            self.snr = other.snr
        if other.rssi is not None:
            self.rssi = other.rssi
        if other.hops is not None:
            self.hops = other.hops

        # Update names if better
        if other.long_name and len(other.long_name) > len(self.long_name):
            self.long_name = other.long_name
        if other.short_name and not self.short_name:
            self.short_name = other.short_name

        # Update status
        self.is_online = True
        self.update_last_seen()


class UnifiedNodeTracker:
    """
    Manages a collection of nodes across RNS and Meshtastic networks.

    Provides thread-safe operations, persistence, and event callbacks.
    """

    # Timeout for marking nodes offline (1 hour)
    OFFLINE_TIMEOUT = 3600

    def __init__(self, cache_dir: Optional[Path] = None):
        """
        Initialize the node tracker.

        Args:
            cache_dir: Directory for node cache persistence
        """
        self.cache_dir = cache_dir or DEFAULT_CACHE_DIR
        self.cache_file = self.cache_dir / "node_cache.json"
        self._nodes: Dict[str, UnifiedNode] = {}
        self._lock = threading.RLock()
        self._callbacks: List[Callable[[str, UnifiedNode], None]] = []

        # Load cached nodes
        self._load_cache()

    def _load_cache(self) -> None:
        """Load nodes from cache file."""
        if self.cache_file.exists():
            try:
                with open(self.cache_file) as f:
                    data = json.load(f)

                for node_id, node_data in data.items():
                    # Reconstruct nested objects
                    if "position" in node_data and node_data["position"]:
                        node_data["position"] = Position(**node_data["position"])
                    if "telemetry" in node_data and node_data["telemetry"]:
                        node_data["telemetry"] = Telemetry(**node_data["telemetry"])

                    self._nodes[node_id] = UnifiedNode(**node_data)
            except Exception:
                self._nodes = {}

    def _save_cache(self) -> None:
        """Save nodes to cache file."""
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

            data = {}
            for node_id, node in self._nodes.items():
                node_dict = asdict(node)
                data[node_id] = node_dict

            with open(self.cache_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def register_callback(
        self,
        callback: Callable[[str, UnifiedNode], None]
    ) -> None:
        """
        Register a callback for node updates.

        Args:
            callback: Function called with (event_type, node)
        """
        self._callbacks.append(callback)

    def _notify_callbacks(self, event_type: str, node: UnifiedNode) -> None:
        """Notify all registered callbacks."""
        for callback in self._callbacks:
            try:
                callback(event_type, node)
            except Exception:
                pass

    def add_or_update(self, node: UnifiedNode) -> UnifiedNode:
        """
        Add a new node or update an existing one.

        Args:
            node: Node to add or update

        Returns:
            The unified node (may be merged with existing)
        """
        with self._lock:
            if node.unified_id in self._nodes:
                existing = self._nodes[node.unified_id]
                existing.merge_from(node)
                self._notify_callbacks("update", existing)
                return existing
            else:
                self._nodes[node.unified_id] = node
                self._notify_callbacks("new", node)
                return node

    def get(self, unified_id: str) -> Optional[UnifiedNode]:
        """Get a node by its unified ID."""
        with self._lock:
            return self._nodes.get(unified_id)

    def get_by_meshtastic_id(self, mesh_id: str) -> Optional[UnifiedNode]:
        """Get a node by its Meshtastic ID."""
        with self._lock:
            for node in self._nodes.values():
                if node.meshtastic_id == mesh_id:
                    return node
            return None

    def get_by_rns_address(self, rns_addr: str) -> Optional[UnifiedNode]:
        """Get a node by its RNS address."""
        with self._lock:
            for node in self._nodes.values():
                if node.rns_address == rns_addr:
                    return node
            return None

    def remove(self, unified_id: str) -> bool:
        """Remove a node by its unified ID."""
        with self._lock:
            if unified_id in self._nodes:
                node = self._nodes.pop(unified_id)
                self._notify_callbacks("remove", node)
                return True
            return False

    def get_all(self) -> List[UnifiedNode]:
        """Get all tracked nodes."""
        with self._lock:
            return list(self._nodes.values())

    def get_meshtastic_nodes(self) -> List[UnifiedNode]:
        """Get nodes from Meshtastic network."""
        with self._lock:
            return [
                n for n in self._nodes.values()
                if n.network in ("meshtastic", "both")
            ]

    def get_rns_nodes(self) -> List[UnifiedNode]:
        """Get nodes from RNS network."""
        with self._lock:
            return [
                n for n in self._nodes.values()
                if n.network in ("rns", "both")
            ]

    def get_online_nodes(self) -> List[UnifiedNode]:
        """Get currently online nodes."""
        with self._lock:
            return [n for n in self._nodes.values() if n.is_online]

    def get_gateway_nodes(self) -> List[UnifiedNode]:
        """Get nodes marked as gateways."""
        with self._lock:
            return [n for n in self._nodes.values() if n.is_gateway]

    def get_nodes_with_position(self) -> List[UnifiedNode]:
        """Get nodes with valid positions."""
        with self._lock:
            return [n for n in self._nodes.values() if n.has_position()]

    def update_online_status(self) -> int:
        """
        Update online status based on last seen time.

        Returns:
            Number of nodes marked offline
        """
        now = time.time()
        marked_offline = 0

        with self._lock:
            for node in self._nodes.values():
                if node.is_online and (now - node.last_seen) > self.OFFLINE_TIMEOUT:
                    node.mark_offline()
                    self._notify_callbacks("offline", node)
                    marked_offline += 1

        return marked_offline

    def get_statistics(self) -> Dict[str, int]:
        """Get node statistics."""
        with self._lock:
            nodes = list(self._nodes.values())

        return {
            "total": len(nodes),
            "online": sum(1 for n in nodes if n.is_online),
            "offline": sum(1 for n in nodes if not n.is_online),
            "meshtastic": sum(1 for n in nodes if n.network in ("meshtastic", "both")),
            "rns": sum(1 for n in nodes if n.network in ("rns", "both")),
            "with_position": sum(1 for n in nodes if n.has_position()),
            "gateways": sum(1 for n in nodes if n.is_gateway),
        }

    def to_geojson(self) -> Dict[str, Any]:
        """Export nodes with positions to GeoJSON FeatureCollection."""
        features = []

        with self._lock:
            for node in self._nodes.values():
                if node.has_position():
                    feature = node.position.to_geojson()
                    feature["properties"].update({
                        "unified_id": node.unified_id,
                        "short_name": node.short_name,
                        "long_name": node.long_name,
                        "network": node.network,
                        "is_online": node.is_online,
                        "is_gateway": node.is_gateway,
                    })
                    features.append(feature)

        return {
            "type": "FeatureCollection",
            "features": features
        }

    def save(self) -> bool:
        """Persist nodes to cache."""
        try:
            self._save_cache()
            return True
        except Exception:
            return False

    def clear(self) -> None:
        """Clear all tracked nodes."""
        with self._lock:
            self._nodes.clear()
