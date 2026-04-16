"""
SQLite-backed persistent message queue with retry and deduplication.

Adapted from MeshForge's gateway/message_queue.py.  Messages survive
restarts, get automatic retry with exponential backoff, and move to
a dead-letter queue after exhausting retries.

Usage:
    from src.utils.message_queue import MessageQueue, Priority

    mq = MessageQueue(send_fn=radio.send)
    mq.start()
    mq.enqueue(b'\\x01\\x02\\x03')
    # ... messages are drained and sent automatically ...
    mq.stop()
"""

import hashlib
import logging
import os
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from enum import Enum, IntEnum
from typing import Callable, Dict, List, Optional

from src.utils.bridge_health import classify_error
from src.utils.timeouts import (
    MSG_QUEUE_POLL,
    MSG_QUEUE_MAX_RETRIES,
    MSG_QUEUE_RETRY_INITIAL,
    MSG_QUEUE_RETRY_MAX,
    MSG_QUEUE_RETRY_MULTIPLIER,
    MSG_QUEUE_DEDUP_WINDOW,
    MSG_QUEUE_DEDUP_CLEANUP,
)

log = logging.getLogger("message_queue")


# ── Enums ────────────────────────────────────────────────────

class MessageStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DELIVERED = "delivered"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


class Priority(IntEnum):
    NORMAL = 0
    HIGH = 1


# ── Data Classes ─────────────────────────────────────────────

@dataclass
class QueuedMessage:
    """In-memory representation of a queued message row."""
    id: str
    data: bytes
    content_hash: str
    priority: int
    status: str
    attempts: int
    max_retries: int
    created_at: float
    updated_at: float
    next_retry: Optional[float]
    error: Optional[str]
    error_class: Optional[str]


# ── Helper Functions ─────────────────────────────────────────

def _default_db_path() -> str:
    """Return the default SQLite DB path: ~/.config/rns-gateway/message_queue.db"""
    from src.utils.common import get_real_user_home
    config_dir = os.path.join(get_real_user_home(), ".config", "rns-gateway")
    os.makedirs(config_dir, mode=0o700, exist_ok=True)
    # Ensure directory permissions are correct even if it already existed
    try:
        os.chmod(config_dir, 0o700)
    except OSError:
        pass
    return os.path.join(config_dir, "message_queue.db")


def _content_hash(data: bytes) -> str:
    """Compute truncated SHA-256 hex digest (32 chars = 128 bits)."""
    return hashlib.sha256(data).hexdigest()[:32]


def _calculate_backoff(attempt: int) -> float:
    """Exponential backoff: initial * multiplier^attempt, capped at max."""
    delay = MSG_QUEUE_RETRY_INITIAL * (MSG_QUEUE_RETRY_MULTIPLIER ** attempt)
    return min(delay, MSG_QUEUE_RETRY_MAX)


# ── SQL Schema ───────────────────────────────────────────────

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS messages (
    id           TEXT PRIMARY KEY,
    data         BLOB NOT NULL,
    content_hash TEXT NOT NULL,
    priority     INTEGER NOT NULL DEFAULT 0,
    status       TEXT NOT NULL DEFAULT 'pending',
    attempts     INTEGER NOT NULL DEFAULT 0,
    max_retries  INTEGER NOT NULL DEFAULT 5,
    created_at   REAL NOT NULL,
    updated_at   REAL NOT NULL,
    next_retry   REAL,
    error        TEXT,
    error_class  TEXT
);

CREATE INDEX IF NOT EXISTS idx_messages_status
    ON messages(status);
CREATE INDEX IF NOT EXISTS idx_messages_priority_created
    ON messages(priority DESC, created_at ASC);
CREATE INDEX IF NOT EXISTS idx_messages_next_retry
    ON messages(next_retry);

