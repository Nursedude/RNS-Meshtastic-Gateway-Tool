import RNS
import time
import sys
import threading
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

class MeshtasticInterface(Interface):
    """
    RNS Interface Driver for Meshtastic LoRa Radios.
    Bridges Reticulum packets over the Meshtastic Python API via Serial/USB.
    """
    
    def __init__(self, owner, name):
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
        
        # Traffic Shaping & Stats (Critical for Stability)
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

        # --- HARDWARE CONFIGURATION ---
        try:
            if "interfaces" in owner.config and name in owner.config["interfaces"]:
                self.port = owner.config["interfaces"][name]["port"]
            else:
                self.port = "COM3"
        except Exception:
            self.port = "COM3"

        print(f"[{self.name}] Initializing on {self.port}...")

        # --- HARDWARE CONNECTION ---
        if HAS_MESH_LIB:
            try:
                self.interface = meshtastic.serial_interface.SerialInterface(self.port)
                # Subscribe to incoming Mesh packets
                meshtastic.pub.subscribe(self.on_receive, "meshtastic.receive.data")
                self.online = True
                self.OUT = True
                print(f"[{self.name}] Hardware Connected Successfully.")
            except Exception as e:
                print(f"[{self.name}] Hardware Error: {e}")
                self.online = False
        else:
            print(f"[{self.name}] CRITICAL: 'meshtastic' python library not found!")
            self.online = False

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
            # Silently drop malformed packets to avoid log spam
            pass

    def process_outgoing(self, data):
        self.process_incoming(data)

    def detach(self):
        """
        Clean shutdown to release the COM port.
        """
        if self.interface:
            try:
                self.interface.close()
            except Exception:
                pass
        self.detached = True
        self.online = False
        print(f"[{self.name}] Interface Detached.")

    def __str__(self):
        return f"Meshtastic Radio ({self.port})"