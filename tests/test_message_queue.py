"""Tests for src/utils/message_queue.py — SQLite persistent message queue."""
import sqlite3
import time

import pytest

from src.utils.message_queue import (
    MessageQueue,
    MessageStatus,
    Priority,
    _calculate_backoff,
    _content_hash,
)


# ── Helper function tests ─────────────────────────────────────


class TestContentHash:
    def test_deterministic(self):
        assert _content_hash(b'\x01\x02') == _content_hash(b'\x01\x02')

    def test_different_data_different_hash(self):
        assert _content_hash(b'\x01') != _content_hash(b'\x02')

    def test_length_is_32(self):
        assert len(_content_hash(b'test')) == 32

    def test_empty_data(self):
        h = _content_hash(b'')
        assert len(h) == 32


class TestCalculateBackoff:
    def test_initial_delay(self):
        delay = _calculate_backoff(0)
        assert delay == pytest.approx(2.0)

    def test_exponential_growth(self):
        d0 = _calculate_backoff(0)
        d1 = _calculate_backoff(1)
        d2 = _calculate_backoff(2)
        assert d1 > d0
        assert d2 > d1

    def test_capped_at_max(self):
        delay = _calculate_backoff(100)
        assert delay <= 60.0


# ── Enqueue tests ──────────────────────────────────────────────