CREATE TABLE IF NOT EXISTS dedup_hashes (
    content_hash TEXT PRIMARY KEY,
    created_at   REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_dedup_created
    ON dedup_hashes(created_at);
"""


# ── MessageQueue ─────────────────────────────────────────────

class MessageQueue:
    """SQLite-backed persistent message queue with drain thread.

    Args:
        send_fn: Callable(bytes) that transmits one packet.
                 Must raise on failure, return normally on success.
        db_path: Path to SQLite database file.  Defaults to
                 ~/.config/rns-gateway/message_queue.db.
        max_retries: Default max retry attempts per message.
        on_status_change: Optional callback(msg_id, old_status, new_status)
                          for event bus integration.
        inter_packet_delay_fn: Optional callable returning seconds to
            sleep between packets (e.g. for slow-start recovery).
    """

    def __init__(
        self,
        send_fn: Callable[[bytes], None],
        db_path: Optional[str] = None,
        max_retries: int = MSG_QUEUE_MAX_RETRIES,
        on_status_change: Optional[Callable] = None,
        inter_packet_delay_fn: Optional[Callable] = None,
    ):
        self._send_fn = send_fn
        self._db_path = db_path or _default_db_path()
        self._max_retries = max_retries
        self._on_status_change = on_status_change
        self._delay_fn = inter_packet_delay_fn
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._local = threading.local()
        self._last_dedup_cleanup = 0.0

        self._init_db()
        self._recover_in_progress()

    # ── Database ──────────────────────────────────────────────

    def _init_db(self) -> None:
        """Create tables and indexes if they do not exist."""
        conn = self._get_conn()
        conn.executescript(_SCHEMA_SQL)
        conn.commit()

    def _get_conn(self) -> sqlite3.Connection:
        """Get a thread-local SQLite connection.

        Each thread gets its own connection for safety.
        WAL mode allows concurrent reads while one thread writes.
        """
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            conn = sqlite3.connect(self._db_path)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return self._local.conn

    def _recover_in_progress(self) -> int:
        """Reset IN_PROGRESS messages to PENDING on startup.

        Messages stuck in IN_PROGRESS were mid-flight when the process died.
        Returns the number of recovered messages.
        """
        conn = self._get_conn()
        now = time.time()
        cursor = conn.execute(
            "UPDATE messages SET status = ?, updated_at = ? WHERE status = ?",
            (MessageStatus.PENDING.value, now, MessageStatus.IN_PROGRESS.value),
        )
        conn.commit()
        count = cursor.rowcount
        if count > 0:
            log.info("Recovered %d in-progress message(s) from previous run", count)
        return count

    # ── Enqueue ───────────────────────────────────────────────

    def enqueue(
        self,
        data: bytes,
        priority: Priority = Priority.NORMAL,
    ) -> Optional[str]:
        """Add a message to the persistent queue.

        Returns:
            Message ID (UUID) if enqueued, None if deduplicated.
        """
        content_hash = _content_hash(data)

        conn = self._get_conn()

        # Deduplication check
        now = time.time()
        cutoff = now - MSG_QUEUE_DEDUP_WINDOW
        row = conn.execute(
            "SELECT 1 FROM dedup_hashes WHERE content_hash = ? AND created_at > ?",
            (content_hash, cutoff),
        ).fetchone()
        if row is not None:
            log.debug("Duplicate message rejected (hash=%s)", content_hash[:8])
            return None

        # Insert message
        msg_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO messages "
            "(id, data, content_hash, priority, status, attempts, max_retries, "
            " created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?)",
            (msg_id, data, content_hash, int(priority),
             MessageStatus.PENDING.value, self._max_retries, now, now),
        )

        # Record dedup hash
        conn.execute(
            "INSERT OR REPLACE INTO dedup_hashes (content_hash, created_at) VALUES (?, ?)",
            (content_hash, now),
        )
        conn.commit()

        self._emit_status_change(msg_id, None, MessageStatus.PENDING.value)
        log.debug("Enqueued message %s (priority=%s, %d bytes)",
                  msg_id[:8], Priority(priority).name, len(data))
        return msg_id

    # ── Delivery Tracking ────────────────────────────────────

    def mark_delivered(self, msg_id: str) -> None:
        """Mark a message as successfully delivered."""
        conn = self._get_conn()
        now = time.time()
        conn.execute(
            "UPDATE messages SET status = ?, updated_at = ? WHERE id = ?",
            (MessageStatus.DELIVERED.value, now, msg_id),
        )
        conn.commit()
        self._emit_status_change(msg_id, MessageStatus.IN_PROGRESS.value,
                                 MessageStatus.DELIVERED.value)

    def mark_failed(self, msg_id: str, error: Exception) -> None:
        """Mark a message as failed; schedule retry or dead-letter.

        Permanent errors and exhausted retries go to DEAD_LETTER.
        Transient errors go back to PENDING with exponential backoff.
        """
        category = classify_error(error)
        conn = self._get_conn()
        now = time.time()

        row = conn.execute(
            "SELECT attempts, max_retries FROM messages WHERE id = ?",
            (msg_id,),
        ).fetchone()
        if row is None:
            return

        attempts = row["attempts"]
        max_retries = row["max_retries"]

        if category == "permanent" or attempts >= max_retries:
            # Dead letter
            conn.execute(
                "UPDATE messages SET status = ?, error = ?, error_class = ?, "
                "updated_at = ? WHERE id = ?",
                (MessageStatus.DEAD_LETTER.value, str(error)[:500],
                 category, now, msg_id),
            )
            conn.commit()
            self._emit_status_change(msg_id, MessageStatus.IN_PROGRESS.value,
                                     MessageStatus.DEAD_LETTER.value)
            log.warning("Message %s dead-lettered: %s (%s)",
                        msg_id[:8], error, category)
        else:
            # Schedule retry with backoff
            next_retry = now + _calculate_backoff(attempts)
            conn.execute(
                "UPDATE messages SET status = ?, attempts = attempts + 1, "
                "next_retry = ?, error = ?, error_class = ?, updated_at = ? "
                "WHERE id = ?",
                (MessageStatus.PENDING.value, next_retry,
                 str(error)[:500], category, now, msg_id),
            )
            conn.commit()
            self._emit_status_change(msg_id, MessageStatus.IN_PROGRESS.value,
                                     MessageStatus.PENDING.value)
            log.debug("Message %s scheduled for retry (attempt %d/%d, backoff %.1fs)",
                      msg_id[:8], attempts + 1, max_retries,
                      next_retry - now)

    # ── Drain Thread ──────────────────────────────────────────

    def get_next_pending(self) -> Optional[QueuedMessage]:
        """Fetch the highest-priority oldest PENDING message ready for retry.

        Returns None if no dispatchable messages exist.
        """
        conn = self._get_conn()
        now = time.time()
        row = conn.execute(
            "SELECT * FROM messages "
            "WHERE status = ? AND (next_retry IS NULL OR next_retry <= ?) "
            "ORDER BY priority DESC, created_at ASC "
            "LIMIT 1",
            (MessageStatus.PENDING.value, now),
        ).fetchone()

        if row is None:
            return None

        return QueuedMessage(
            id=row["id"],
            data=row["data"],
            content_hash=row["content_hash"],
            priority=row["priority"],
            status=row["status"],
            attempts=row["attempts"],
            max_retries=row["max_retries"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            next_retry=row["next_retry"],
            error=row["error"],
            error_class=row["error_class"],
        )

    def start(self) -> None:
        """Start the drain thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._drain, daemon=True, name="mq-drain",
        )
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        """Stop the drain thread and wait."""
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=timeout)
            self._thread = None

    def _drain(self) -> None:
        """Drain loop: pull PENDING messages and send them."""
        while not self._stop.is_set():
            try:
                msg = self.get_next_pending()
                if msg is None:
                    self._stop.wait(MSG_QUEUE_POLL)
                    self._periodic_dedup_cleanup()
                    continue

                # Mark IN_PROGRESS
                conn = self._get_conn()
                conn.execute(
                    "UPDATE messages SET status = ?, updated_at = ? WHERE id = ?",
                    (MessageStatus.IN_PROGRESS.value, time.time(), msg.id),
                )
                conn.commit()
                self._emit_status_change(msg.id, MessageStatus.PENDING.value,
                                         MessageStatus.IN_PROGRESS.value)

                # Inter-packet delay for slow-start recovery
                if self._delay_fn:
                    delay = self._delay_fn()
                    if delay > 0:
                        time.sleep(delay)

                # Attempt send
                try:
                    self._send_fn(msg.data)
                    self.mark_delivered(msg.id)
                except Exception as e:
                    self.mark_failed(msg.id, e)

                self._periodic_dedup_cleanup()

            except Exception as e:
                log.error("Message queue drain error: %s", e)
                self._stop.wait(MSG_QUEUE_POLL)

    def _periodic_dedup_cleanup(self) -> None:
        """Delete expired dedup hashes periodically."""
        now = time.time()
        if now - self._last_dedup_cleanup < MSG_QUEUE_DEDUP_CLEANUP:
            return
        self._last_dedup_cleanup = now
        try:
            conn = self._get_conn()
            cutoff = now - MSG_QUEUE_DEDUP_WINDOW
            conn.execute(
                "DELETE FROM dedup_hashes WHERE created_at < ?", (cutoff,),
            )
            conn.commit()
        except Exception as e:
            log.debug("Dedup cleanup error: %s", e)

    # ── Query / Stats ─────────────────────────────────────────

    def get_stats(self) -> Dict[str, int]:
        """Return queue statistics for dashboards."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT status, COUNT(*) as cnt FROM messages GROUP BY status",
        ).fetchall()
        stats = {s.value: 0 for s in MessageStatus}
        for row in rows:
            stats[row["status"]] = row["cnt"]
        return stats

    def get_dead_letters(self, limit: int = 50) -> List[QueuedMessage]:
        """Retrieve dead-lettered messages for inspection."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM messages WHERE status = ? "
            "ORDER BY updated_at DESC LIMIT ?",
            (MessageStatus.DEAD_LETTER.value, limit),
        ).fetchall()
        return [
            QueuedMessage(
                id=r["id"], data=r["data"], content_hash=r["content_hash"],
                priority=r["priority"], status=r["status"],
                attempts=r["attempts"], max_retries=r["max_retries"],
                created_at=r["created_at"], updated_at=r["updated_at"],
                next_retry=r["next_retry"], error=r["error"],
                error_class=r["error_class"],
            )
            for r in rows
        ]

    def retry_dead_letter(self, msg_id: str) -> bool:
        """Move a dead-lettered message back to PENDING for manual retry."""
        conn = self._get_conn()
        now = time.time()
        cursor = conn.execute(
            "UPDATE messages SET status = ?, attempts = 0, next_retry = NULL, "
            "error = NULL, error_class = NULL, updated_at = ? "
            "WHERE id = ? AND status = ?",
            (MessageStatus.PENDING.value, now, msg_id,
             MessageStatus.DEAD_LETTER.value),
        )
        conn.commit()
        if cursor.rowcount > 0:
            self._emit_status_change(msg_id, MessageStatus.DEAD_LETTER.value,
                                     MessageStatus.PENDING.value)
            return True
        return False

    def purge_delivered(self, older_than: float = 3600.0) -> int:
        """Delete delivered messages older than threshold.

        Args:
            older_than: Age in seconds. Messages delivered more than
                this many seconds ago are deleted.

        Returns:
            Number of messages deleted.
        """
        conn = self._get_conn()
        cutoff = time.time() - older_than
        cursor = conn.execute(
            "DELETE FROM messages WHERE status = ? AND updated_at < ?",
            (MessageStatus.DELIVERED.value, cutoff),
        )
        conn.commit()
        return cursor.rowcount

    @property
    def pending_count(self) -> int:
        """Number of messages in PENDING status."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE status = ?",
            (MessageStatus.PENDING.value,),
        ).fetchone()
        return row[0]

    @property
    def dead_letter_count(self) -> int:
        """Number of messages in DEAD_LETTER status."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE status = ?",
            (MessageStatus.DEAD_LETTER.value,),
        ).fetchone()
        return row[0]

    # ── Event Bus ─────────────────────────────────────────────

    def _emit_status_change(
        self, msg_id: str, old_status: Optional[str], new_status: str,
    ) -> None:
        """Emit queue status change event."""
        if self._on_status_change:
            try:
                self._on_status_change(msg_id, old_status, new_status)
            except Exception as e:
                log.debug("Status change callback error: %s", e)
        try:
            from src.utils.event_bus import event_bus
            event_bus.emit('queue_status', {
                'msg_id': msg_id,
                'old_status': old_status,
                'new_status': new_status,
                'timestamp': time.time(),
            })
        except Exception as e:
            log.debug("Event bus emit error: %s", e)

    # ── Cleanup ───────────────────────────────────────────────

    def close(self) -> None:
        """Stop drain thread and close database connections."""
        self.stop()
        if hasattr(self._local, 'conn') and self._local.conn is not None:
            self._local.conn.close()
            self._local.conn = None
