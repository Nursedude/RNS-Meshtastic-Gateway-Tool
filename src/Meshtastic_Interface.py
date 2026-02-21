import RNS
import os
import sys
import collections

# [IMPORT PROTECTION]
# Ensure we load the correct Interface class structure for this RNS version.
try:
    from RNS.Interfaces.Interface import Interface
except ImportError:
    print("[WARN] RNS.Interfaces.Interface not found, trying RNS.Interface...")
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

    def __init__(self, owner, name, config=None):
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

    def _init_serial(self, owner, name, config):
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

        print(f"[{self.name}] Initializing serial on {self.port}...")

        if not HAS_MESH_LIB:
            print(f"[{self.name}] CRITICAL: 'meshtastic' python library not found!")
            return

        try:
            self.interface = meshtastic.serial_interface.SerialInterface(self.port)
            meshtastic.pub.subscribe(self.on_receive, "meshtastic.receive.data")
            self.online = True
            self.OUT = True
            print(f"[{self.name}] Serial connected on {self.port}.")
        except Exception as e:
            print(f"[{self.name}] Serial Error: {e}")

    def _init_tcp(self, owner, name, config):
        """Initialize via TCP connection to meshtasticd."""
        self.host = config.get("host", "localhost")
        self.tcp_port = config.get("tcp_port", 4403)
        self.port = f"{self.host}:{self.tcp_port}"

        print(f"[{self.name}] Initializing TCP on {self.host}:{self.tcp_port}...")

        if not HAS_MESH_LIB:
            print(f"[{self.name}] CRITICAL: 'meshtastic' python library not found!")
            return

        if not HAS_TCP_LIB:
            print(f"[{self.name}] CRITICAL: 'meshtastic.tcp_interface' not available!")
            print(f"[{self.name}] Upgrade meshtastic library: pip install --upgrade meshtastic")
            return

        try:
            self.interface = meshtastic.tcp_interface.TCPInterface(
                hostname=self.host,
                portNumber=self.tcp_port,
            )
            meshtastic.pub.subscribe(self.on_receive, "meshtastic.receive.data")
            self.online = True
            self.OUT = True
            print(f"[{self.name}] TCP connected to {self.host}:{self.tcp_port}.")
        except Exception as e:
            print(f"[{self.name}] TCP Error: {e}")

    def process_incoming(self, data):
        """
        Handles data flowing FROM Reticulum TO the Mesh Radio (TX).
        """
        if self.online and self.interface:
            try:
                print(f"[{self.name}] >>> TRANSMITTING {len(data)} BYTES TO MESH...")
                self.txb += len(data)

                # FORCE BROADCAST: destinationId='^all' ensures the packet leaves the radio.
                # In the future, we can map RNS Hashes to Meshtastic Node IDs here.
                self.interface.sendData(data, destinationId='^all')

                print(f"[{self.name}] >>> SENT TO RADIO HARDWARE.")
            except Exception as e:
                print(f"[{self.name}] Transmit Error: {e}")

    def on_receive(self, packet, interface):
        """
        Handles data flowing FROM the Mesh Radio TO Reticulum (RX).
        """
        try:
            if 'decoded' in packet and 'payload' in packet['decoded']:
                payload = packet['decoded']['payload']
                self.rxb += len(payload)
                # Pass data up to the RNS Core
                self.owner.inbound(payload, self)
        except Exception as e:
            print(f"[{self.name}] RX Error (packet dropped): {e}")

    def process_outgoing(self, data):
        # RNS calls process_outgoing for TX; delegate to our TX handler
        self.process_incoming(data)

    def reconnect(self):
        """
        Attempt to reconnect after a connection loss.
        Closes existing interface cleanly, then re-initializes.
        """
        print(f"[{self.name}] Attempting reconnect...")

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

    def detach(self):
        """
        Clean shutdown to release the connection.
        """
        if self.interface:
            try:
                self.interface.close()
            except Exception as e:
                print(f"[{self.name}] Warning during detach: {e}")
        self.detached = True
        self.online = False
        print(f"[{self.name}] Interface Detached.")

    def __str__(self):
        return f"Meshtastic Radio ({self.connection_type}: {self.port})"
