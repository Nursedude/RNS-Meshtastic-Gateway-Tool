"""Tests for src.utils.threads – ThreadManager lifecycle."""
import threading
import time
import pytest
from src.utils.threads import ThreadManager


def _dummy_worker(stop_event, output):
    """Worker that runs until stop_event is set."""
    while not stop_event.is_set():
        stop_event.wait(0.05)
    output.append("stopped")


def _quick_worker():
    """Worker that exits immediately."""
    pass


class TestThreadManager:
    def test_start_and_stop_thread(self):
        mgr = ThreadManager()
        stop = threading.Event()
        output = []
        mgr.start_thread("w1", _dummy_worker, args=(stop, output), stop_event=stop)

        assert "w1" in mgr.running_threads
        assert mgr.stop_thread("w1", timeout=2)
        assert "stopped" in output
        assert "w1" not in mgr.running_threads

    def test_shutdown_stops_all(self):
        mgr = ThreadManager()
        stop1 = threading.Event()
        stop2 = threading.Event()
        out1, out2 = [], []
        mgr.start_thread("a", _dummy_worker, args=(stop1, out1), stop_event=stop1)
        mgr.start_thread("b", _dummy_worker, args=(stop2, out2), stop_event=stop2)

        assert len(mgr.running_threads) == 2
        still = mgr.shutdown(timeout=2)
        assert still == 0
        assert "stopped" in out1
        assert "stopped" in out2
        assert mgr.running_threads == []

    def test_stop_nonexistent_thread(self):
        mgr = ThreadManager()
        assert not mgr.stop_thread("nope")

    def test_quick_thread_completes(self):
        mgr = ThreadManager()
        mgr.start_thread("fast", _quick_worker)
        time.sleep(0.1)  # let it finish
        assert "fast" not in mgr.running_threads

    def test_running_threads_property(self):
        mgr = ThreadManager()
        stop = threading.Event()
        mgr.start_thread("x", _dummy_worker, args=(stop, []), stop_event=stop)
        assert "x" in mgr.running_threads
        stop.set()
        time.sleep(0.1)
        assert "x" not in mgr.running_threads
