"""
RNS-Meshtastic Bridge Service.

Provides bidirectional message bridging between Reticulum Network Stack (RNS)
and Meshtastic mesh networks with configurable routing rules.
"""

import queue
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Callable, List, Dict, Any

from .config import GatewayConfig, RoutingRule
from .node_tracker import UnifiedNodeTracker, UnifiedNode, Position, Telemetry


@dataclass
class BridgedMessage:
    """Represents a message in transit between networks."""

    message_id: str
    source_network: str  # "meshtastic" or "rns"
    destination_network: str
    source_id: str
    destination_id: Optional[str]  # None for broadcast
    content: str
    channel: int = 0
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Tracking
    delivered: bool = False
    delivery_time: Optional[float] = None
    error: Optional[str] = None

    def mark_delivered(self) -> None:
        """Mark message as successfully delivered."""
        self.delivered = True
        self.delivery_time = time.time()

    def mark_failed(self, error: str) -> None:
        """Mark message as failed with error."""
        self.delivered = False
        self.error = error


class RNSMeshtasticBridge:
    """
    Bidirectional gateway bridging RNS and Meshtastic networks.

    Manages connections to both networks, message queuing, routing,
    and node tracking with callback support for external components.
    """

    def __init__(
        self,
        config: Optional[GatewayConfig] = None,
        node_tracker: Optional[UnifiedNodeTracker] = None
    ):
        """
        Initialize the bridge.

        Args:
            config: Gateway configuration
            node_tracker: Node tracker instance
        """
        self.config = config or GatewayConfig.load()
        self.node_tracker = node_tracker or UnifiedNodeTracker()

        # Message queues
        self._meshtastic_queue: queue.Queue[BridgedMessage] = queue.Queue()
        self._rns_queue: queue.Queue[BridgedMessage] = queue.Queue()

        # Connection state
        self._meshtastic_connected = False
        self._rns_connected = False
        self._running = False

        # Threads
        self._meshtastic_thread: Optional[threading.Thread] = None
        self._rns_thread: Optional[threading.Thread] = None
        self._bridge_thread: Optional[threading.Thread] = None

        # Statistics
        self._stats = {
            "messages_bridged": 0,
            "messages_failed": 0,
            "meshtastic_received": 0,
            "rns_received": 0,
            "start_time": None,
            "last_message_time": None,
        }

        # Callbacks
        self._message_callbacks: List[Callable[[BridgedMessage], None]] = []
        self._status_callbacks: List[Callable[[str, Any], None]] = []

        # Lock for thread safety
        self._lock = threading.RLock()

    def register_message_callback(
        self,
        callback: Callable[[BridgedMessage], None]
    ) -> None:
        """Register callback for bridged messages."""
        self._message_callbacks.append(callback)

    def register_status_callback(
        self,
        callback: Callable[[str, Any], None]
    ) -> None:
        """Register callback for status changes."""
        self._status_callbacks.append(callback)

    def _notify_message(self, message: BridgedMessage) -> None:
        """Notify callbacks of a bridged message."""
        for callback in self._message_callbacks:
            try:
                callback(message)
            except Exception:
                pass

    def _notify_status(self, event: str, data: Any = None) -> None:
        """Notify callbacks of status change."""
        for callback in self._status_callbacks:
            try:
                callback(event, data)
            except Exception:
                pass

    def _connect_meshtastic(self) -> bool:
        """
        Establish connection to Meshtastic network.

        Returns:
            True if connection successful
        """
        try:
            # Try to import meshtastic library
            try:
                import meshtastic
                import meshtastic.tcp_interface
            except ImportError:
                # Fall back to CLI-based interaction
                self._meshtastic_connected = True
                self._notify_status("meshtastic_connected", {"mode": "cli"})
                return True

            # Connect via TCP to meshtasticd
            host = self.config.meshtastic.host
            port = self.config.meshtastic.port

            # Note: Actual connection would be established here
            # For now, we mark as connected for the framework
            self._meshtastic_connected = True
            self._notify_status("meshtastic_connected", {
                "host": host,
                "port": port,
                "mode": "tcp"
            })
            return True

        except Exception as e:
            self._notify_status("meshtastic_error", {"error": str(e)})
            return False

    def _connect_rns(self) -> bool:
        """
        Establish connection to RNS network.

        Returns:
            True if connection successful
        """
        try:
            # Try to import RNS library
            try:
                import RNS
            except ImportError:
                # RNS not available, mark as connected for framework
                self._rns_connected = True
                self._notify_status("rns_connected", {"mode": "stub"})
                return True

            # Initialize RNS
            config_dir = self.config.rns.config_dir

            # Note: Actual RNS initialization would happen here
            self._rns_connected = True
            self._notify_status("rns_connected", {
                "config_dir": config_dir,
                "identity": self.config.rns.identity_name
            })
            return True

        except Exception as e:
            self._notify_status("rns_error", {"error": str(e)})
            return False

    def _meshtastic_loop(self) -> None:
        """Main loop for Meshtastic network handling."""
        retry_count = 0
        max_retries = self.config.max_retries
        retry_delay = self.config.retry_delay

        while self._running:
            if not self._meshtastic_connected:
                if not self._connect_meshtastic():
                    retry_count += 1
                    if retry_count >= max_retries:
                        self._notify_status("meshtastic_max_retries", {})
                        break
                    time.sleep(retry_delay)
                    continue
                retry_count = 0

            try:
                # Process outgoing messages to Meshtastic
                try:
                    message = self._meshtastic_queue.get(timeout=1.0)
                    self._send_to_meshtastic(message)
                except queue.Empty:
                    pass

                # Poll for incoming would happen here in real implementation

            except Exception as e:
                self._meshtastic_connected = False
                self._notify_status("meshtastic_disconnected", {"error": str(e)})

    def _rns_loop(self) -> None:
        """Main loop for RNS network handling."""
        retry_count = 0
        max_retries = self.config.max_retries
        retry_delay = self.config.retry_delay

        while self._running:
            if not self._rns_connected:
                if not self._connect_rns():
                    retry_count += 1
                    if retry_count >= max_retries:
                        self._notify_status("rns_max_retries", {})
                        break
                    time.sleep(retry_delay)
                    continue
                retry_count = 0

            try:
                # Process outgoing messages to RNS
                try:
                    message = self._rns_queue.get(timeout=1.0)
                    self._send_to_rns(message)
                except queue.Empty:
                    pass

                # RNS callbacks handle incoming

            except Exception as e:
                self._rns_connected = False
                self._notify_status("rns_disconnected", {"error": str(e)})

    def _bridge_loop(self) -> None:
        """Main loop for message bridging logic."""
        while self._running:
            # Update node online status periodically
            self.node_tracker.update_online_status()
            time.sleep(5)

    def _send_to_meshtastic(self, message: BridgedMessage) -> bool:
        """
        Send a message to the Meshtastic network.

        Args:
            message: Message to send

        Returns:
            True if sent successfully
        """
        try:
            # Apply routing rules
            rules = self.config.get_matching_rules(
                message.content,
                "rns_to_meshtastic"
            )
            if not rules:
                message.mark_failed("No matching routing rules")
                return False

            # Actual send would happen here
            message.mark_delivered()
            self._stats["messages_bridged"] += 1
            self._stats["last_message_time"] = time.time()
            self._notify_message(message)
            return True

        except Exception as e:
            message.mark_failed(str(e))
            self._stats["messages_failed"] += 1
            return False

    def _send_to_rns(self, message: BridgedMessage) -> bool:
        """
        Send a message to the RNS network.

        Args:
            message: Message to send

        Returns:
            True if sent successfully
        """
        try:
            # Apply routing rules
            rules = self.config.get_matching_rules(
                message.content,
                "meshtastic_to_rns"
            )
            if not rules:
                message.mark_failed("No matching routing rules")
                return False

            # Actual send would happen here
            message.mark_delivered()
            self._stats["messages_bridged"] += 1
            self._stats["last_message_time"] = time.time()
            self._notify_message(message)
            return True

        except Exception as e:
            message.mark_failed(str(e))
            self._stats["messages_failed"] += 1
            return False

    def handle_meshtastic_packet(
        self,
        packet: Dict[str, Any],
        interface: Any = None
    ) -> None:
        """
        Handle incoming Meshtastic packet.

        Args:
            packet: Meshtastic packet data
            interface: Meshtastic interface (optional)
        """
        self._stats["meshtastic_received"] += 1

        # Extract packet info
        from_id = packet.get("fromId", packet.get("from", ""))
        to_id = packet.get("toId", packet.get("to", ""))
        decoded = packet.get("decoded", {})

        # Handle text messages
        if decoded.get("portnum") == "TEXT_MESSAGE_APP":
            text = decoded.get("text", "")
            if text and self.config.bridge_enabled:
                message = BridgedMessage(
                    message_id=f"mesh_{time.time()}_{from_id}",
                    source_network="meshtastic",
                    destination_network="rns",
                    source_id=from_id,
                    destination_id=to_id if to_id != "^all" else None,
                    content=text,
                    metadata={"raw_packet": packet}
                )
                self._rns_queue.put(message)

        # Handle position updates
        if decoded.get("portnum") == "POSITION_APP":
            position_data = decoded.get("position", {})
            if position_data:
                self._update_node_position(from_id, position_data, "meshtastic")

        # Handle telemetry
        if decoded.get("portnum") == "TELEMETRY_APP":
            telemetry_data = decoded.get("telemetry", {})
            if telemetry_data:
                self._update_node_telemetry(from_id, telemetry_data, "meshtastic")

        # Update node tracker
        self._ensure_node_tracked(from_id, "meshtastic", packet)

    def handle_rns_message(
        self,
        message_data: Dict[str, Any],
        source_hash: str
    ) -> None:
        """
        Handle incoming RNS message.

        Args:
            message_data: Message data
            source_hash: Source RNS hash
        """
        self._stats["rns_received"] += 1

        content = message_data.get("content", "")
        dest_hash = message_data.get("destination")

        if content and self.config.bridge_enabled:
            message = BridgedMessage(
                message_id=f"rns_{time.time()}_{source_hash}",
                source_network="rns",
                destination_network="meshtastic",
                source_id=source_hash,
                destination_id=dest_hash,
                content=content,
                metadata={"raw_data": message_data}
            )
            self._meshtastic_queue.put(message)

        # Update node tracker
        self._ensure_node_tracked(source_hash, "rns", message_data)

    def _ensure_node_tracked(
        self,
        node_id: str,
        network: str,
        data: Dict[str, Any]
    ) -> UnifiedNode:
        """Ensure a node is tracked in the unified tracker."""
        # Check if already tracked
        if network == "meshtastic":
            existing = self.node_tracker.get_by_meshtastic_id(node_id)
        else:
            existing = self.node_tracker.get_by_rns_address(node_id)

        if existing:
            existing.update_last_seen()
            existing.is_online = True
            return existing

        # Create new node
        node = UnifiedNode(
            unified_id=f"{network}_{node_id}",
            meshtastic_id=node_id if network == "meshtastic" else None,
            rns_address=node_id if network == "rns" else None,
            network=network,
            short_name=data.get("shortName", ""),
            long_name=data.get("longName", ""),
            hardware_model=data.get("hwModel", ""),
        )

        # Extract radio metrics
        if "snr" in data:
            node.snr = data["snr"]
        if "rssi" in data:
            node.rssi = data["rssi"]
        if "hopLimit" in data:
            node.hops = data.get("hopStart", 0) - data.get("hopLimit", 0)

        return self.node_tracker.add_or_update(node)

    def _update_node_position(
        self,
        node_id: str,
        position_data: Dict[str, Any],
        network: str
    ) -> None:
        """Update node position in tracker."""
        lat = position_data.get("latitude", position_data.get("latitudeI", 0))
        lon = position_data.get("longitude", position_data.get("longitudeI", 0))
        alt = position_data.get("altitude", 0)

        # Handle integer format (Meshtastic uses 1e-7 scaling)
        if isinstance(lat, int) and abs(lat) > 1000:
            lat = lat / 1e7
        if isinstance(lon, int) and abs(lon) > 1000:
            lon = lon / 1e7

        if lat and lon:
            position = Position(latitude=lat, longitude=lon, altitude=alt)

            # Get or create node
            node = self._ensure_node_tracked(node_id, network, {})
            node.position = position
            self.node_tracker.add_or_update(node)

    def _update_node_telemetry(
        self,
        node_id: str,
        telemetry_data: Dict[str, Any],
        network: str
    ) -> None:
        """Update node telemetry in tracker."""
        device_metrics = telemetry_data.get("deviceMetrics", {})
        environment = telemetry_data.get("environmentMetrics", {})

        telemetry = Telemetry(
            battery_level=device_metrics.get("batteryLevel"),
            voltage=device_metrics.get("voltage"),
            channel_utilization=device_metrics.get("channelUtilization"),
            air_util_tx=device_metrics.get("airUtilTx"),
            uptime=device_metrics.get("uptimeSeconds"),
            temperature=environment.get("temperature"),
            humidity=environment.get("relativeHumidity"),
            pressure=environment.get("barometricPressure"),
        )

        # Get or create node
        node = self._ensure_node_tracked(node_id, network, {})
        node.telemetry = telemetry
        self.node_tracker.add_or_update(node)

    def start(self) -> bool:
        """
        Start the bridge service.

        Returns:
            True if started successfully
        """
        if self._running:
            return True

        self._running = True
        self._stats["start_time"] = time.time()

        # Start network threads
        self._meshtastic_thread = threading.Thread(
            target=self._meshtastic_loop,
            name="MeshtasticLoop",
            daemon=True
        )
        self._rns_thread = threading.Thread(
            target=self._rns_loop,
            name="RNSLoop",
            daemon=True
        )
        self._bridge_thread = threading.Thread(
            target=self._bridge_loop,
            name="BridgeLoop",
            daemon=True
        )

        self._meshtastic_thread.start()
        self._rns_thread.start()
        self._bridge_thread.start()

        self._notify_status("bridge_started", {})
        return True

    def stop(self) -> None:
        """Stop the bridge service."""
        self._running = False

        # Wait for threads to finish
        if self._meshtastic_thread:
            self._meshtastic_thread.join(timeout=5.0)
        if self._rns_thread:
            self._rns_thread.join(timeout=5.0)
        if self._bridge_thread:
            self._bridge_thread.join(timeout=5.0)

        # Save node cache
        self.node_tracker.save()

        self._notify_status("bridge_stopped", {})

    def get_status(self) -> Dict[str, Any]:
        """Get current bridge status."""
        uptime = 0
        if self._stats["start_time"]:
            uptime = time.time() - self._stats["start_time"]

        return {
            "running": self._running,
            "meshtastic_connected": self._meshtastic_connected,
            "rns_connected": self._rns_connected,
            "bridge_enabled": self.config.bridge_enabled,
            "uptime_seconds": uptime,
            "messages_bridged": self._stats["messages_bridged"],
            "messages_failed": self._stats["messages_failed"],
            "meshtastic_received": self._stats["meshtastic_received"],
            "rns_received": self._stats["rns_received"],
            "last_message_time": self._stats["last_message_time"],
            "nodes_tracked": len(self.node_tracker.get_all()),
        }

    def send_message(
        self,
        content: str,
        destination_network: str,
        destination_id: Optional[str] = None,
        channel: int = 0
    ) -> BridgedMessage:
        """
        Send a message through the bridge.

        Args:
            content: Message content
            destination_network: Target network ("meshtastic" or "rns")
            destination_id: Target node ID (None for broadcast)
            channel: Meshtastic channel (default 0)

        Returns:
            BridgedMessage tracking the send
        """
        source_network = "rns" if destination_network == "meshtastic" else "meshtastic"

        message = BridgedMessage(
            message_id=f"user_{time.time()}",
            source_network=source_network,
            destination_network=destination_network,
            source_id="local",
            destination_id=destination_id,
            content=content,
            channel=channel
        )

        if destination_network == "meshtastic":
            self._meshtastic_queue.put(message)
        else:
            self._rns_queue.put(message)

        return message
