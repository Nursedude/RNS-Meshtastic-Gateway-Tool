import argparse
import logging
import os
import signal
import sys
import threading

# Add project root and src folder to path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, 'src'))

import RNS

from version import __version__
from src.utils.common import CONFIG_PATH, load_config
from src.utils.log import setup_logging, default_log_path, install_crash_handler
from src.utils.reconnect import ReconnectStrategy
from src.utils.bridge_health import BridgeHealthMonitor
from src.utils.health_probe import ActiveHealthProbe, HealthResult
from src.utils.threads import shutdown_all_threads

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


def start_gateway(debug=False):
    cfg = load_config()
    if not cfg:
        log.warning("Could not load %s. Using default settings.", CONFIG_PATH)
    gw_config = cfg.get("gateway", {})

    # Structured logging opt-in (MeshForge pattern)
    log_level = logging.DEBUG if debug else logging.INFO
    setup_logging(
        level=log_level,
        log_file=default_log_path(),
        structured=gw_config.get("structured_logging", False),
    )

    print("============================================================")
    print(f"  SUPERVISOR NOC | RNS-MESHTASTIC GATEWAY v{__version__}")
    print("============================================================")

    # 1. Initialize Reticulum (pass configdir to avoid EADDRINUSE when rnsd is running)
    rns_configdir = gw_config.get("rns_configdir", None)
    rns_connection = RNS.Reticulum(configdir=rns_configdir)

    log.info("Loading Interface 'Meshtastic Radio'...")

    # 2. Create reliability components before driver (MeshForge pattern)
    strategy = ReconnectStrategy.for_meshtastic()
    bridge_health = BridgeHealthMonitor()

    # Instantiate the Driver with bridge health + slow-start wiring
    mesh_interface = MeshtasticInterface(
        rns_connection, "Meshtastic Radio",
        config=gw_config,
        bridge_health=bridge_health,
        inter_packet_delay_fn=strategy.inter_packet_delay,
    )

    if mesh_interface.online:
        bridge_health.record_connection_event("meshtastic", "connected")
    else:
        log.warning("Initial connection failed. Will retry...")

    # 3. Active health probe with hysteresis (MeshForge pattern)
    #    3 consecutive failures before marking unhealthy (prevents false positives)
    health_probe = ActiveHealthProbe(
        interval=HEALTH_CHECK_INTERVAL, fails=3, passes=2,
    )
    health_probe.register_check(
        "meshtastic",
        lambda: HealthResult(
            healthy=mesh_interface.health_check(),
            reason="interface_health_check",
        ),
    )
    health_probe.start()

    # Signal handling for clean systemd/SIGTERM shutdown
    def _handle_signal(signum, frame):
        sig_name = signal.Signals(signum).name
        log.info("Received %s — shutting down gateway...", sig_name)
        _stop_event.set()

    signal.signal(signal.SIGTERM, _handle_signal)
    if hasattr(signal, 'SIGHUP'):
        signal.signal(signal.SIGHUP, _handle_signal)

    # 5. Main loop with health probe and auto-reconnect
    try:
        while not _stop_event.is_set():
            if mesh_interface.online:
                # Connection is healthy — reset attempt counter
                strategy.record_success()

                # Health probe runs in background with hysteresis.
                # Only mark offline if probe confirms sustained failure.
                if not health_probe.is_healthy("meshtastic"):
                    status = health_probe.get_status("meshtastic")
                    if status and status["state"] == "unhealthy":
                        log.warning("[%s] Health probe: UNHEALTHY — marking offline",
                                    mesh_interface.name)
                        mesh_interface.online = False
                        bridge_health.record_connection_event(
                            "meshtastic", "error", detail="health probe unhealthy")
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

    # Clean shutdown (MeshForge pattern: stop probes → detach → shutdown threads)
    health_probe.stop()
    mesh_interface.detach()
    shutdown_all_threads()
    sys.exit(0)

def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="RNS-Meshtastic Gateway — bridge Reticulum and Meshtastic networks",
    )
    parser.add_argument(
        "--version", action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--debug", action="store_true",
        help="Enable debug-level logging",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    install_crash_handler()
    args = _parse_args()
    try:
        start_gateway(debug=args.debug)
    except Exception as e:
        log.critical("Gateway crashed: %s", e, exc_info=True)
        sys.exit(1)
