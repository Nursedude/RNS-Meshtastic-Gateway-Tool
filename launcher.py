import RNS
import logging
import os
import signal
import sys
import threading
import time

# Add project root and src folder to path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, 'src'))

from version import __version__
from src.utils.common import CONFIG_PATH, load_config
from src.utils.log import setup_logging
from src.utils.reconnect import ReconnectStrategy

log = logging.getLogger("gateway")

# Import the custom driver
try:
    from Meshtastic_Interface import MeshtasticInterface
except ImportError as e:
    logging.basicConfig()
    log.critical("Could not import Meshtastic Driver: %s", e)
    sys.exit(1)

HEALTH_CHECK_INTERVAL = 30      # seconds between connection health checks

# Module-level stop event for clean shutdown
_stop_event = threading.Event()


def start_gateway():
    cfg = load_config()
    if not cfg:
        log.warning("Could not load %s. Using default settings.", CONFIG_PATH)
    gw_config = cfg.get("gateway", {})

    # Structured logging opt-in (MeshForge pattern)
    setup_logging(structured=gw_config.get("structured_logging", False))

    print("============================================================")
    print(f"  SUPERVISOR NOC | RNS-MESHTASTIC GATEWAY v{__version__}")
    print("============================================================")

    # 1. Initialize Reticulum (pass configdir to avoid EADDRINUSE when rnsd is running)
    rns_configdir = gw_config.get("rns_configdir", None)
    rns_connection = RNS.Reticulum(configdir=rns_configdir)

    log.info("Loading Interface 'Meshtastic Radio'...")

    # 2. Instantiate the Driver
    mesh_interface = MeshtasticInterface(rns_connection, "Meshtastic Radio", config=gw_config)

    if not mesh_interface.online:
        log.warning("Initial connection failed. Will retry...")

    # 3. Signal handling for clean systemd/SIGTERM shutdown
    def _handle_signal(signum, frame):
        sig_name = signal.Signals(signum).name
        log.info("Received %s — shutting down gateway...", sig_name)
        _stop_event.set()

    signal.signal(signal.SIGTERM, _handle_signal)
    if hasattr(signal, 'SIGHUP'):
        signal.signal(signal.SIGHUP, _handle_signal)

    # 4. Main loop with health check and auto-reconnect
    strategy = ReconnectStrategy.for_meshtastic()
    last_health_check = 0.0

    try:
        while not _stop_event.is_set():
            if mesh_interface.online:
                # Connection is healthy — reset attempt counter
                strategy.record_success()

                # Periodic health check: verify the interface is still responsive
                now = time.time()
                if now - last_health_check >= HEALTH_CHECK_INTERVAL:
                    last_health_check = now
                    if not mesh_interface.health_check():
                        log.warning("[%s] Health check failed", mesh_interface.name)
                        mesh_interface.online = False
                        continue

                # Interruptible sleep — wakes immediately on SIGTERM
                _stop_event.wait(1)
            else:
                # Connection is down — attempt reconnect with backoff
                if not strategy.should_retry():
                    log.warning("%d reconnect attempts exhausted. Resetting...",
                                strategy.max_attempts)
                    strategy.reset()
                    strategy.wait(_stop_event, timeout=strategy.max_delay)
                    continue

                delay = strategy.get_delay()
                strategy.record_failure()
                log.info("Reconnect attempt %d/%d in %.1fs...",
                         strategy.attempts, strategy.max_attempts, delay)
                strategy.wait(_stop_event, timeout=delay)

                if _stop_event.is_set():
                    break

                if mesh_interface.reconnect():
                    log.info("Reconnected after %d attempt(s)!", strategy.attempts)
                    strategy.record_success()
                else:
                    log.warning("Reconnect attempt %d failed.", strategy.attempts)

    except KeyboardInterrupt:
        log.info("Shutting down gateway...")

    # Clean shutdown
    mesh_interface.detach()
    sys.exit(0)

if __name__ == "__main__":
    try:
        start_gateway()
    except Exception as e:
        log.critical("Gateway crashed: %s", e, exc_info=True)
        sys.exit(1)
