"""
Bounded transmit queue with a dedicated drain thread.

Decouples RNS transport callbacks from radio I/O so that
process_incoming() never blocks the RNS thread.  Inspired by
MeshForge's gateway/message_queue.py but stripped to essentials.
"""
import logging
import queue
import threading

log = logging.getLogger("tx_queue")


class TxQueue:
    """Thread-safe bounded FIFO with a daemon drain thread.

    Args:
        send_fn: Callable that actually transmits one packet (bytes).
        maxsize: Maximum queued packets before backpressure kicks in.
        inter_packet_delay_fn: Optional callable returning seconds to
            sleep between packets (e.g. for slow-start recovery).
    """

    def __init__(self, send_fn, maxsize=32, inter_packet_delay_fn=None):
        self._send_fn = send_fn
        self._queue = queue.Queue(maxsize=maxsize)
        self._delay_fn = inter_packet_delay_fn
        self._stop = threading.Event()
        self._thread = None
        self._dropped = 0
        self._lock = threading.Lock()

    def start(self) -> None:
        """Start the drain thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._drain, daemon=True, name="tx-drain")
        self._thread.start()

    def stop(self, timeout=2.0) -> None:
        """Signal the drain thread to stop and wait for it."""
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=timeout)
            self._thread = None

    def enqueue(self, data: bytes) -> bool:
        """Add a packet to the queue.  Returns False on backpressure (queue full)."""
        try:
            self._queue.put_nowait(data)
            return True
        except queue.Full:
            with self._lock:
                self._dropped += 1
            log.warning("TX queue full — packet dropped (%d total dropped)", self._dropped)
            return False

    @property
    def dropped(self) -> int:
        with self._lock:
            return self._dropped

    @property
    def pending(self) -> int:
        return self._queue.qsize()

    def _drain(self) -> None:
        """Drain loop: pull packets and send them."""
        import time

        while not self._stop.is_set():
            try:
                data = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            # Inter-packet delay for slow-start recovery
            if self._delay_fn:
                delay = self._delay_fn()
                if delay > 0:
                    time.sleep(delay)

            try:
                self._send_fn(data)
            except Exception as e:
                log.error("TX drain send error: %s", e)
