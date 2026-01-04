"""
Node monitoring for RNS-Meshtastic Gateway Tool.

Provides real-time node monitoring via TCP connection to meshtasticd,
with support for multiple output formats and continuous watch mode.
"""

import json
import socket
import time
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, List, Any, Callable

from ..gateway.node_tracker import UnifiedNodeTracker, UnifiedNode, Position, Telemetry


@dataclass
class MonitorConfig:
    """Node monitor configuration."""

    host: str = "localhost"
    port: int = 4403
    update_interval: float = 5.0  # seconds
    connection_timeout: float = 10.0


class NodeMonitor:
    """
    Real-time node monitoring via meshtasticd TCP connection.

    Provides sudo-free monitoring by connecting to the meshtasticd
    TCP API and polling for node information.
    """

    # Config file location
    CONFIG_PATH = Path.home() / ".config" / "rns-meshtastic-gateway" / "monitor.json"

    def __init__(self, config: Optional[MonitorConfig] = None):
        """
        Initialize the node monitor.

        Args:
            config: Monitor configuration
        """
        self.config = config or self._load_config()
        self._socket: Optional[socket.socket] = None
        self._connected = False
        self._running = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._node_tracker = UnifiedNodeTracker()

        # Callbacks
        self._update_callbacks: List[Callable[[List[UnifiedNode]], None]] = []
        self._error_callbacks: List[Callable[[str], None]] = []

    def _load_config(self) -> MonitorConfig:
        """Load configuration from file."""
        if self.CONFIG_PATH.exists():
            try:
                with open(self.CONFIG_PATH) as f:
                    data = json.load(f)
                return MonitorConfig(**data)
            except Exception:
                pass
        return MonitorConfig()

    def save_config(self) -> bool:
        """Save configuration to file."""
        try:
            self.CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(self.CONFIG_PATH, "w") as f:
                json.dump({
                    "host": self.config.host,
                    "port": self.config.port,
                    "update_interval": self.config.update_interval,
                    "connection_timeout": self.config.connection_timeout,
                }, f, indent=2)
            return True
        except Exception:
            return False

    def register_update_callback(
        self,
        callback: Callable[[List[UnifiedNode]], None]
    ) -> None:
        """Register callback for node updates."""
        self._update_callbacks.append(callback)

    def register_error_callback(
        self,
        callback: Callable[[str], None]
    ) -> None:
        """Register callback for errors."""
        self._error_callbacks.append(callback)

    def _notify_update(self, nodes: List[UnifiedNode]) -> None:
        """Notify callbacks of node update."""
        for callback in self._update_callbacks:
            try:
                callback(nodes)
            except Exception:
                pass

    def _notify_error(self, error: str) -> None:
        """Notify callbacks of error."""
        for callback in self._error_callbacks:
            try:
                callback(error)
            except Exception:
                pass

    def connect(self) -> bool:
        """
        Establish connection to meshtasticd.

        Returns:
            True if connection successful
        """
        if self._connected:
            return True

        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.settimeout(self.config.connection_timeout)
            self._socket.connect((self.config.host, self.config.port))
            self._connected = True
            return True
        except socket.error as e:
            self._notify_error(f"Connection failed: {e}")
            self._connected = False
            return False

    def disconnect(self) -> None:
        """Disconnect from meshtasticd."""
        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None
        self._connected = False

    def _receive_data(self, timeout: float = 5.0) -> Optional[bytes]:
        """
        Receive data from socket.

        Args:
            timeout: Receive timeout

        Returns:
            Received data or None
        """
        if not self._socket:
            return None

        try:
            self._socket.settimeout(timeout)
            data = self._socket.recv(4096)
            return data if data else None
        except socket.timeout:
            return None
        except socket.error as e:
            self._notify_error(f"Receive error: {e}")
            self._connected = False
            return None

    def _send_command(self, command: str) -> bool:
        """
        Send command to meshtasticd.

        Args:
            command: Command string

        Returns:
            True if sent successfully
        """
        if not self._socket:
            return False

        try:
            self._socket.send(command.encode() + b"\n")
            return True
        except socket.error as e:
            self._notify_error(f"Send error: {e}")
            self._connected = False
            return False

    def poll_nodes(self) -> List[UnifiedNode]:
        """
        Poll for current node list.

        Returns:
            List of nodes
        """
        if not self._connected and not self.connect():
            return []

        # For actual implementation, this would parse meshtasticd protocol
        # Currently returns cached nodes from tracker
        return self._node_tracker.get_all()

    def _parse_node_info(self, data: Dict[str, Any]) -> UnifiedNode:
        """
        Parse node info from meshtasticd response.

        Args:
            data: Node data dictionary

        Returns:
            UnifiedNode instance
        """
        node_id = data.get("id", data.get("num", ""))
        if isinstance(node_id, int):
            node_id = f"!{node_id:08x}"

        node = UnifiedNode(
            unified_id=f"meshtastic_{node_id}",
            meshtastic_id=node_id,
            network="meshtastic",
            short_name=data.get("shortName", ""),
            long_name=data.get("longName", ""),
            hardware_model=data.get("hwModel", ""),
        )

        # Parse position
        if "position" in data:
            pos = data["position"]
            lat = pos.get("latitude", pos.get("latitudeI", 0))
            lon = pos.get("longitude", pos.get("longitudeI", 0))
            # Handle integer format
            if isinstance(lat, int) and abs(lat) > 1000:
                lat = lat / 1e7
            if isinstance(lon, int) and abs(lon) > 1000:
                lon = lon / 1e7
            if lat and lon:
                node.position = Position(
                    latitude=lat,
                    longitude=lon,
                    altitude=pos.get("altitude", 0)
                )

        # Parse telemetry
        if "deviceMetrics" in data:
            dm = data["deviceMetrics"]
            node.telemetry = Telemetry(
                battery_level=dm.get("batteryLevel"),
                voltage=dm.get("voltage"),
                channel_utilization=dm.get("channelUtilization"),
                air_util_tx=dm.get("airUtilTx"),
                uptime=dm.get("uptimeSeconds"),
            )

        # Parse radio metrics
        if "snr" in data:
            node.snr = data["snr"]
        if "rssi" in data:
            node.rssi = data["rssi"]

        node.update_last_seen()
        return node

    def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        while self._running:
            try:
                nodes = self.poll_nodes()
                if nodes:
                    self._notify_update(nodes)
                time.sleep(self.config.update_interval)
            except Exception as e:
                self._notify_error(f"Monitor loop error: {e}")
                time.sleep(1)

    def start_watch(self) -> bool:
        """
        Start continuous monitoring.

        Returns:
            True if started successfully
        """
        if self._running:
            return True

        if not self.connect():
            return False

        self._running = True
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            name="NodeMonitor",
            daemon=True
        )
        self._monitor_thread.start()
        return True

    def stop_watch(self) -> None:
        """Stop continuous monitoring."""
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5.0)
        self.disconnect()

    def get_node_table(self) -> List[Dict[str, Any]]:
        """
        Get formatted node table data.

        Returns:
            List of node dictionaries for display
        """
        nodes = self._node_tracker.get_all()
        table = []

        for node in nodes:
            row = {
                "id": node.meshtastic_id or node.unified_id,
                "name": node.long_name or node.short_name or "Unknown",
                "hardware": node.hardware_model or "Unknown",
                "battery": f"{node.telemetry.battery_level:.0f}%" if node.telemetry and node.telemetry.battery_level else "N/A",
                "snr": f"{node.snr:.1f}dB" if node.snr is not None else "N/A",
                "rssi": f"{node.rssi:.0f}dBm" if node.rssi is not None else "N/A",
                "last_seen": node.get_age(),
                "online": node.is_online,
            }

            if node.has_position():
                row["position"] = f"{node.position.latitude:.4f}, {node.position.longitude:.4f}"
            else:
                row["position"] = "N/A"

            table.append(row)

        # Sort by last seen
        table.sort(key=lambda x: x["last_seen"])
        return table

    def get_json_output(self) -> str:
        """
        Get nodes as JSON string.

        Returns:
            JSON string of all nodes
        """
        nodes = self._node_tracker.get_all()
        data = []

        for node in nodes:
            node_data = {
                "id": node.meshtastic_id or node.rns_address or node.unified_id,
                "unified_id": node.unified_id,
                "short_name": node.short_name,
                "long_name": node.long_name,
                "network": node.network,
                "is_online": node.is_online,
                "is_gateway": node.is_gateway,
                "hardware_model": node.hardware_model,
                "firmware_version": node.firmware_version,
                "snr": node.snr,
                "rssi": node.rssi,
                "hops": node.hops,
                "first_seen": node.first_seen,
                "last_seen": node.last_seen,
            }

            if node.position:
                node_data["position"] = {
                    "latitude": node.position.latitude,
                    "longitude": node.position.longitude,
                    "altitude": node.position.altitude,
                }

            if node.telemetry:
                node_data["telemetry"] = {
                    "battery_level": node.telemetry.battery_level,
                    "voltage": node.telemetry.voltage,
                    "temperature": node.telemetry.temperature,
                    "humidity": node.telemetry.humidity,
                    "uptime": node.telemetry.uptime,
                }

            data.append(node_data)

        return json.dumps(data, indent=2)

    def get_statistics(self) -> Dict[str, Any]:
        """Get monitoring statistics."""
        stats = self._node_tracker.get_statistics()
        stats["connected"] = self._connected
        stats["watching"] = self._running
        stats["host"] = self.config.host
        stats["port"] = self.config.port
        return stats
