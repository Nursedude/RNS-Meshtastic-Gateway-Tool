from typing import Any, Dict, Optional

import RNS
import logging
import os
import collections

log = logging.getLogger("meshtastic_interface")

# [IMPORT PROTECTION]
# Ensure we load the correct Interface class structure for this RNS version.
try:
    from RNS.Interfaces.Interface import Interface
except ImportError:
    log.warning("RNS.Interfaces.Interface not found, trying RNS.Interface...")
    from RNS import Interface

# [HARDWARE CHECK]
try:
    import meshtastic
    import meshtastic.serial_interface
    HAS_MESH_LIB = True
except ImportError:
    HAS_MESH_LIB = False

# [TCP INTERFACE CHECK]
HAS_TCP_LIB = False
if HAS_MESH_LIB:
    try:
        import meshtastic.tcp_interface
        HAS_TCP_LIB = True
    except ImportError:
        pass


def _format_bytes(num_bytes: int) -> str:
    """Format byte count with human-readable units (MeshForge PR #1143)."""
    if num_bytes < 1024:
        return f"{num_bytes} B"
    elif num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f} KB"
    elif num_bytes < 1024 * 1024 * 1024:
        return f"{num_bytes / (1024 * 1024):.1f} MB"
    return f"{num_bytes / (1024 * 1024 * 1024):.2f} GB"


def _default_serial_port():
    """Return a platform-appropriate default serial port, with auto-detection."""
    try:
        from serial.tools.list_ports import comports
        ports = [p.device for p in comports()]
        if ports:
            return ports[0]
    except ImportError:
        pass
    if os.name == 'nt':
        return "COM3"
    return "/dev/ttyUSB0"


