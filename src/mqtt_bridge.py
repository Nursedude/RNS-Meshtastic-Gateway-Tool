"""
MQTT Bridge Handler — zero-interference bridge to meshtasticd.

RX: Subscribe to MQTT topic ``msh/{region}/2/json/{channel}/#`` to
    receive mesh messages without blocking the meshtasticd web client.
TX: POST HTTP protobuf to ``http://localhost:9443/api/v1/toradio``.

Presents the same public interface as ``MeshtasticInterface`` so
``launcher.py`` can swap between direct and MQTT modes transparently.

Usage (in config.json):
    "gateway": {
        "bridge_mode": "mqtt",
        "mqtt_host": "localhost",
        "mqtt_port": 1883,
        "mqtt_topic_root": "msh",
        "mqtt_region": "US",
        "http_api_port": 9443
    }
"""

import base64
import collections
import json
import logging
import threading
import time
import urllib.request
import urllib.error
from typing import Any, Dict, Optional

import paho.mqtt.client as mqtt

from src.utils.circuit_breaker import CircuitBreaker
from src.utils.timeouts import (
    MQTT_DEDUP_WINDOW,
    MQTT_KEEPALIVE,
    MQTT_RECONNECT_MAX,
    MQTT_RECONNECT_MIN,
    HTTP_TORADIO_TIMEOUT,
)

log = logging.getLogger("mqtt_bridge")


