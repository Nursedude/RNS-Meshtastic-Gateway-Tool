"""
Broadcast Test — Send an RNS announce packet over the Meshtastic interface.

Verifies that the RNS→Meshtastic TX path is working. Watch the radio LED
for transmit activity during the hold period.

Usage:
    python scripts/broadcast.py [--timeout SECONDS]
"""
import argparse
import logging
import sys
import time

log = logging.getLogger("broadcast_test")


def broadcast_test(timeout=5):
    """Send an announce packet and hold the connection open.

    Args:
        timeout: Seconds to keep the connection open after announcing.

    Returns:
        0 on success, 1 on failure.
    """
    try:
        import RNS
    except ImportError:
        log.critical("RNS library not installed. Run: pip install rns")
        return 1

    log.info("Initializing Reticulum...")
    try:
        RNS.Reticulum()  # Initialize stack (instance used implicitly by RNS)
    except Exception as e:
        log.critical("Failed to initialize Reticulum: %s", e)
        return 1

    identity = RNS.Identity()

    print("=" * 50)
    print("   BROADCAST TEST")
    print("=" * 50)

    try:
        destination = RNS.Destination(
            identity, RNS.Destination.IN, RNS.Destination.SINGLE,
            "ping_test", "broadcast",
        )
    except Exception as e:
        log.error("Failed to create destination: %s", e)
        return 1

    log.info("Packaging announce packet...")
    try:
        destination.announce()
        log.info("Packet handed to Reticulum.")
    except Exception as e:
        log.error("Announce failed: %s", e)
        return 1

    print(f"\n  Holding connection open for {timeout}s — watch the radio LED.")
    time.sleep(timeout)

    log.info("Broadcast test complete.")
    return 0


def main():
    parser = argparse.ArgumentParser(description="RNS broadcast test over Meshtastic")
    parser.add_argument(
        '--timeout', type=int, default=5,
        help="Seconds to hold connection after announce (default: 5)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    sys.exit(broadcast_test(timeout=args.timeout))


if __name__ == "__main__":
    main()
