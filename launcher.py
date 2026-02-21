import RNS
import os
import random
import sys
import time

# Add project root and src folder to path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, 'src'))

from version import __version__
from src.utils.common import CONFIG_PATH, load_config

# Import the custom driver
try:
    from Meshtastic_Interface import MeshtasticInterface
except ImportError as e:
    print("[CRITICAL] Could not import Meshtastic Driver.")
    print(f"Error: {e}")
    sys.exit(1)

# Reconnect settings (inspired by MeshForge ReconnectStrategy)
RECONNECT_INITIAL_DELAY = 2.0   # seconds
RECONNECT_MAX_DELAY = 60.0      # seconds
RECONNECT_MULTIPLIER = 2.0
RECONNECT_JITTER = 0.15         # 15% jitter to prevent thundering herd
RECONNECT_MAX_ATTEMPTS = 10
HEALTH_CHECK_INTERVAL = 30      # seconds between connection health checks


def _backoff_delay(attempt):
    """Calculate reconnect delay with exponential backoff + jitter."""
    base = min(RECONNECT_INITIAL_DELAY * (RECONNECT_MULTIPLIER ** attempt), RECONNECT_MAX_DELAY)
    jitter = base * RECONNECT_JITTER
    return base + random.uniform(-jitter, jitter)


def start_gateway():
    print("============================================================")
    print(f"  SUPERVISOR NOC | RNS-MESHTASTIC GATEWAY v{__version__}")
    print("============================================================")

    cfg = load_config()
    if not cfg:
        print(f"[WARN] Could not load {CONFIG_PATH}. Using default settings.")
    gw_config = cfg.get("gateway", {})

    # 1. Initialize Reticulum
    rns_connection = RNS.Reticulum()

    print("\n[GO] Loading Interface 'Meshtastic Radio'...")

    # 2. Instantiate the Driver
    mesh_interface = MeshtasticInterface(rns_connection, "Meshtastic Radio", config=gw_config)

    if not mesh_interface.online:
        print(" [FAIL] Initial connection failed. Will retry...")

    # 3. Main loop with health check and auto-reconnect
    reconnect_attempts = 0
    last_health_check = time.time()

    try:
        while True:
            now = time.time()

            if mesh_interface.online:
                # Connection is healthy — reset attempt counter
                reconnect_attempts = 0

                # Periodic health check: verify the interface is still responsive
                if now - last_health_check >= HEALTH_CHECK_INTERVAL:
                    last_health_check = now
                    if mesh_interface.interface is None:
                        print(f"[{mesh_interface.name}] Health check: interface lost")
                        mesh_interface.online = False

                time.sleep(1)
            else:
                # Connection is down — attempt reconnect with backoff
                if reconnect_attempts >= RECONNECT_MAX_ATTEMPTS:
                    print(f"[WARN] {RECONNECT_MAX_ATTEMPTS} reconnect attempts exhausted. Resetting...")
                    reconnect_attempts = 0
                    time.sleep(RECONNECT_MAX_DELAY)
                    continue

                delay = _backoff_delay(reconnect_attempts)
                reconnect_attempts += 1
                print(f"[RECONNECT] Attempt {reconnect_attempts}/{RECONNECT_MAX_ATTEMPTS} "
                      f"in {delay:.1f}s...")
                time.sleep(delay)

                if mesh_interface.reconnect():
                    print(f" [SUCCESS] Reconnected after {reconnect_attempts} attempt(s)!")
                    reconnect_attempts = 0
                else:
                    print(f" [FAIL] Reconnect attempt {reconnect_attempts} failed.")

    except KeyboardInterrupt:
        print("\n[STOP] Shutting down gateway...")
        mesh_interface.detach()
        sys.exit(0)

if __name__ == "__main__":
    try:
        start_gateway()
    except Exception as e:
        print(f"\n[FATAL] Gateway crashed: {e}")
        sys.exit(1)