class MqttBridge:
    """MQTT bridge to meshtasticd — zero interference with web client.

    RX: Subscribe to MQTT topic ``msh/{region}/2/json/{channel}/#``
    TX: POST HTTP protobuf to meshtasticd REST API
    """

    MESHTASTIC_MAX_PAYLOAD = 228

    def __init__(
        self,
        owner: Any,
        name: str,
        config: Optional[Dict[str, Any]] = None,
        bridge_health=None,
        inter_packet_delay_fn=None,
    ) -> None:
        cfg = config or {}

        # --- RNS COMPLIANCE SECTION ---
        self.owner = owner
        self.name = name
        self.online = False
        self.IN = True
        self.OUT = False
        self.bitrate = cfg.get("bitrate", 500)
        self.rxb = 0
        self.txb = 0
        self.rx_packets = 0
        self.tx_packets = 0
        self.tx_errors = 0
        self.detached = False

        self.ingress_control = False
        self.held_announces = []
        self.rate_violation_occurred = False
        self.clients = 0
        self.ia_freq_deque = collections.deque(maxlen=100)
        self.oa_freq_deque = collections.deque(maxlen=100)
        self.announce_cap = 0
        self.ifac_identity = None

        try:
            import RNS
            self.mode = RNS.Interfaces.Interface.MODE_ACCESS_POINT
        except BaseException:  # RNS may crash (PanicException) or be missing
            self.mode = 1

        # --- MQTT CONFIG ---
        self._mqtt_host = cfg.get("mqtt_host", "localhost")
        self._mqtt_port = cfg.get("mqtt_port", 1883)
        self._topic_root = cfg.get("mqtt_topic_root", "msh")
        self._region = cfg.get("mqtt_region", "US")
        http_api_port = cfg.get("http_api_port", 9443)
        self._http_api_url = (
            cfg.get("http_api_url")
            or f"http://localhost:{http_api_port}/api/v1/toradio"
        )

        # Build subscribe topic: msh/{region}/2/json/#
        self._subscribe_topic = f"{self._topic_root}/{self._region}/2/json/#"

        # --- RELIABILITY ---
        self._bridge_health = bridge_health
        self._inter_packet_delay_fn = inter_packet_delay_fn
        self._circuit_breaker = CircuitBreaker()

        # --- TX QUEUE ---
        features = cfg.get("features", {}) if isinstance(cfg, dict) else {}
        self._use_message_queue = features.get("message_queue", False)
        self._use_tx_queue = features.get("tx_queue", True)
        self._message_queue = None
        self._tx_queue = None

        if self._use_message_queue:
            from src.utils.message_queue import MessageQueue
            self._message_queue = MessageQueue(
                send_fn=self._do_send,
                inter_packet_delay_fn=self._inter_packet_delay_fn,
                on_status_change=self._on_queue_status_change,
            )
        elif self._use_tx_queue:
            from src.utils.tx_queue import TxQueue
            self._tx_queue = TxQueue(
                send_fn=self._do_send,
                maxsize=32,
                inter_packet_delay_fn=self._inter_packet_delay_fn,
            )

        # --- DEDUPLICATION ---
        self._seen_ids: Dict[str, float] = {}
        self._dedup_lock = threading.Lock()
        self._last_dedup_cleanup = time.monotonic()

        # --- MQTT CLIENT ---
        self._mqtt_client: Optional[mqtt.Client] = None
        self._connect_mqtt()

        # Start queues after connection
        if self._message_queue and self.online:
            self._message_queue.start()
        elif self._tx_queue and self.online:
            self._tx_queue.start()

    def _on_queue_status_change(self, msg_id, old_status, new_status):
        """Handle message queue status changes for logging."""
        log.debug("[%s] Message %s: %s -> %s",
                  self.name, msg_id[:8] if msg_id else "?",
                  old_status, new_status)

    # ── MQTT Connection ──────────────────────────────────────────

    def _connect_mqtt(self) -> None:
        """Initialize and connect the MQTT client."""
        try:
            self._mqtt_client = mqtt.Client(
                callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            )
            self._mqtt_client.on_connect = self._on_connect
            self._mqtt_client.on_disconnect = self._on_disconnect
            self._mqtt_client.on_message = self._on_message
            self._mqtt_client.reconnect_delay_set(
                min_delay=int(MQTT_RECONNECT_MIN),
                max_delay=int(MQTT_RECONNECT_MAX),
            )

            log.info("[%s] Connecting to MQTT broker %s:%s...",
                     self.name, self._mqtt_host, self._mqtt_port)
            self._mqtt_client.connect(
                self._mqtt_host,
                self._mqtt_port,
                keepalive=MQTT_KEEPALIVE,
            )
            self._mqtt_client.loop_start()
        except (OSError, ConnectionError, ValueError) as e:
            log.error("[%s] MQTT connection error: %s", self.name, e)
            if self._bridge_health:
                self._bridge_health.record_connection_event(
                    "meshtastic", "error", detail=str(e))

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        """MQTT on_connect callback — subscribe to mesh topic."""
        if rc == 0:
            log.info("[%s] MQTT connected. Subscribing to %s",
                     self.name, self._subscribe_topic)
            client.subscribe(self._subscribe_topic)
            self.online = True
            self.OUT = True
            if self._bridge_health:
                self._bridge_health.record_connection_event(
                    "meshtastic", "connected")
            try:
                from src.utils.event_bus import emit_service_status
                emit_service_status("meshtastic", True, "MQTT connected")
            except Exception:  # noqa: S110
                pass
        else:
            log.error("[%s] MQTT connect failed (rc=%s)", self.name, rc)
            self.online = False
            self.OUT = False

    def _on_disconnect(self, client, userdata, flags, rc, properties=None):
        """MQTT on_disconnect callback."""
        log.warning("[%s] MQTT disconnected (rc=%s). Auto-reconnect active.",
                    self.name, rc)
        self.online = False
        self.OUT = False
        if self._bridge_health:
            self._bridge_health.record_connection_event(
                "meshtastic", "disconnected")
        try:
            from src.utils.event_bus import emit_service_status
            emit_service_status("meshtastic", False, "MQTT disconnected")
        except Exception:  # noqa: S110
            pass

    # ── RX Path (MQTT → RNS) ─────────────────────────────────────

    def _on_message(self, client, userdata, msg):
        """MQTT message callback — parse JSON, pass to RNS."""
        try:
            payload_str = msg.payload.decode("utf-8", errors="replace")
            data = json.loads(payload_str)

            # Deduplication by message ID
            msg_id = str(data.get("id", ""))
            if msg_id and self._is_duplicate(msg_id):
                log.debug("[%s] Duplicate message %s — skipping", self.name, msg_id)
                return

            # Extract payload bytes
            # meshtasticd JSON format: {"payload": "<base64>", ...}
            encoded = data.get("payload")
            if not encoded:
                log.debug("[%s] MQTT message has no payload field", self.name)
                return

            if isinstance(encoded, str):
                raw_bytes = base64.b64decode(encoded)
            elif isinstance(encoded, bytes):
                raw_bytes = encoded
            else:
                log.warning("[%s] Unexpected payload type: %s",
                            self.name, type(encoded).__name__)
                return

            self.rxb += len(raw_bytes)
            self.rx_packets += 1

            if self._bridge_health:
                self._bridge_health.record_message_sent("mesh_to_rns")

            # Event bus notification
            try:
                from src.utils.event_bus import emit_message
                node_id = data.get("from", data.get("sender", ""))
                emit_message(
                    direction="rx",
                    content=repr(raw_bytes[:32]),
                    node_id=str(node_id),
                    network="meshtastic",
                    raw_data=data,
                )
            except Exception:  # noqa: S110
                pass

            if self._circuit_breaker:
                self._circuit_breaker.record_success()

            # Pass to RNS transport
            self.owner.inbound(raw_bytes, self)

        except json.JSONDecodeError as e:
            log.warning("[%s] MQTT RX: invalid JSON: %s", self.name, e)
        except (KeyError, TypeError, ValueError) as e:
            log.warning("[%s] MQTT RX error (packet dropped): %s", self.name, e)

    # ── TX Path (RNS → Mesh via HTTP) ────────────────────────────

    def _do_send(self, data: bytes) -> None:
        """Low-level send: POST data to meshtasticd HTTP API."""
        try:
            if len(data) > self.MESHTASTIC_MAX_PAYLOAD:
                log.warning("[%s] Payload %d bytes exceeds limit (%d).",
                            self.name, len(data), self.MESHTASTIC_MAX_PAYLOAD)

            log.debug("[%s] >>> HTTP POST %d bytes to %s",
                      self.name, len(data), self._http_api_url)

            req = urllib.request.Request(  # noqa: S310
                self._http_api_url,
                data=data,
                headers={"Content-Type": "application/x-protobuf"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=HTTP_TORADIO_TIMEOUT):  # noqa: S310
                pass

            self.txb += len(data)
            self.tx_packets += 1
            log.debug("[%s] >>> HTTP POST success.", self.name)

            if self._circuit_breaker:
                self._circuit_breaker.record_success()
            if self._bridge_health:
                self._bridge_health.record_message_sent("rns_to_mesh")

            try:
                from src.utils.event_bus import emit_message
                emit_message(
                    direction="tx",
                    content=repr(data[:32]),
                    network="meshtastic",
                )
            except Exception:  # noqa: S110
                pass

        except (urllib.error.URLError, OSError, ValueError) as e:
            self.tx_errors += 1
            if self._circuit_breaker:
                self._circuit_breaker.record_failure()
            if self._bridge_health:
                self._bridge_health.record_message_failed("rns_to_mesh")
                self._bridge_health.record_error("meshtastic", e)
            log.error("[%s] HTTP TX error: %s", self.name, e)

    def process_incoming(self, data: bytes) -> None:
        """Handle data from RNS → mesh (TX via HTTP)."""
        if not (self.online and self._mqtt_client):
            return

        if self._circuit_breaker and not self._circuit_breaker.allow_request():
            log.warning("[%s] Circuit breaker OPEN — TX blocked", self.name)
            return

        if self._message_queue:
            self._message_queue.enqueue(data)
        elif self._tx_queue:
            self._tx_queue.enqueue(data)
        else:
            self._do_send(data)

    def process_outgoing(self, data: bytes) -> None:
        """Handle outbound data from RNS (delegates to process_incoming)."""
        self.process_incoming(data)

    # ── Deduplication ─────────────────────────────────────────────

    def _is_duplicate(self, msg_id: str) -> bool:
        """Check if message ID was seen within the dedup window."""
        now = time.monotonic()
        with self._dedup_lock:
            if msg_id in self._seen_ids:
                return True
            self._seen_ids[msg_id] = now
            # Periodic cleanup
            if now - self._last_dedup_cleanup > MQTT_DEDUP_WINDOW:
                cutoff = now - MQTT_DEDUP_WINDOW
                self._seen_ids = {
                    k: v for k, v in self._seen_ids.items() if v > cutoff
                }
                self._last_dedup_cleanup = now
            return False

    # ── Health & Reconnect ────────────────────────────────────────

    def health_check(self) -> bool:
        """Active health probe — checks MQTT connection and circuit breaker."""
        if self._mqtt_client is None:
            return False
        if not self._mqtt_client.is_connected():
            return False
        if self._circuit_breaker and not self._circuit_breaker.allow_request():
            from src.utils.circuit_breaker import State
            if self._circuit_breaker.state is State.OPEN:
                log.warning("[%s] Health check: circuit breaker OPEN (%d failures)",
                            self.name, self._circuit_breaker.failures)
                return False
        return True

    def reconnect(self) -> bool:
        """Attempt to reconnect MQTT client."""
        log.info("[%s] Attempting MQTT reconnect...", self.name)

        # Stop queues
        if self._message_queue:
            self._message_queue.stop()
        if self._tx_queue:
            self._tx_queue.stop()

        # Tear down existing client
        if self._mqtt_client:
            try:
                self._mqtt_client.loop_stop()
                self._mqtt_client.disconnect()
            except (OSError, AttributeError):
                pass
            self._mqtt_client = None

        self.online = False
        self.OUT = False

        if self._bridge_health:
            self._bridge_health.record_connection_event(
                "meshtastic", "disconnected")

        if self._circuit_breaker:
            self._circuit_breaker.reset()

        # Reconnect
        self._connect_mqtt()

        # Restart queues
        if self._message_queue and self.online:
            self._message_queue.start()
        elif self._tx_queue and self.online:
            self._tx_queue.start()

        if self._bridge_health and self.online:
            self._bridge_health.record_connection_event(
                "meshtastic", "connected")

        return self.online

    def detach(self) -> None:
        """Clean shutdown — stop MQTT loop, disconnect."""
        if self._message_queue:
            self._message_queue.stop()
        if self._tx_queue:
            self._tx_queue.stop()

        if self._mqtt_client:
            try:
                self._mqtt_client.loop_stop()
                self._mqtt_client.disconnect()
            except (OSError, AttributeError) as e:
                log.warning("[%s] Warning during detach: %s", self.name, e)

        self.detached = True
        self.online = False
        log.info("[%s] MQTT Bridge detached.", self.name)

    @property
    def metrics(self) -> dict:
        """Snapshot of interface metrics for dashboard/monitoring."""
        m = {
            "tx_packets": self.tx_packets,
            "rx_packets": self.rx_packets,
            "tx_bytes": self.txb,
            "rx_bytes": self.rxb,
            "tx_errors": self.tx_errors,
            "online": self.online,
            "bridge_mode": "mqtt",
            "mqtt_host": self._mqtt_host,
            "mqtt_port": self._mqtt_port,
        }
        if self._message_queue:
            m["message_queue_pending"] = self._message_queue.pending_count
            m["message_queue_dead_letters"] = self._message_queue.dead_letter_count
        if self._tx_queue:
            m["tx_queue_pending"] = self._tx_queue.pending
            m["tx_queue_dropped"] = self._tx_queue.dropped
        if self._circuit_breaker:
            m["circuit_breaker_state"] = self._circuit_breaker.state.value
            m["circuit_breaker_failures"] = self._circuit_breaker.failures
        return m

    def __str__(self):
        return (
            f"MQTT Bridge ({self._mqtt_host}:{self._mqtt_port} "
            f"→ {self._http_api_url})"
        )

    def __repr__(self):
        return (
            f"<MqttBridge name={self.name!r} "
            f"mqtt={self._mqtt_host}:{self._mqtt_port} "
            f"online={self.online} "
            f"tx={self.tx_packets}pkt/{self.txb}B "
            f"rx={self.rx_packets}pkt/{self.rxb}B "
            f"errors={self.tx_errors}>"
        )
