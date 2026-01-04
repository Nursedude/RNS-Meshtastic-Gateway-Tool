"""
Status dashboard for RNS-Meshtastic Gateway Tool.

Provides real-time system status display with service monitoring,
system health metrics, and bridge status.
"""

import time
from dataclasses import dataclass
from typing import Optional, Dict, Any, List

from ..utils.system import (
    get_cpu_temperature,
    get_cpu_usage,
    get_available_memory,
    get_disk_space,
    is_service_running,
    is_raspberry_pi,
    get_board_model,
    run_command,
)
from ..gateway.rns_bridge import RNSMeshtasticBridge
from ..gateway.node_tracker import UnifiedNodeTracker


@dataclass
class ServiceStatus:
    """Status of a monitored service."""

    name: str
    running: bool
    version: Optional[str] = None
    details: Optional[str] = None


@dataclass
class SystemMetrics:
    """System resource metrics."""

    cpu_usage: Optional[float] = None
    cpu_temperature: Optional[float] = None
    memory_available_mb: Optional[float] = None
    memory_total_mb: Optional[float] = None
    disk_free_mb: Optional[float] = None
    disk_total_mb: Optional[float] = None
    load_average: Optional[tuple] = None


class StatusDashboard:
    """
    Real-time status dashboard for gateway monitoring.

    Provides system health metrics, service status,
    and bridge statistics in a unified view.
    """

    def __init__(
        self,
        bridge: Optional[RNSMeshtasticBridge] = None,
        node_tracker: Optional[UnifiedNodeTracker] = None
    ):
        """
        Initialize the status dashboard.

        Args:
            bridge: RNS-Meshtastic bridge instance
            node_tracker: Node tracker instance
        """
        self.bridge = bridge
        self.node_tracker = node_tracker or UnifiedNodeTracker()

    def get_service_status(self) -> List[ServiceStatus]:
        """
        Get status of monitored services.

        Returns:
            List of ServiceStatus objects
        """
        services = []

        # Check meshtasticd
        meshtasticd_running = is_service_running("meshtasticd")
        meshtasticd_version = None
        if meshtasticd_running:
            rc, stdout, _ = run_command("meshtasticd --version 2>/dev/null", suppress_errors=True)
            if rc == 0:
                meshtasticd_version = stdout.strip()

        services.append(ServiceStatus(
            name="meshtasticd",
            running=meshtasticd_running,
            version=meshtasticd_version
        ))

        # Check RNS service (if applicable)
        rns_running = is_service_running("rnsd")
        services.append(ServiceStatus(
            name="rnsd",
            running=rns_running
        ))

        return services

    def get_system_metrics(self) -> SystemMetrics:
        """
        Get current system resource metrics.

        Returns:
            SystemMetrics object
        """
        metrics = SystemMetrics()

        # CPU
        metrics.cpu_usage = get_cpu_usage()
        metrics.cpu_temperature = get_cpu_temperature()

        # Memory
        available_mb = get_available_memory()
        if available_mb >= 0:
            metrics.memory_available_mb = available_mb
            # Estimate total (rough)
            try:
                with open("/proc/meminfo") as f:
                    for line in f:
                        if line.startswith("MemTotal:"):
                            metrics.memory_total_mb = int(line.split()[1]) / 1024
                            break
            except Exception:
                pass

        # Disk
        total, used, free = get_disk_space("/")
        if free >= 0:
            metrics.disk_free_mb = free
            metrics.disk_total_mb = total

        # Load average
        try:
            with open("/proc/loadavg") as f:
                parts = f.read().split()
                metrics.load_average = (
                    float(parts[0]),
                    float(parts[1]),
                    float(parts[2])
                )
        except Exception:
            pass

        return metrics

    def get_bridge_status(self) -> Dict[str, Any]:
        """
        Get bridge service status.

        Returns:
            Bridge status dictionary
        """
        if not self.bridge:
            return {
                "available": False,
                "running": False,
            }

        status = self.bridge.get_status()
        status["available"] = True
        return status

    def get_node_summary(self) -> Dict[str, Any]:
        """
        Get summary of tracked nodes.

        Returns:
            Node statistics dictionary
        """
        return self.node_tracker.get_statistics()

    def get_full_status(self) -> Dict[str, Any]:
        """
        Get comprehensive status report.

        Returns:
            Complete status dictionary
        """
        services = self.get_service_status()
        metrics = self.get_system_metrics()
        bridge = self.get_bridge_status()
        nodes = self.get_node_summary()

        # Calculate overall health
        health_score = self._calculate_health_score(services, metrics, bridge)

        return {
            "timestamp": time.time(),
            "health_score": health_score,
            "platform": {
                "is_raspberry_pi": is_raspberry_pi(),
                "board_model": get_board_model(),
            },
            "services": [
                {
                    "name": s.name,
                    "running": s.running,
                    "version": s.version,
                    "details": s.details,
                }
                for s in services
            ],
            "system": {
                "cpu_usage": metrics.cpu_usage,
                "cpu_temperature": metrics.cpu_temperature,
                "memory_available_mb": metrics.memory_available_mb,
                "memory_total_mb": metrics.memory_total_mb,
                "disk_free_mb": metrics.disk_free_mb,
                "disk_total_mb": metrics.disk_total_mb,
                "load_average": metrics.load_average,
            },
            "bridge": bridge,
            "nodes": nodes,
        }

    def _calculate_health_score(
        self,
        services: List[ServiceStatus],
        metrics: SystemMetrics,
        bridge: Dict[str, Any]
    ) -> float:
        """
        Calculate overall system health score (0-100).

        Args:
            services: List of service statuses
            metrics: System metrics
            bridge: Bridge status

        Returns:
            Health score percentage
        """
        score = 100.0
        deductions = 0

        # Service checks (30 points max)
        for service in services:
            if not service.running:
                deductions += 15

        # Resource checks (40 points max)
        if metrics.cpu_usage is not None and metrics.cpu_usage > 90:
            deductions += 15
        elif metrics.cpu_usage is not None and metrics.cpu_usage > 70:
            deductions += 5

        if metrics.cpu_temperature is not None and metrics.cpu_temperature > 80:
            deductions += 15
        elif metrics.cpu_temperature is not None and metrics.cpu_temperature > 70:
            deductions += 5

        if metrics.memory_available_mb is not None and metrics.memory_available_mb < 100:
            deductions += 10
        elif metrics.memory_available_mb is not None and metrics.memory_available_mb < 256:
            deductions += 5

        if metrics.disk_free_mb is not None and metrics.disk_free_mb < 500:
            deductions += 10
        elif metrics.disk_free_mb is not None and metrics.disk_free_mb < 1000:
            deductions += 5

        # Bridge checks (30 points max)
        if bridge.get("available"):
            if not bridge.get("running"):
                deductions += 15
            if not bridge.get("meshtastic_connected"):
                deductions += 7.5
            if not bridge.get("rns_connected"):
                deductions += 7.5

        return max(0, score - deductions)

    def format_text_dashboard(self) -> str:
        """
        Format status as text for CLI display.

        Returns:
            Formatted text string
        """
        status = self.get_full_status()
        lines = []

        # Header
        lines.append("=" * 60)
        lines.append("RNS-MESHTASTIC GATEWAY STATUS")
        lines.append("=" * 60)
        lines.append("")

        # Health score
        health = status["health_score"]
        if health >= 80:
            health_icon = "[OK]"
        elif health >= 50:
            health_icon = "[WARN]"
        else:
            health_icon = "[CRIT]"

        lines.append(f"Health Score: {health:.0f}% {health_icon}")
        lines.append("")

        # Platform
        if status["platform"]["board_model"]:
            lines.append(f"Platform: {status['platform']['board_model']}")
        lines.append("")

        # Services
        lines.append("Services:")
        for svc in status["services"]:
            icon = "[+]" if svc["running"] else "[-]"
            version = f" ({svc['version']})" if svc["version"] else ""
            lines.append(f"  {icon} {svc['name']}{version}")
        lines.append("")

        # System metrics
        sys = status["system"]
        lines.append("System:")
        if sys["cpu_usage"] is not None:
            lines.append(f"  CPU Usage: {sys['cpu_usage']:.1f}%")
        if sys["cpu_temperature"] is not None:
            lines.append(f"  CPU Temp: {sys['cpu_temperature']:.1f}C")
        if sys["memory_available_mb"] is not None:
            lines.append(f"  Memory: {sys['memory_available_mb']:.0f}MB available")
        if sys["disk_free_mb"] is not None:
            lines.append(f"  Disk: {sys['disk_free_mb']:.0f}MB free")
        if sys["load_average"]:
            lines.append(f"  Load: {sys['load_average'][0]:.2f}, {sys['load_average'][1]:.2f}, {sys['load_average'][2]:.2f}")
        lines.append("")

        # Bridge status
        bridge = status["bridge"]
        lines.append("Bridge:")
        if bridge.get("available"):
            icon = "[+]" if bridge.get("running") else "[-]"
            lines.append(f"  Status: {icon} {'Running' if bridge.get('running') else 'Stopped'}")
            if bridge.get("running"):
                lines.append(f"  Meshtastic: {'Connected' if bridge.get('meshtastic_connected') else 'Disconnected'}")
                lines.append(f"  RNS: {'Connected' if bridge.get('rns_connected') else 'Disconnected'}")
                lines.append(f"  Messages Bridged: {bridge.get('messages_bridged', 0)}")
        else:
            lines.append("  Not initialized")
        lines.append("")

        # Node summary
        nodes = status["nodes"]
        lines.append("Nodes:")
        lines.append(f"  Total: {nodes.get('total', 0)}")
        lines.append(f"  Online: {nodes.get('online', 0)}")
        lines.append(f"  Meshtastic: {nodes.get('meshtastic', 0)}")
        lines.append(f"  RNS: {nodes.get('rns', 0)}")
        lines.append(f"  With Position: {nodes.get('with_position', 0)}")
        lines.append("")

        lines.append("=" * 60)

        return "\n".join(lines)

    def interactive_dashboard(self) -> None:
        """
        Display interactive dashboard with refresh capability.
        """
        print("\nRNS-Meshtastic Gateway Dashboard")
        print("Press Ctrl+C to exit\n")

        try:
            while True:
                # Clear screen (ANSI escape)
                print("\033[H\033[J", end="")

                # Display dashboard
                print(self.format_text_dashboard())

                # Wait for next refresh
                time.sleep(5)

        except KeyboardInterrupt:
            print("\nDashboard closed.")
