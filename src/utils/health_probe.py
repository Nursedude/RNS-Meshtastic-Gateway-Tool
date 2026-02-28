"""
Active Health Probes for gateway services.

Based on MeshForge's utils/active_health_probe.py.  Implements the
NGINX active-health-check pattern: periodic background checks with
hysteresis to avoid false positives from transient glitches.

Key behaviour:
- ``fails`` consecutive failures before marking service UNHEALTHY
- ``passes`` consecutive passes before marking service HEALTHY
- Background thread runs checks at ``interval`` seconds

Usage:
    from src.utils.health_probe import ActiveHealthProbe, HealthResult

    probe = ActiveHealthProbe(interval=30, fails=3, passes=2)
    probe.register_check("meshtastic",
        lambda: HealthResult(healthy=True, reason="ok"))
    probe.start()

    if probe.is_healthy("meshtastic"):
        connect()

    probe.stop()
"""
import logging
import socket
import subprocess
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional

log = logging.getLogger("health_probe")


class HealthState(Enum):
    """Health state for a monitored service."""
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    RECOVERING = "recovering"


@dataclass
class HealthResult:
    """Result of a single health check."""
    healthy: bool
    reason: str = ""
    latency_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)

    def __bool__(self) -> bool:
        return bool(self.healthy)


@dataclass
class ServiceHealthState:
    """Tracks health state for a single service with hysteresis."""
    name: str
    state: HealthState = HealthState.UNKNOWN
    consecutive_passes: int = 0
    consecutive_fails: int = 0
    last_check: Optional[float] = None
    last_result: Optional[HealthResult] = None
    total_checks: int = 0
    total_passes: int = 0
    total_fails: int = 0

    @property
    def uptime_percent(self) -> float:
        if self.total_checks == 0:
            return 0.0
        return (self.total_passes / self.total_checks) * 100


