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

    def __init__(self, owner: Any, name: str, config: Optional[Dict[str, Any]] = None) -> None:
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

        # --- RELIABILITY: Circuit Breaker (MeshForge pattern) ---
        features = (config or {}).get("features", {}) if isinstance(config, dict) else {}
        self._use_circuit_breaker = features.get("circuit_breaker", True)
        self._use_tx_queue = features.get("tx_queue", True)

        self._circuit_breaker = None
        if self._use_circuit_breaker:
            from src.utils.circuit_breaker import CircuitBreaker
            self._circuit_breaker = CircuitBreaker()

        # --- RELIABILITY: Transmit Queue (MeshForge pattern) ---
        self._tx_queue = None
        if self._use_tx_queue:
            from src.utils.tx_queue import TxQueue
            self._tx_queue = TxQueue(
                send_fn=self._do_send,
                maxsize=32,
            )

        # --- HARDWARE CONFIGURATION ---
        self.interface = None

        if self.connection_type == "tcp":
            self._init_tcp(owner, name, config or {})
        else:
            self._init_serial(owner, name, config or {})

        # Start TX queue after connection is established
        if self._tx_queue and self.online:
            self._tx_queue.start()

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
        except (OSError, AttributeError, TypeError) as e:
            self.tx_errors += 1
            if self._circuit_breaker:
                self._circuit_breaker.record_failure()
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

        # TX queue: enqueue for async drain, or send directly
        if self._tx_queue:
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

        # Stop TX queue before teardown
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

        # Restart TX queue if connection succeeded
        if self._tx_queue and self.online:
            self._tx_queue.start()

        return self.online

    def detach(self) -> None:
        """
        Clean shutdown to release the connection.
        """
        # Stop TX queue
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
        """Snapshot of interface metrics for dashboard/monitoring integration."""
        m = {
            "tx_packets": self.tx_packets,
            "rx_packets": self.rx_packets,
            "tx_bytes": self.txb,
            "rx_bytes": self.rxb,
            "tx_errors": self.tx_errors,
            "online": self.online,
        }
        if self._tx_queue:
            m["tx_queue_pending"] = self._tx_queue.pending
            m["tx_queue_dropped"] = self._tx_queue.dropped
        if self._circuit_breaker:
            m["circuit_breaker_state"] = self._circuit_breaker.state.value
            m["circuit_breaker_failures"] = self._circuit_breaker.failures
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
