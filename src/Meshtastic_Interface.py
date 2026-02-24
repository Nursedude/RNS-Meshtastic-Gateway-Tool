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
    """

    # Meshtastic maximum payload size (bytes)
    MESHTASTIC_MAX_PAYLOAD = 228

    def __init__(self, owner: Any, name: str, config: Optional[Dict[str, Any]] = None) -> None:
        # --- RNS COMPLIANCE SECTION ---
        # These attributes are strictly required by RNS to prevent runtime crashes.
        self.owner = owner
        self.name = name
        self.online = False
        self.IN = True
        self.OUT = False
        self.bitrate = 500  # Standard LoRa Bitrate proxy
        self.rxb = 0        # Receive Byte Counter
        self.txb = 0        # Transmit Byte Counter
        self.rx_packets = 0  # Receive Packet Counter
        self.tx_packets = 0  # Transmit Packet Counter
        self.tx_errors = 0   # Transmit Error Counter
        self.detached = False

        # Required by RNS Interface base class
        self.ingress_control = False
        self.held_announces = []
        self.rate_violation_occurred = False
        self.clients = 0
        self.ia_freq_deque = collections.deque(maxlen=100) # Inbound Frequency Log
        self.oa_freq_deque = collections.deque(maxlen=100) # Outbound Frequency Log
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

        # --- HARDWARE CONFIGURATION ---
        self.interface = None

        if self.connection_type == "tcp":
            self._init_tcp(owner, name, config or {})
        else:
            self._init_serial(owner, name, config or {})

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

    def process_incoming(self, data: bytes) -> None:
        """Handle data flowing FROM Reticulum TO the Mesh Radio (TX).

        NOTE on RNS naming convention: In the RNS Interface API,
        "incoming" means data arriving *into this interface* from the
        RNS transport layer — i.e., data that needs to be *transmitted*
        out over the physical medium (the mesh radio).
        """
        if self.online and self.interface:
            try:
                if len(data) > self.MESHTASTIC_MAX_PAYLOAD:
                    log.warning("[%s] Payload %d bytes exceeds Meshtastic limit (%d). "
                                "Radio may fragment or drop.", self.name, len(data),
                                self.MESHTASTIC_MAX_PAYLOAD)

                log.debug("[%s] >>> TRANSMITTING %d BYTES TO MESH...", self.name, len(data))
                self.txb += len(data)
                self.tx_packets += 1

                # FORCE BROADCAST: destinationId='^all' ensures the packet leaves the radio.
                # In the future, we can map RNS Hashes to Meshtastic Node IDs here.
                self.interface.sendData(data, destinationId='^all')

                log.debug("[%s] >>> SENT TO RADIO HARDWARE.", self.name)
            except (OSError, AttributeError, TypeError) as e:
                self.tx_errors += 1
                log.error("[%s] Transmit Error: %s", self.name, e)

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

    def reconnect(self) -> bool:
        """
        Attempt to reconnect after a connection loss.
        Closes existing interface cleanly, then re-initializes.
        """
        log.info("[%s] Attempting reconnect...", self.name)

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

        # Re-initialize based on connection type
        config = {}
        if self.connection_type == "tcp":
            config = {"host": self.host, "tcp_port": self.tcp_port, "connection_type": "tcp"}
            self._init_tcp(self.owner, self.name, config)
        else:
            config = {"port": self.port, "connection_type": "serial"}
            self._init_serial(self.owner, self.name, config)

        return self.online

    def detach(self) -> None:
        """
        Clean shutdown to release the connection.
        """
        if self.interface:
            try:
                self.interface.close()
            except (OSError, AttributeError) as e:
                log.warning("[%s] Warning during detach: %s", self.name, e)
        self.detached = True
        self.online = False
        log.info("[%s] Interface Detached.", self.name)

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