class ActiveHealthProbe:
    """Proactive health checking for mesh services.

    Based on NGINX active health check pattern:
    - Periodic checks independent of traffic
    - Hysteresis: multiple consecutive fails before marking unhealthy
    - Recovery: multiple consecutive passes before marking healthy

    Args:
        interval: Seconds between health checks.
        fails:    Consecutive failures to mark service unhealthy.
        passes:   Consecutive passes to mark service healthy.
    """

    def __init__(
        self,
        interval: int = 30,
        fails: int = 3,
        passes: int = 2,
    ):
        self.interval = interval
        self.fails = fails
        self.passes = passes

        self._checks: Dict[str, Callable[[], HealthResult]] = {}
        self._states: Dict[str, ServiceHealthState] = {}
        self._callbacks: Dict[str, List[Callable]] = {
            "on_healthy": [],
            "on_unhealthy": [],
            "on_state_change": [],
        }

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()

    # ── Registration ─────────────────────────────────────────
    def register_check(
        self,
        service_name: str,
        check_fn: Callable[[], HealthResult],
    ) -> None:
        """Register a health check function for a service."""
        with self._lock:
            self._checks[service_name] = check_fn
            self._states[service_name] = ServiceHealthState(name=service_name)
            log.debug("Registered health check: %s", service_name)

    def register_callback(
        self,
        event: str,
        callback: Callable,
    ) -> None:
        """Register a callback for health state changes.

        Args:
            event:    "on_healthy", "on_unhealthy", or "on_state_change".
            callback: ``callback(service_name, new_state)``.
        """
        if event in self._callbacks:
            self._callbacks[event].append(callback)

    # ── Core Check Logic ─────────────────────────────────────
    def _run_check(self, service_name: str) -> HealthResult:
        """Run health check for a service and update state."""
        check_fn = self._checks.get(service_name)
        if not check_fn:
            return HealthResult(healthy=False, reason="no_check_registered")

        start = time.time()
        try:
            result = check_fn()
            result.latency_ms = (time.time() - start) * 1000
            result.timestamp = time.time()
        except Exception as exc:
            result = HealthResult(
                healthy=False,
                reason="check_exception: %s" % exc,
                latency_ms=(time.time() - start) * 1000,
            )

        with self._lock:
            state = self._states[service_name]
            old_state = state.state

            state.last_check = result.timestamp
            state.last_result = result
            state.total_checks += 1

            if result.healthy:
                state.consecutive_passes += 1
                state.consecutive_fails = 0
                state.total_passes += 1

                if state.state != HealthState.HEALTHY:
                    if state.consecutive_passes >= self.passes:
                        state.state = HealthState.HEALTHY
                        state.consecutive_passes = 0
                        log.info("Health probe: %s is now HEALTHY", service_name)
                    elif state.state == HealthState.UNHEALTHY:
                        state.state = HealthState.RECOVERING
                        log.debug(
                            "Health probe: %s recovering (%d/%d)",
                            service_name, state.consecutive_passes, self.passes,
                        )
            else:
                state.consecutive_fails += 1
                state.consecutive_passes = 0
                state.total_fails += 1

                if state.state != HealthState.UNHEALTHY:
                    if state.consecutive_fails >= self.fails:
                        state.state = HealthState.UNHEALTHY
                        state.consecutive_fails = 0
                        log.warning(
                            "Health probe: %s is now UNHEALTHY: %s",
                            service_name, result.reason,
                        )
                    elif state.state == HealthState.RECOVERING:
                        state.state = HealthState.UNHEALTHY
                        log.debug("Health probe: %s recovery failed", service_name)

            if old_state != state.state:
                self._fire_callbacks(service_name, state.state)

        return result

    def _fire_callbacks(self, service_name: str, new_state: HealthState) -> None:
        """Fire registered callbacks for a state change."""
        for cb in self._callbacks["on_state_change"]:
            try:
                cb(service_name, new_state)
            except Exception as exc:
                log.debug("Health callback error: %s", exc)

        key = "on_healthy" if new_state == HealthState.HEALTHY else (
            "on_unhealthy" if new_state == HealthState.UNHEALTHY else None
        )
        if key:
            for cb in self._callbacks[key]:
                try:
                    cb(service_name, new_state)
                except Exception as exc:
                    log.debug("Health callback error: %s", exc)

    # ── Background Thread ────────────────────────────────────
    def _probe_loop(self) -> None:
        """Background thread that runs periodic health checks.

        Outer try/except acts as a watchdog — if the loop body crashes
        we log and continue rather than letting the probe die silently.
        """
        log.info(
            "Active health probe started (interval=%ds, fails=%d, passes=%d)",
            self.interval, self.fails, self.passes,
        )
        loop_errors = 0

        while not self._stop_event.is_set():
            try:
                services = list(self._checks.keys())
                for svc in services:
                    if self._stop_event.is_set():
                        break
                    try:
                        self._run_check(svc)
                    except Exception as exc:
                        log.debug("Health check error for %s: %s", svc, exc)

                self._stop_event.wait(self.interval)
            except Exception as exc:
                loop_errors += 1
                log.warning("Health probe loop error #%d: %s", loop_errors, exc)
                self._stop_event.wait(min(self.interval, 5))

        log.info("Active health probe stopped")

    def start(self) -> None:
        """Start the background health probe thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._probe_loop, daemon=True, name="health-probe",
        )
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        """Stop the background health probe thread."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=timeout)

    # ── Query Methods ────────────────────────────────────────
    def check_now(self, service_name: str) -> HealthResult:
        """Run an immediate health check (bypass interval)."""
        return self._run_check(service_name)

    def is_healthy(self, service_name: str) -> bool:
        """True if service state is HEALTHY."""
        with self._lock:
            state = self._states.get(service_name)
            if not state:
                return False
            return state.state == HealthState.HEALTHY

    def get_status(self, service_name: str) -> Optional[Dict]:
        """Get detailed health status for a service."""
        with self._lock:
            state = self._states.get(service_name)
            if not state:
                return None
            return {
                "name": state.name,
                "state": state.state.value,
                "consecutive_passes": state.consecutive_passes,
                "consecutive_fails": state.consecutive_fails,
                "last_check": state.last_check,
                "last_result": {
                    "healthy": bool(state.last_result.healthy),
                    "reason": state.last_result.reason,
                    "latency_ms": state.last_result.latency_ms,
                } if state.last_result is not None else None,
                "uptime_percent": round(state.uptime_percent, 1),
                "total_checks": state.total_checks,
            }

    def get_all_status(self) -> Dict[str, Dict]:
        """Get health status for all registered services."""
        result = {}
        for svc in self._checks:
            status = self.get_status(svc)
            if status:
                result[svc] = status
        return result

    # ── Built-in Check Functions ─────────────────────────────
    def check_tcp_port(self, port: int, host: str = "localhost") -> HealthResult:
        """Check if a TCP port is accepting connections."""
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex((host, port))
            if result == 0:
                return HealthResult(healthy=True, reason="connected")
            return HealthResult(healthy=False, reason="connect_failed_%d" % result)
        except socket.timeout:
            return HealthResult(healthy=False, reason="timeout")
        except socket.error as exc:
            return HealthResult(healthy=False, reason="socket_error: %s" % exc)
        finally:
            if sock:
                try:
                    sock.close()
                except Exception:  # noqa: S110
                    pass

    def check_systemd_service(self, service_name: str) -> HealthResult:
        """Check if a systemd service is active."""
        try:
            result = subprocess.run(
                ["systemctl", "is-active", service_name],
                capture_output=True, text=True, timeout=5,
            )
            status = result.stdout.strip()
            if status == "active":
                return HealthResult(healthy=True, reason="active")
            return HealthResult(healthy=False, reason="status_%s" % status)
        except subprocess.TimeoutExpired:
            return HealthResult(healthy=False, reason="timeout")
        except FileNotFoundError:
            return HealthResult(healthy=False, reason="systemctl_not_found")
        except Exception as exc:
            return HealthResult(healthy=False, reason=str(exc)[:100])


# ── Module-level singleton ───────────────────────────────────
_health_probe: Optional[ActiveHealthProbe] = None
_probe_lock = threading.Lock()


def get_health_probe(
    interval: int = 30,
    fails: int = 3,
    passes: int = 2,
) -> ActiveHealthProbe:
    """Get the singleton health probe, creating it on first call.

    The probe is NOT started automatically — call ``.start()`` when ready.
    """
    global _health_probe
    with _probe_lock:
        if _health_probe is not None:
            return _health_probe
        _health_probe = ActiveHealthProbe(
            interval=interval, fails=fails, passes=passes,
        )
        return _health_probe
