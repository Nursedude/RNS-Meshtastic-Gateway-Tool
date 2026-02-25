"""Tests for src/utils/tx_queue.py — bounded transmit queue."""
import threading
import time

import pytest

from src.utils.tx_queue import TxQueue


class TestEnqueue:
    def test_enqueue_returns_true(self):
        sent = []
        q = TxQueue(send_fn=sent.append, maxsize=4)
        assert q.enqueue(b'\x01') is True

    def test_backpressure_when_full(self):
        sent = []
        q = TxQueue(send_fn=sent.append, maxsize=2)
        assert q.enqueue(b'\x01') is True
        assert q.enqueue(b'\x02') is True
        assert q.enqueue(b'\x03') is False  # Full
        assert q.dropped == 1

    def test_pending_count(self):
        sent = []
        q = TxQueue(send_fn=sent.append, maxsize=10)
        q.enqueue(b'\x01')
        q.enqueue(b'\x02')
        assert q.pending == 2


class TestDrain:
    def test_packets_are_sent(self):
        sent = []
        q = TxQueue(send_fn=sent.append, maxsize=10)
        q.enqueue(b'\x01')
        q.enqueue(b'\x02')
        q.start()
        time.sleep(0.2)
        q.stop()
        assert sent == [b'\x01', b'\x02']

    def test_exception_in_send_does_not_crash(self):
        def bad_send(data):
            raise OSError("radio disconnected")

        q = TxQueue(send_fn=bad_send, maxsize=10)
        q.enqueue(b'\x01')
        q.start()
        time.sleep(0.2)
        q.stop()
        # Should not raise — error is logged

    def test_stop_drains_cleanly(self):
        sent = []
        q = TxQueue(send_fn=sent.append, maxsize=10)
        q.start()
        q.enqueue(b'\x01')
        time.sleep(0.2)
        q.stop(timeout=2.0)
        assert q.pending == 0


class TestInterPacketDelay:
    def test_delay_fn_is_called(self):
        sent = []
        delay_calls = []

        def delay_fn():
            delay_calls.append(1)
            return 0.0  # No actual delay in test

        q = TxQueue(send_fn=sent.append, maxsize=10, inter_packet_delay_fn=delay_fn)
        q.enqueue(b'\x01')
        q.start()
        time.sleep(0.2)
        q.stop()
        assert len(delay_calls) >= 1
        assert sent == [b'\x01']


class TestStartStop:
    def test_double_start_is_safe(self):
        q = TxQueue(send_fn=lambda d: None, maxsize=10)
        q.start()
        q.start()  # Should not create a second thread
        q.stop()

    def test_stop_without_start_is_safe(self):
        q = TxQueue(send_fn=lambda d: None, maxsize=10)
        q.stop()  # Should not raise
