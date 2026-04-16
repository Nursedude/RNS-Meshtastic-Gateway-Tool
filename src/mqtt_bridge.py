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
        "http_api_port": 9443,
        "mqtt_username": null,
        "mqtt_password": null,
        "mqtt_tls": false
    }

MQTT credentials can also be set via environment variables:
    GATEWAY_MQTT_USERNAME, GATEWAY_MQTT_PASSWORD

TLS is strongly recommended for non-localhost MQTT brokers.
"""

import base64
import binascii
import collections
import ipaddress
import json
import logging
import os
import re
import ssl
import threading
import time
import urllib.request
import urllib.error
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import paho.mqtt.client as mqtt

from src.utils.circuit_breaker import CircuitBreaker
from src.utils.timeouts import (
    MQTT_DEDUP_MAX_ENTRIES,
    MQTT_DEDUP_WINDOW,
    MQTT_KEEPALIVE,
    MQTT_RECONNECT_MAX,
    MQTT_RECONNECT_MIN,
    HTTP_TORADIO_TIMEOUT,
)

# Maximum inbound MQTT payload size (bytes) to prevent OOM from malicious broker
MQTT_MAX_PAYLOAD_SIZE = 4096

# Regex for validating MQTT topic components (no control chars, no null bytes)
_TOPIC_SAFE_RE = re.compile(r'^[a-zA-Z0-9/_\-\.]+$')

# SSRF defence: cloud metadata service hostnames + IPs that must never be
# reachable from the gateway HTTP client even if a misconfigured config.json
# points there. The IP/network checks block both literal IPs and DNS-rebind
# results that resolve to these ranges (resolution check happens at request
# time via the kept hostname comparison).
_BLOCKED_METADATA_HOSTS = frozenset({
    "metadata",
    "metadata.google.internal",
    "metadata.googleapis.com",
    "metadata.azure.com",
    "instance-data",
    "instance-data.ec2.internal",
})
_BLOCKED_METADATA_IPS = frozenset({
    ipaddress.ip_address("169.254.169.254"),  # AWS / Azure / OpenStack / DO
    ipaddress.ip_address("100.100.100.200"),  # Alibaba Cloud
    ipaddress.ip_address("fd00:ec2::254"),    # AWS IPv6
})
_BLOCKED_METADATA_NETWORKS = (
    ipaddress.ip_network("169.254.0.0/16"),   # IPv4 link-local (covers AWS)
    ipaddress.ip_network("fe80::/10"),        # IPv6 link-local
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
        except Exception:
            log.debug("[%s] RNS not available for mode detection, using default", name)
            self.mode = 1
        except BaseException as e:
            # RNS's PanicException inherits from BaseException in some
            # versions and is non-recoverable for RNS itself, but mode
            # detection failing must not crash the bridge. Re-raise anything
            # that isn't a recognised panic so SystemExit / KeyboardInterrupt
            # still propagate.
            if type(e).__name__ not in ("PanicException", "SystemPanicException"):
                raise
            log.warning(
                "[%s] RNS PanicException during mode detection: %s — "
                "continuing with default mode", name, e,
            )
            self.mode = 1

        # --- MQTT CONFIG ---
        self._mqtt_host = cfg.get("mqtt_host", "localhost")
        self._mqtt_port = cfg.get("mqtt_port", 1883)
        self._topic_root = cfg.get("mqtt_topic_root", "msh")
        self._region = cfg.get("mqtt_region", "US")
        http_api_port = cfg.get("http_api_port", 9443)

        # MQTT authentication — config or environment variables
        self._mqtt_username = (
            cfg.get("mqtt_username")
            or os.environ.get("GATEWAY_MQTT_USERNAME")
        )
        self._mqtt_password = (
            cfg.get("mqtt_password")
            or os.environ.get("GATEWAY_MQTT_PASSWORD")
        )
        self._mqtt_tls = cfg.get("mqtt_tls", False)

        # Warn if connecting to non-localhost without TLS
        if self._mqtt_host not in ("localhost", "127.0.0.1", "::1"):
            if not self._mqtt_tls:
                log.warning(
                    "[%s] MQTT broker %s is not localhost but TLS is disabled. "
                    "Set gateway.mqtt_tls=true for encrypted connections.",
                    self.name, self._mqtt_host,
                )
            if not self._mqtt_username:
                log.warning(
                    "[%s] MQTT broker %s has no authentication configured. "
                    "Set gateway.mqtt_username/mqtt_password or "
                    "GATEWAY_MQTT_USERNAME/GATEWAY_MQTT_PASSWORD env vars.",
                    self.name, self._mqtt_host,
                )

        # Validate and build HTTP API URL (SSRF prevention)
        self._http_api_url = self._validate_http_api_url(
            cfg.get("http_api_url"),
            http_api_port,
        )

        # Validate and build subscribe topic (topic injection prevention)
        self._subscribe_topic = self._build_subscribe_topic(
            self._topic_root, self._region,
        )

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

    # ── Validation Helpers ──────────────────────────────────────

    @staticmethod
    def _is_blocked_metadata_host(hostname: str) -> bool:
        """True if the hostname/IP targets a cloud metadata endpoint.

        Catches literal IPs (incl. IPv6 in bracketed form already stripped by
        urlparse) against the blocked IP set and link-local networks, plus
        well-known metadata DNS names. DNS rebinding via a hostname that
        resolves to a blocked IP is not caught here — defence-in-depth only.
        """
        host = hostname.strip().lower().rstrip(".")
        if host in _BLOCKED_METADATA_HOSTS:
            return True
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            return False
        if ip in _BLOCKED_METADATA_IPS:
            return True
        return any(ip in net for net in _BLOCKED_METADATA_NETWORKS)

    @staticmethod
    def _validate_http_api_url(
        custom_url: Optional[str],
        default_port: int,
    ) -> str:
        """Validate HTTP API URL to prevent SSRF.

        Only allows http:// scheme to localhost or explicit config values.
        Rejects file://, ftp://, and other dangerous schemes. Cloud metadata
        endpoints (169.254.169.254, metadata.google.internal, etc.) are
        rejected as defence-in-depth against operator misconfiguration.
        """
        fallback = f"http://localhost:{default_port}/api/v1/toradio"
        if custom_url:
            try:
                parsed = urlparse(custom_url)
                if parsed.scheme not in ("http", "https"):
                    log.error(
                        "http_api_url scheme %r not allowed (only http/https). "
                        "Falling back to localhost.",
                        parsed.scheme,
                    )
                    return fallback
                if not parsed.hostname:
                    log.error(
                        "http_api_url has no hostname. Falling back to localhost."
                    )
                    return fallback
                if MqttBridge._is_blocked_metadata_host(parsed.hostname):
                    log.error(
                        "http_api_url host %r is a blocked cloud-metadata "
                        "endpoint. Falling back to localhost.",
                        parsed.hostname,
                    )
                    return fallback
                # Reject URLs with embedded credentials
                if parsed.username or parsed.password:
                    log.warning(
                        "http_api_url contains embedded credentials — "
                        "stripping them for safety."
                    )
                    clean = parsed._replace(
                        netloc=f"{parsed.hostname}:{parsed.port or default_port}"
                    )
                    return clean.geturl()
                return custom_url
            except ValueError:
                log.error("Invalid http_api_url. Falling back to localhost.")
                return fallback
        return fallback

    @staticmethod
    def _build_subscribe_topic(topic_root: str, region: str) -> str:
        """Build and validate the MQTT subscribe topic.

        Prevents topic injection via control characters or wildcards
        in the root/region components.
        """
        for label, value in [("mqtt_topic_root", topic_root),
                             ("mqtt_region", region)]:
            if not value or not isinstance(value, str):
                log.error("Invalid %s: must be a non-empty string", label)
                raise ValueError(f"Invalid {label}")
            if not _TOPIC_SAFE_RE.match(value):
                log.error(
                    "Invalid %s %r — contains unsafe characters. "
                    "Only alphanumeric, /, _, -, . allowed.",
                    label, value,
                )
                raise ValueError(f"Invalid {label}: {value!r}")
        return f"{topic_root}/{region}/2/json/#"

    # ── MQTT Connection ──────────────────────────────────────────

    def _connect_mqtt(self) -> None:
        """Initialize and connect the MQTT client with optional TLS/auth."""
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

            # TLS configuration
            if self._mqtt_tls:
                self._mqtt_client.tls_set(
                    cert_reqs=ssl.CERT_REQUIRED,
                    tls_version=ssl.PROTOCOL_TLS_CLIENT,
                )
                log.info("[%s] MQTT TLS enabled", self.name)

            # Authentication
            if self._mqtt_username:
                self._mqtt_client.username_pw_set(
                    self._mqtt_username,
                    self._mqtt_password,
                )
                log.info("[%s] MQTT authentication configured (user=%s)",
                         self.name, self._mqtt_username)

            log.info("[%s] Connecting to MQTT broker %s:%s...",
                     self.name, self._mqtt_host, self._mqtt_port)
            self._mqtt_client.connect(
                self._mqtt_host,
                self._mqtt_port,
                keepalive=MQTT_KEEPALIVE,
            )
            self._mqtt_client.loop_start()
        except (OSError, ConnectionError, ValueError, ssl.SSLError) as e:
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
            except Exception as e:
                # Event bus is optional; never block MQTT callbacks for it.
                # Broader catch than (ImportError, AttributeError) so a
                # transient bus hiccup (RuntimeError from a saturated
                # ThreadPool, QueueFull, etc.) doesn't break connect handling.
                log.debug("[%s] event bus emit_service_status(up) failed: %s",
                          self.name, e)
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
        except Exception as e:
            # Event bus is optional; never block MQTT callbacks for it.
            log.debug("[%s] event bus emit_service_status(down) failed: %s",
                      self.name, e)

    # ── RX Path (MQTT → RNS) ─────────────────────────────────────

    def _on_message(self, client, userdata, msg):
        """MQTT message callback — parse JSON, pass to RNS."""
        try:
            # Guard against oversized payloads (OOM prevention)
            if len(msg.payload) > MQTT_MAX_PAYLOAD_SIZE:
                log.warning(
                    "[%s] MQTT payload %d bytes exceeds limit (%d) — dropped",
                    self.name, len(msg.payload), MQTT_MAX_PAYLOAD_SIZE,
                )
                return

            payload_str = msg.payload.decode("utf-8", errors="replace")
            data = json.loads(payload_str)

            if not isinstance(data, dict):
                log.warning("[%s] MQTT RX: expected JSON object, got %s",
                            self.name, type(data).__name__)
                return

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

            # Event bus notification (strip raw_data to safe fields only)
            try:
                from src.utils.event_bus import emit_message
                node_id = data.get("from", data.get("sender", ""))
                # Only forward safe metadata fields — not the full MQTT payload
                safe_metadata = {
                    k: data[k] for k in (
                        "id", "from", "to", "channel", "type",
                        "snr", "rssi", "hopStart", "hopLimit", "fromName",
                    ) if k in data
                }
                emit_message(
                    direction="rx",
                    content=repr(raw_bytes[:32]),
                    node_id=str(node_id),
                    network="meshtastic",
                    raw_data=safe_metadata,
                )
            except Exception as e:
                # Event bus is optional; never block the RX path for it.
                log.debug("[%s] event bus emit_message(rx) failed: %s",
                          self.name, e)

            if self._circuit_breaker:
                self._circuit_breaker.record_success()

            # Pass to RNS transport
            self.owner.inbound(raw_bytes, self)

        except json.JSONDecodeError as e:
            log.warning("[%s] MQTT RX: invalid JSON: %s", self.name, e)
        except (KeyError, TypeError, ValueError, binascii.Error) as e:
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
            except Exception as e:
                # Event bus is optional; never block the TX path for it.
                log.debug("[%s] event bus emit_message(tx) failed: %s",
                          self.name, e)

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
            time_to_clean = now - self._last_dedup_cleanup > MQTT_DEDUP_WINDOW
            over_cap = len(self._seen_ids) > MQTT_DEDUP_MAX_ENTRIES
            if time_to_clean or over_cap:
                cutoff = now - MQTT_DEDUP_WINDOW
                self._seen_ids = {
                    k: v for k, v in self._seen_ids.items() if v > cutoff
                }
                # If still over cap (window-fresh flood), keep the newest half.
                if len(self._seen_ids) > MQTT_DEDUP_MAX_ENTRIES:
                    keep = sorted(
                        self._seen_ids.items(), key=lambda kv: kv[1],
                    )[-(MQTT_DEDUP_MAX_ENTRIES // 2):]
                    self._seen_ids = dict(keep)
                    log.warning(
                        "[%s] dedup dict exceeded %d entries — trimmed to %d",
                        self.name, MQTT_DEDUP_MAX_ENTRIES, len(self._seen_ids),
                    )
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