class TestEnqueue:
    def test_enqueue_returns_id(self, tmp_path):
        mq = MessageQueue(send_fn=lambda d: None, db_path=str(tmp_path / "test.db"))
        msg_id = mq.enqueue(b'\x01\x02')
        assert msg_id is not None
        assert len(msg_id) == 36  # UUID4

    def test_pending_count_increases(self, tmp_path):
        mq = MessageQueue(send_fn=lambda d: None, db_path=str(tmp_path / "test.db"))
        mq.enqueue(b'\x01')
        mq.enqueue(b'\x02')
        assert mq.pending_count == 2

    def test_high_priority_dispatched_first(self, tmp_path):
        mq = MessageQueue(send_fn=lambda d: None, db_path=str(tmp_path / "test.db"))
        mq.enqueue(b'\x01', priority=Priority.NORMAL)
        mq.enqueue(b'\x02', priority=Priority.HIGH)
        msg = mq.get_next_pending()
        assert msg.data == b'\x02'  # HIGH priority first

    def test_persists_to_sqlite(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        mq = MessageQueue(send_fn=lambda d: None, db_path=db_path)
        mq.enqueue(b'\x01\x02')
        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        assert count == 1
        conn.close()


# ── Deduplication tests ────────────────────────────────────────


class TestDeduplication:
    def test_duplicate_within_window_returns_none(self, tmp_path):
        mq = MessageQueue(send_fn=lambda d: None, db_path=str(tmp_path / "test.db"))
        id1 = mq.enqueue(b'\x01')
        id2 = mq.enqueue(b'\x01')  # Same content
        assert id1 is not None
        assert id2 is None

    def test_different_content_not_deduped(self, tmp_path):
        mq = MessageQueue(send_fn=lambda d: None, db_path=str(tmp_path / "test.db"))
        id1 = mq.enqueue(b'\x01')
        id2 = mq.enqueue(b'\x02')
        assert id1 is not None
        assert id2 is not None

    def test_pending_count_after_dedup(self, tmp_path):
        mq = MessageQueue(send_fn=lambda d: None, db_path=str(tmp_path / "test.db"))
        mq.enqueue(b'\x01')
        mq.enqueue(b'\x01')  # Duplicate
        assert mq.pending_count == 1


# ── Delivery tests ─────────────────────────────────────────────


class TestDelivery:
    def test_mark_delivered(self, tmp_path):
        mq = MessageQueue(send_fn=lambda d: None, db_path=str(tmp_path / "test.db"))
        msg_id = mq.enqueue(b'\x01')
        mq.mark_delivered(msg_id)
        assert mq.pending_count == 0

    def test_drain_sends_and_delivers(self, tmp_path):
        sent = []
        mq = MessageQueue(
            send_fn=lambda d: sent.append(d),
            db_path=str(tmp_path / "test.db"),
        )
        mq.enqueue(b'\x01')
        mq.start()
        time.sleep(0.5)
        mq.stop()
        assert sent == [b'\x01']
        assert mq.pending_count == 0

    def test_drain_multiple_messages(self, tmp_path):
        sent = []
        mq = MessageQueue(
            send_fn=lambda d: sent.append(d),
            db_path=str(tmp_path / "test.db"),
        )
        mq.enqueue(b'\x01')
        mq.enqueue(b'\x02')
        mq.enqueue(b'\x03')
        mq.start()
        time.sleep(1.0)
        mq.stop()
        assert len(sent) == 3
        assert mq.pending_count == 0


# ── Retry tests ────────────────────────────────────────────────


class TestRetry:
    def test_transient_error_retries(self, tmp_path):
        attempts = []

        def failing_send(data):
            attempts.append(1)
            raise ConnectionError("timeout")

        mq = MessageQueue(
            send_fn=failing_send,
            db_path=str(tmp_path / "test.db"),
            max_retries=3,
        )
        mq.enqueue(b'\x01')
        mq.start()
        time.sleep(1.5)
        mq.stop()
        assert len(attempts) >= 1

    def test_permanent_error_dead_letters(self, tmp_path):
        def perm_fail(data):
            raise PermissionError("permission denied")

        mq = MessageQueue(
            send_fn=perm_fail,
            db_path=str(tmp_path / "test.db"),
        )
        mq.enqueue(b'\x01')
        mq.start()
        time.sleep(0.5)
        mq.stop()
        assert mq.dead_letter_count == 1
        assert mq.pending_count == 0

    def test_max_retries_dead_letters(self, tmp_path):
        def fail_send(data):
            raise ConnectionError("timeout")

        mq = MessageQueue(
            send_fn=fail_send,
            db_path=str(tmp_path / "test.db"),
            max_retries=2,
        )
        mq.enqueue(b'\x01')
        # Manually simulate retry exhaustion
        msg = mq.get_next_pending()
        for _ in range(3):
            mq.mark_failed(msg.id, ConnectionError("timeout"))
        assert mq.dead_letter_count == 1


# ── Dead letter tests ──────────────────────────────────────────


class TestDeadLetter:
    def test_get_dead_letters(self, tmp_path):
        def perm_fail(data):
            raise PermissionError("permission denied")

        mq = MessageQueue(
            send_fn=perm_fail,
            db_path=str(tmp_path / "test.db"),
        )
        mq.enqueue(b'\x01')
        mq.start()
        time.sleep(0.5)
        mq.stop()
        dead = mq.get_dead_letters()
        assert len(dead) == 1
        assert dead[0].data == b'\x01'

    def test_retry_dead_letter(self, tmp_path):
        mq = MessageQueue(send_fn=lambda d: None, db_path=str(tmp_path / "test.db"))
        msg_id = mq.enqueue(b'\x01')
        # Force to dead letter via permanent error (message must match pattern)
        mq.mark_failed(msg_id, PermissionError("permission denied"))
        assert mq.dead_letter_count == 1
        assert mq.retry_dead_letter(msg_id) is True
        assert mq.pending_count == 1
        assert mq.dead_letter_count == 0


# ── Persistence tests ──────────────────────────────────────────


class TestPersistence:
    def test_survives_restart(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        mq1 = MessageQueue(send_fn=lambda d: None, db_path=db_path)
        mq1.enqueue(b'\x01')
        mq1.enqueue(b'\x02')
        mq1.close()

        # Re-open the same DB
        sent = []
        mq2 = MessageQueue(
            send_fn=lambda d: sent.append(d),
            db_path=db_path,
        )
        assert mq2.pending_count == 2
        mq2.start()
        time.sleep(1.0)
        mq2.stop()
        assert set(sent) == {b'\x01', b'\x02'}

    def test_in_progress_recovered_on_startup(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        mq1 = MessageQueue(send_fn=lambda d: None, db_path=db_path)
        msg_id = mq1.enqueue(b'\x01')
        # Manually set to IN_PROGRESS (simulating crash mid-send)
        conn = mq1._get_conn()
        conn.execute(
            "UPDATE messages SET status = ? WHERE id = ?",
            (MessageStatus.IN_PROGRESS.value, msg_id),
        )
        conn.commit()
        mq1.close()

        # New instance should recover it
        mq2 = MessageQueue(send_fn=lambda d: None, db_path=db_path)
        assert mq2.pending_count == 1
        mq2.close()


# ── Stats tests ────────────────────────────────────────────────


class TestStats:
    def test_get_stats(self, tmp_path):
        mq = MessageQueue(send_fn=lambda d: None, db_path=str(tmp_path / "test.db"))
        mq.enqueue(b'\x01')
        stats = mq.get_stats()
        assert stats[MessageStatus.PENDING.value] >= 1

    def test_purge_delivered(self, tmp_path):
        mq = MessageQueue(send_fn=lambda d: None, db_path=str(tmp_path / "test.db"))
        msg_id = mq.enqueue(b'\x01')
        mq.mark_delivered(msg_id)
        count = mq.purge_delivered(older_than=0)
        assert count == 1


# ── Start/Stop tests ──────────────────────────────────────────


class TestStartStop:
    def test_double_start_safe(self, tmp_path):
        mq = MessageQueue(send_fn=lambda d: None, db_path=str(tmp_path / "test.db"))
        mq.start()
        mq.start()  # Should not create second thread
        mq.stop()

    def test_stop_without_start_safe(self, tmp_path):
        mq = MessageQueue(send_fn=lambda d: None, db_path=str(tmp_path / "test.db"))
        mq.stop()  # Should not raise

    def test_close(self, tmp_path):
        mq = MessageQueue(send_fn=lambda d: None, db_path=str(tmp_path / "test.db"))
        mq.enqueue(b'\x01')
        mq.close()  # Should not raise


# ── Status change callback tests ──────────────────────────────


class TestStatusCallback:
    def test_callback_invoked(self, tmp_path):
        changes = []

        def on_change(msg_id, old, new):
            changes.append((msg_id, old, new))

        mq = MessageQueue(
            send_fn=lambda d: None,
            db_path=str(tmp_path / "test.db"),
            on_status_change=on_change,
        )
        msg_id = mq.enqueue(b'\x01')
        mq.mark_delivered(msg_id)
        # Should have at least: enqueue (None->pending) + delivered
        assert len(changes) >= 2
        assert changes[-1][2] == MessageStatus.DELIVERED.value
