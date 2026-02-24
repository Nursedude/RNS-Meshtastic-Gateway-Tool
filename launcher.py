import RNS
import logging
import os
import random
import signal
import sys
import time

# Add project root and src folder to path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, 'src'))

from version import __version__
from src.utils.common import CONFIG_PATH, load_config
from src.utils.log import setup_logging

log = logging.getLogger("gateway")

# Import the custom driver
try:
    from Meshtastic_Interface import MeshtasticInterface
except ImportError as e:
    logging.basicConfig()
    log.critical("Could not import Meshtastic Driver: %s", e)
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
    setup_logging()

    print("============================================================")
    print(f"  SUPERVISOR NOC | RNS-MESHTASTIC GATEWAY v{__version__}")
    print("============================================================")

    cfg = load_config()
    if not cfg:
        log.warning("Could not load %s. Using default settings.", CONFIG_PATH)
    gw_config = cfg.get("gateway", {})

    # 1. Initialize Reticulum
    rns_connection = RNS.Reticulum()

    log.info("Loading Interface 'Meshtastic Radio'...")

    # 2. Instantiate the Driver
    mesh_interface = MeshtasticInterface(rns_connection, "Meshtastic Radio", config=gw_config)

    if not mesh_interface.online:
        log.warning("Initial connection failed. Will retry...")

    # 3. Signal handling for clean systemd/SIGTERM shutdown
    def _handle_signal(signum, frame):
        sig_name = signal.Signals(signum).name
        log.info("Received %s — shutting down gateway...", sig_name)
        mesh_interface.detach()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _handle_signal)
    if hasattr(signal, 'SIGHUP'):
        signal.signal(signal.SIGHUP, _handle_signal)

    # 4. Main loop with health check and auto-reconnect
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
                        log.warning("[%s] Health check: interface lost", mesh_interface.name)
                        mesh_interface.online = False

                time.sleep(1)
            else:
                # Connection is down — attempt reconnect with backoff
                if reconnect_attempts >= RECONNECT_MAX_ATTEMPTS:
                    log.warning("%d reconnect attempts exhausted. Resetting...", RECONNECT_MAX_ATTEMPTS)
                    reconnect_attempts = 0
                    time.sleep(RECONNECT_MAX_DELAY)
                    continue

                delay = _backoff_delay(reconnect_attempts)
                reconnect_attempts += 1
                log.info("Reconnect attempt %d/%d in %.1fs...",
                         reconnect_attempts, RECONNECT_MAX_ATTEMPTS, delay)
                time.sleep(delay)

                if mesh_interface.reconnect():
                    log.info("Reconnected after %d attempt(s)!", reconnect_attempts)
                    reconnect_attempts = 0
                else:
                    log.warning("Reconnect attempt %d failed.", reconnect_attempts)

    except KeyboardInterrupt:
        log.info("Shutting down gateway...")
        mesh_interface.detach()
        sys.exit(0)

if __name__ == "__main__":
    try:
        start_gateway()
    except Exception as e:
        log.critical("Gateway crashed: %s", e, exc_info=True)
        sys.exit(1)
