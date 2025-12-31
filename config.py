# Configuration for RNS-Meshtastic Gateway

# --- Meshtastic Settings ---
# If connecting via USB, set to the serial port (e.g., '/dev/ttyUSB0' or 'COM3')
# If None, it attempts to auto-detect.
MESH_SERIAL_PORT = None 

# --- Reticulum Settings ---
# The name of the RNS Identity file
IDENTITY_FILE = 'storage/gateway_identity'

# The Aspect string for this destination (think of it as a channel topic)
# RNS addresses are generated from this.
RNS_ASPECT = 'meshtastic_bridge'

# Display name for logging
APP_NAME = "RNS-Mesh-Gateway"