class MeshtasticInterface(Interface):
    """
    RNS Interface Driver for Meshtastic LoRa Radios.
    Bridges Reticulum packets over the Meshtastic Python API.
    Supports serial/USB and TCP (meshtasticd) connections.

    Reliability features (adopted from MeshForge patterns):
    - Circuit breaker: stops hammering a dead radio after N failures
    - Transmit queue: decouples RNS thread from radio I/O
    - Health check: active probe beyond just checking interface != None
    """

    # Meshtastic maximum payload size (bytes)
    MESHTASTIC_MAX_PAYLOAD = 228

    def __init__(
        self,
        owner: Any,
        name: str,
        config: Optional[Dict[str, Any]] = None,
        bridge_health=None,
        inter_packet_delay_fn=None,
    ) -> None:
        # --- RNS COMPLIANCE SECTION ---
        # These attributes are required by the RNS Interface base class and
        # transport internals.  Even when unused by *this* driver, RNS core
        # may read them during transport decisions, rnstatus display, or
        # announce rate-limiting.  Removing any will cause AttributeError
        # crashes at runtime.  See: RNS/Interfaces/Interface.py in the
        # Reticulum source.
        self.owner = owner
        self.name = name
        self.online = False
        self.IN = True                  # Accept inbound traffic
        self.OUT = False                # Outbound enabled after connect
        self.bitrate = 500              # LoRa bitrate proxy (bps)
        self.rxb = 0                    # Total received bytes
        self.txb = 0                    # Total transmitted bytes
        self.rx_packets = 0             # Received packet count
        self.tx_packets = 0             # Transmitted packet count
        self.tx_errors = 0              # Failed transmit count
        self.detached = False

        # RNS transport internals — required even if unused by this driver.
        # ingress_control: RNS announce rate-limiting flag
        # held_announces: Queued announces during rate-limiting
        # rate_violation_occurred: Set by RNS when rate limit exceeded
        # clients: Connection count for shared interfaces
        # ia_freq_deque/oa_freq_deque: Announce frequency tracking
        # announce_cap: Maximum announce rate (0 = unlimited)
        # ifac_identity: Interface authentication identity
        self.ingress_control = False
        self.held_announces = []
        self.rate_violation_occurred = False
        self.clients = 0
        self.ia_freq_deque = collections.deque(maxlen=100)
        self.oa_freq_deque = collections.deque(maxlen=100)
        self.announce_cap = 0
        self.ifac_identity = None

        # Mode Definition (For rnstatus display)
        try:
            self.mode = RNS.Interfaces.Interface.MODE_ACCESS_POINT
        except (AttributeError, KeyError):
            self.mode = 1

        # --- CONNECTION MODE ---
        self.connection_type = "serial"
        if config and config.get("connection_type"):
            self.connection_type = config["connection_type"]

        # --- RELIABILITY: Bridge Health Monitor (MeshForge pattern) ---
        self._bridge_health = bridge_health  # Optional BridgeHealthMonitor
        self._inter_packet_delay_fn = inter_packet_delay_fn  # Optional slow-start

        # --- RELIABILITY: Circuit Breaker (MeshForge pattern) ---
        features = (config or {}).get("features", {}) if isinstance(config, dict) else {}
        self._use_circuit_breaker = features.get("circuit_breaker", True)
        self._use_tx_queue = features.get("tx_queue", True)

        self._circuit_breaker = None
        if self._use_circuit_breaker:
            from src.utils.circuit_breaker import CircuitBreaker
            self._circuit_breaker = CircuitBreaker()

        # --- RELIABILITY: Persistent Message Queue (Session 2) ---
        self._use_message_queue = features.get("message_queue", False)
        self._message_queue = None

        # --- RELIABILITY: Transmit Queue (MeshForge pattern) ---
        # When message_queue is enabled, it has its own drain thread with
        # inter-packet delay support, so TxQueue is not needed.
        self._tx_queue = None
        if self._use_message_queue:
            from src.utils.message_queue import MessageQueue
            self._message_queue = MessageQueue(
                send_fn=self._do_send,
                inter_packet_delay_fn=self._inter_packet_delay_fn,
                on_status_change=self._on_queue_status_change,
            )
        elif self._use_tx_queue:
            from src.utils.tx_queue import TxQueue
            self._tx_queue = TxQueue(
                send_fn=self._do_send,
                maxsize=32,
                inter_packet_delay_fn=self._inter_packet_delay_fn,
            )

        # --- HARDWARE CONFIGURATION ---
        self.interface = None

        if self.connection_type == "tcp":
            self._init_tcp(owner, name, config or {})
        else:
            self._init_serial(owner, name, config or {})

        # Start queue after connection is established
        if self._message_queue and self.online:
            self._message_queue.start()
        elif self._tx_queue and self.online:
            self._tx_queue.start()

    def _on_queue_status_change(self, msg_id, old_status, new_status):
        """Handle message queue status changes for logging/monitoring."""
        log.debug("[%s] Message %s: %s -> %s",
                  self.name, msg_id[:8] if msg_id else "?",
                  old_status, new_status)

    def _init_serial(self, owner: Any, name: str, config: Dict[str, Any]) -> None:
        """Initialize via serial/USB connection."""
        # Priority: explicit config > RNS owner config > platform default
        self.port = config.get("port")

        if not self.port:
            try:
                if "interfaces" in owner.config and name in owner.config["interfaces"]:
                    self.port = owner.config["interfaces"][name]["port"]
            except (KeyError, TypeError, AttributeError):
                pass

        if not self.port:
            self.port = _default_serial_port()

        log.info("[%s] Initializing serial on %s...", self.name, self.port)

        # Pre-flight: verify device exists (MeshForge startup_checks pattern)
        if not os.path.exists(self.port):
            log.warning("[%s] Serial device %s not found (pre-flight check)",
                        self.name, self.port)

        if not HAS_MESH_LIB:
            log.critical("[%s] 'meshtastic' python library not found!", self.name)
            return

        try:
            self.interface = meshtastic.serial_interface.SerialInterface(self.port)
            meshtastic.pub.subscribe(self.on_receive, "meshtastic.receive.data")
            self.online = True
            self.OUT = True
            log.info("[%s] Serial connected on %s.", self.name, self.port)
        except (OSError, ConnectionError, ValueError) as e:
            log.error("[%s] Serial Error: %s", self.name, e)

    def _init_tcp(self, owner: Any, name: str, config: Dict[str, Any]) -> None:
        """Initialize via TCP connection to meshtasticd."""
        from src.utils.common import validate_hostname, validate_port

        self.host = config.get("host", "localhost")
        self.tcp_port = config.get("tcp_port", 4403)
        self.port = f"{self.host}:{self.tcp_port}"

        # Validate host/port before connecting (MeshForge security pattern)
        ok, err = validate_hostname(self.host)
        if not ok:
            log.error("[%s] Invalid TCP host: %s", self.name, err)
            return
        ok, err = validate_port(self.tcp_port)
        if not ok:
            log.error("[%s] Invalid TCP port: %s", self.name, err)
            return

        log.info("[%s] Initializing TCP on %s:%s...", self.name, self.host, self.tcp_port)

        # Pre-flight: check if meshtasticd port is listening
        from src.utils.service_check import check_tcp_port
        tcp_ok, tcp_detail = check_tcp_port(self.tcp_port, self.host)
        if not tcp_ok:
            log.warning("[%s] TCP pre-flight: %s", self.name, tcp_detail)

        if not HAS_MESH_LIB:
            log.critical("[%s] 'meshtastic' python library not found!", self.name)
            return

        if not HAS_TCP_LIB:
            log.critical("[%s] 'meshtastic.tcp_interface' not available!", self.name)
            log.critical("[%s] Upgrade meshtastic library: pip install --upgrade meshtastic", self.name)
            return

        try:
            self.interface = meshtastic.tcp_interface.TCPInterface(
                hostname=self.host,
                portNumber=self.tcp_port,
            )
            meshtastic.pub.subscribe(self.on_receive, "meshtastic.receive.data")
            self.online = True
            self.OUT = True
            log.info("[%s] TCP connected to %s:%s.", self.name, self.host, self.tcp_port)
        except (OSError, ConnectionError, ValueError) as e:
            log.error("[%s] TCP Error: %s", self.name, e)

    def _do_send(self, data: bytes) -> None:
        """Low-level send: transmit one packet to the radio hardware.

        Called by the TX queue drain thread (or directly if queue is disabled).
        Integrates with the circuit breaker to track success/failure.
        """
        try:
            if len(data) > self.MESHTASTIC_MAX_PAYLOAD:
                log.warning("[%s] Payload %d bytes exceeds Meshtastic limit (%d). "
                            "Radio may fragment or drop.", self.name, len(data),
                            self.MESHTASTIC_MAX_PAYLOAD)

            log.debug("[%s] >>> TRANSMITTING %d BYTES TO MESH...", self.name, len(data))
            self.txb += len(data)
            self.tx_packets += 1

            self.interface.sendData(data, destinationId='^all')

            log.debug("[%s] >>> SENT TO RADIO HARDWARE.", self.name)
            if self._circuit_breaker:
                self._circuit_breaker.record_success()
            if self._bridge_health:
                self._bridge_health.record_message_sent("rns_to_mesh")

            # Event bus notification for dashboards
            try:
                from src.utils.event_bus import emit_message
                emit_message(
                    direction="tx",
                    content=repr(data[:32]),
                    network="meshtastic",
                )
            except (ImportError, AttributeError):
                pass  # Event bus is optional; never block TX path
        except (OSError, AttributeError, TypeError) as e:
            self.tx_errors += 1
            if self._circuit_breaker:
                self._circuit_breaker.record_failure()
            if self._bridge_health:
                self._bridge_health.record_message_failed("rns_to_mesh")
                self._bridge_health.record_error("meshtastic", e)
            log.error("[%s] Transmit Error: %s", self.name, e)

    def process_incoming(self, data: bytes) -> None:
        """Handle data flowing FROM Reticulum TO the Mesh Radio (TX).

        NOTE on RNS naming convention: In the RNS Interface API,
        "incoming" means data arriving *into this interface* from the
        RNS transport layer — i.e., data that needs to be *transmitted*
        out over the physical medium (the mesh radio).
        """
        if not (self.online and self.interface):
            return

        # Circuit breaker: reject if breaker is open (radio unresponsive)
        if self._circuit_breaker and not self._circuit_breaker.allow_request():
            log.warning("[%s] Circuit breaker OPEN — TX blocked (radio unresponsive)",
                        self.name)
            return

        # Persistent queue takes priority over simple TX queue
        if self._message_queue:
            self._message_queue.enqueue(data)
        elif self._tx_queue:
            self._tx_queue.enqueue(data)
        else:
            self._do_send(data)

    def on_receive(self, packet: Dict[str, Any], interface: Any) -> None:
        """Handle data flowing FROM the Mesh Radio TO Reticulum (RX).

        Called by the meshtastic pub/sub system when a data packet
        arrives on the radio. Extracts the payload and passes it up
        to the RNS transport layer via owner.inbound().
        """
        try:
            if 'decoded' in packet and 'payload' in packet['decoded']:
                payload = packet['decoded']['payload']
                self.rxb += len(payload)
                self.rx_packets += 1
                if self._bridge_health:
                    self._bridge_health.record_message_sent("mesh_to_rns")

                # Event bus notification for dashboards
                try:
                    from src.utils.event_bus import emit_message
                    node_id = packet.get('fromId', '')
                    emit_message(
                        direction="rx",
                        content=repr(payload[:32]),
                        node_id=node_id,
                        network="meshtastic",
                    )
                except (ImportError, AttributeError):
                    pass  # Event bus is optional

                # Pass data up to the RNS Core
                self.owner.inbound(payload, self)
        except (KeyError, TypeError, AttributeError, ValueError) as e:
            log.warning("[%s] RX Error (packet dropped): %s", self.name, e)

    def process_outgoing(self, data: bytes) -> None:
        """Handle outbound data from RNS.

        NOTE on RNS naming convention: "outgoing" means data leaving
        the RNS transport layer — which is the same direction as
        process_incoming for this interface type.  Both result in
        transmission over the mesh radio.
        """
        self.process_incoming(data)

    def health_check(self) -> bool:
        """Active health probe — goes beyond checking interface != None.

        Checks:
        1. Interface object exists
        2. Circuit breaker is not OPEN (too many consecutive failures)
        3. For TCP: underlying socket is still connected
        """
        if self.interface is None:
            return False

        # Circuit breaker tripped → not healthy
        if self._circuit_breaker and not self._circuit_breaker.allow_request():
            from src.utils.circuit_breaker import State
            if self._circuit_breaker.state is State.OPEN:
                log.warning("[%s] Health check: circuit breaker OPEN (%d failures)",
                            self.name, self._circuit_breaker.failures)
                return False

        # TCP: check socket liveness
        if self.connection_type == "tcp":
            try:
                sock = getattr(self.interface, '_socket', None)
                if sock and sock.fileno() == -1:
                    log.warning("[%s] Health check: TCP socket closed", self.name)
                    return False
            except (OSError, AttributeError):
                pass

        return True

    def reconnect(self) -> bool:
        """
        Attempt to reconnect after a connection loss.
        Closes existing interface cleanly, then re-initializes.
        """
        log.info("[%s] Attempting reconnect...", self.name)

        # Stop queues before teardown
        if self._message_queue:
            self._message_queue.stop()
        if self._tx_queue:
            self._tx_queue.stop()

        # Unsubscribe to prevent duplicate handlers on re-init
        try:
            meshtastic.pub.unsubscribe(self.on_receive, "meshtastic.receive.data")
        except (KeyError, ValueError, AttributeError):
            pass

        # Close existing connection
        if self.interface:
            try:
                self.interface.close()
            except (OSError, AttributeError):
                pass
            self.interface = None

        self.online = False
        self.OUT = False

        if self._bridge_health:
            self._bridge_health.record_connection_event("meshtastic", "disconnected")

        # Reset circuit breaker for fresh connection
        if self._circuit_breaker:
            self._circuit_breaker.reset()

        # Re-initialize based on connection type
        config = {}
        if self.connection_type == "tcp":
            config = {"host": self.host, "tcp_port": self.tcp_port, "connection_type": "tcp"}
            self._init_tcp(self.owner, self.name, config)
        else:
            config = {"port": self.port, "connection_type": "serial"}
            self._init_serial(self.owner, self.name, config)

        # Restart queues if connection succeeded
        if self._message_queue and self.online:
            self._message_queue.start()
        elif self._tx_queue and self.online:
            self._tx_queue.start()

        if self._bridge_health and self.online:
            self._bridge_health.record_connection_event("meshtastic", "connected")

        return self.online

    def detach(self) -> None:
        """
        Clean shutdown to release the connection.
        """
        # Stop queues
        if self._message_queue:
            self._message_queue.stop()
        if self._tx_queue:
            self._tx_queue.stop()

        if self.interface:
            try:
                self.interface.close()
            except (OSError, AttributeError) as e:
                log.warning("[%s] Warning during detach: %s", self.name, e)
        self.detached = True
        self.online = False
        log.info("[%s] Interface Detached.", self.name)

    @property
    def metrics(self) -> dict:
        """Snapshot of interface metrics for dashboard/monitoring integration.

        Enhanced with MeshForge-style diagnostics: traffic statistics
        with human-readable byte formatting and circuit breaker stats.
        """
        m = {
            "tx_packets": self.tx_packets,
            "rx_packets": self.rx_packets,
            "tx_bytes": self.txb,
            "rx_bytes": self.rxb,
            "tx_errors": self.tx_errors,
            "online": self.online,
            "connection_type": self.connection_type,
            "tx_bytes_human": _format_bytes(self.txb),
            "rx_bytes_human": _format_bytes(self.rxb),
        }
        if self._message_queue:
            m["message_queue_pending"] = self._message_queue.pending_count
            m["message_queue_dead_letters"] = self._message_queue.dead_letter_count
        if self._tx_queue:
            m["tx_queue_pending"] = self._tx_queue.pending
            m["tx_queue_dropped"] = self._tx_queue.dropped
        if self._circuit_breaker:
            m["circuit_breaker_state"] = self._circuit_breaker.state.value
            m["circuit_breaker_failures"] = self._circuit_breaker.failures
            m["circuit_breaker_stats"] = self._circuit_breaker.get_stats()
        return m

    def __str__(self):
        return f"Meshtastic Radio ({self.connection_type}: {self.port})"

    def __repr__(self):
        return (
            f"<MeshtasticInterface name={self.name!r} type={self.connection_type} "
            f"port={self.port!r} online={self.online} "
            f"tx={self.tx_packets}pkt/{self.txb}B "
            f"rx={self.rx_packets}pkt/{self.rxb}B "
            f"errors={self.tx_errors}>"
        )
