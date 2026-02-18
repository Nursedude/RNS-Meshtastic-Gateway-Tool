import RNS
import json
import os
import sys
import time

# Add project root and src folder to path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, 'src'))

from version import __version__

# Import the custom driver
try:
    from Meshtastic_Interface import MeshtasticInterface
except ImportError as e:
    print("[CRITICAL] Could not import Meshtastic Driver.")
    print(f"Error: {e}")
    sys.exit(1)

CONFIG_PATH = os.path.join(BASE_DIR, 'config.json')


def load_config():
    """Load gateway config.json, returning empty dict on failure."""
    try:
        with open(CONFIG_PATH, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, PermissionError) as e:
        print(f"[WARN] Could not load {CONFIG_PATH}: {e}")
        print("[WARN] Using default settings.")
        return {}


def start_gateway():
    print("============================================================")
    print(f"  SUPERVISOR NOC | RNS-MESHTASTIC GATEWAY v{__version__}")
    print("============================================================")

    cfg = load_config()
    gw_config = cfg.get("gateway", {})

    # 1. Initialize Reticulum
    # This automatically loads the default config from ~/.reticulum
    rns_connection = RNS.Reticulum()

    print("\n[GO] Loading Interface 'Meshtastic Radio'...")

    # 2. Instantiate the Driver
    # Pass RNS instance, name, and gateway config for port/settings.
    mesh_interface = MeshtasticInterface(rns_connection, "Meshtastic Radio", config=gw_config)

    if mesh_interface.online:
        print(" [SUCCESS] Interface Loaded! Waiting for traffic...")

        # Keep the main thread alive
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[STOP] Shutting down gateway...")
            mesh_interface.detach()
            sys.exit(0)
    else:
        print(" [FAIL] Interface failed to initialize.")
        sys.exit(1)

if __name__ == "__main__":
    start_gateway()
