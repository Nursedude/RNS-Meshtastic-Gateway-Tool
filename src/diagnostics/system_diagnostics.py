"""
System diagnostics for RNS-Meshtastic Gateway Tool.

Provides comprehensive health assessment including network connectivity,
hardware status, service monitoring, and system resource checks.
"""

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple

from ..utils.system import (
    run_command,
    is_raspberry_pi,
    get_board_model,
    check_internet_connection,
    is_service_running,
    get_cpu_temperature,
    get_cpu_usage,
    get_available_memory,
    get_disk_space,
)
from ..utils.logger import get_logger


@dataclass
class DiagnosticResult:
    """Result of a single diagnostic check."""

    name: str
    passed: bool
    message: str
    details: Optional[Dict[str, Any]] = None


class SystemDiagnostics:
    """
    Comprehensive system diagnostics for mesh gateway infrastructure.

    Provides checks for network connectivity, hardware interfaces,
    service status, and system resources.
    """

    def __init__(self):
        """Initialize the diagnostics engine."""
        self.logger = get_logger()
        self._results: List[DiagnosticResult] = []

    def _add_result(
        self,
        name: str,
        passed: bool,
        message: str,
        details: Optional[Dict[str, Any]] = None
    ) -> DiagnosticResult:
        """Add a diagnostic result."""
        result = DiagnosticResult(name, passed, message, details)
        self._results.append(result)
        return result

    def clear_results(self) -> None:
        """Clear all diagnostic results."""
        self._results.clear()

    def get_results(self) -> List[DiagnosticResult]:
        """Get all diagnostic results."""
        return self._results.copy()

    def get_health_percentage(self) -> float:
        """Calculate overall health percentage."""
        if not self._results:
            return 0.0
        passed = sum(1 for r in self._results if r.passed)
        return (passed / len(self._results)) * 100

    # Network Diagnostics

    def check_localhost_ping(self) -> DiagnosticResult:
        """Check localhost connectivity."""
        rc, _, _ = run_command("ping -c 1 -W 2 127.0.0.1", suppress_errors=True)
        passed = rc == 0
        return self._add_result(
            "Localhost Ping",
            passed,
            "Localhost responding" if passed else "Localhost not responding"
        )

    def check_gateway_ping(self) -> DiagnosticResult:
        """Check default gateway connectivity."""
        # Get default gateway
        rc, stdout, _ = run_command(
            "ip route | grep default | awk '{print $3}' | head -1",
            suppress_errors=True
        )

        if rc != 0 or not stdout.strip():
            return self._add_result(
                "Gateway Ping",
                False,
                "No default gateway found"
            )

        gateway = stdout.strip()
        rc, _, _ = run_command(f"ping -c 1 -W 2 {gateway}", suppress_errors=True)
        passed = rc == 0

        return self._add_result(
            "Gateway Ping",
            passed,
            f"Gateway {gateway} responding" if passed else f"Gateway {gateway} not responding",
            {"gateway": gateway}
        )

    def check_internet_connectivity(self) -> DiagnosticResult:
        """Check internet connectivity."""
        passed = check_internet_connection()
        return self._add_result(
            "Internet Connectivity",
            passed,
            "Internet accessible" if passed else "No internet connection"
        )

    def check_dns_resolution(self) -> DiagnosticResult:
        """Check DNS resolution."""
        rc, stdout, _ = run_command(
            "host -W 5 github.com",
            suppress_errors=True
        )
        passed = rc == 0 and "has address" in stdout

        return self._add_result(
            "DNS Resolution",
            passed,
            "DNS working" if passed else "DNS resolution failed"
        )

    def check_meshtastic_api(self, host: str = "localhost", port: int = 4403) -> DiagnosticResult:
        """
        Check Meshtastic TCP API connectivity.

        Args:
            host: Meshtasticd host
            port: Meshtasticd port
        """
        import socket

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex((host, port))
            sock.close()

            passed = result == 0
            return self._add_result(
                "Meshtastic API",
                passed,
                f"Connected to {host}:{port}" if passed else f"Cannot connect to {host}:{port}",
                {"host": host, "port": port}
            )
        except Exception as e:
            return self._add_result(
                "Meshtastic API",
                False,
                f"Connection error: {e}",
                {"host": host, "port": port, "error": str(e)}
            )

    # Hardware Diagnostics

    def check_spi_interface(self) -> DiagnosticResult:
        """Check if SPI interface is enabled."""
        spi_dev = Path("/dev/spidev0.0")
        passed = spi_dev.exists()

        return self._add_result(
            "SPI Interface",
            passed,
            "SPI enabled" if passed else "SPI not enabled or not available"
        )

    def check_i2c_interface(self) -> DiagnosticResult:
        """Check if I2C interface is enabled."""
        i2c_dev = Path("/dev/i2c-1")
        passed = i2c_dev.exists()

        return self._add_result(
            "I2C Interface",
            passed,
            "I2C enabled" if passed else "I2C not enabled or not available"
        )

    def check_gpio_access(self) -> DiagnosticResult:
        """Check GPIO access permissions."""
        gpio_path = Path("/sys/class/gpio")
        passed = gpio_path.exists() and os.access(gpio_path, os.R_OK)

        return self._add_result(
            "GPIO Access",
            passed,
            "GPIO accessible" if passed else "GPIO not accessible"
        )

    def check_serial_ports(self) -> DiagnosticResult:
        """Check available serial ports."""
        rc, stdout, _ = run_command(
            "ls /dev/ttyUSB* /dev/ttyACM* 2>/dev/null || true",
            suppress_errors=True
        )

        ports = [p.strip() for p in stdout.split() if p.strip()]
        passed = len(ports) > 0

        return self._add_result(
            "Serial Ports",
            passed,
            f"Found {len(ports)} serial ports" if passed else "No serial ports found",
            {"ports": ports}
        )

    def scan_i2c_devices(self) -> DiagnosticResult:
        """Scan for I2C devices."""
        rc, stdout, _ = run_command("i2cdetect -y 1 2>/dev/null", suppress_errors=True)

        if rc != 0:
            return self._add_result(
                "I2C Devices",
                False,
                "Cannot scan I2C (i2cdetect not available or permission denied)"
            )

        # Parse i2cdetect output for addresses
        devices = []
        for line in stdout.split("\n"):
            parts = line.split(":")[1:] if ":" in line else []
            for part in parts:
                for addr in part.split():
                    if addr != "--" and addr != "UU":
                        devices.append(addr)

        passed = len(devices) > 0
        return self._add_result(
            "I2C Devices",
            passed,
            f"Found {len(devices)} I2C devices" if passed else "No I2C devices found",
            {"devices": devices}
        )

    def check_lora_hardware(self) -> DiagnosticResult:
        """Check for LoRa hardware presence."""
        # Check for common LoRa devices
        indicators = [
            Path("/dev/spidev0.0").exists(),
            Path("/sys/class/gpio").exists(),
        ]

        # Check for known USB LoRa devices
        rc, stdout, _ = run_command("lsusb 2>/dev/null", suppress_errors=True)
        lora_usb_ids = ["1a86:55d4", "303a:1001", "10c4:ea60"]  # Common LoRa USB VID:PIDs
        for vid_pid in lora_usb_ids:
            if vid_pid in stdout:
                indicators.append(True)
                break

        passed = any(indicators)
        return self._add_result(
            "LoRa Hardware",
            passed,
            "LoRa hardware indicators found" if passed else "No LoRa hardware detected"
        )

    # Service Diagnostics

    def check_meshtasticd_service(self) -> DiagnosticResult:
        """Check meshtasticd service status."""
        running = is_service_running("meshtasticd")

        return self._add_result(
            "Meshtasticd Service",
            running,
            "Service running" if running else "Service not running"
        )

    def check_meshtasticd_installed(self) -> DiagnosticResult:
        """Check if meshtasticd is installed."""
        rc, stdout, _ = run_command("which meshtasticd", suppress_errors=True)
        passed = rc == 0 and stdout.strip()

        version = None
        if passed:
            rc, ver_out, _ = run_command("meshtasticd --version 2>/dev/null", suppress_errors=True)
            if rc == 0:
                version = ver_out.strip()

        return self._add_result(
            "Meshtasticd Installed",
            passed,
            f"Installed: {version}" if version else ("Installed" if passed else "Not installed"),
            {"version": version} if version else None
        )

    def check_config_files(self) -> DiagnosticResult:
        """Check for meshtasticd configuration files."""
        config_paths = [
            Path("/etc/meshtasticd/config.yaml"),
            Path.home() / ".config" / "meshtasticd" / "config.yaml",
        ]

        found = [str(p) for p in config_paths if p.exists()]
        passed = len(found) > 0

        return self._add_result(
            "Config Files",
            passed,
            f"Found {len(found)} config files" if passed else "No config files found",
            {"files": found}
        )

    # System Resource Diagnostics

    def check_cpu_temperature(self) -> DiagnosticResult:
        """Check CPU temperature."""
        temp = get_cpu_temperature()

        if temp is None:
            return self._add_result(
                "CPU Temperature",
                True,
                "Temperature sensor not available"
            )

        # Warning thresholds for Raspberry Pi
        passed = temp < 80.0
        message = f"{temp:.1f}C"
        if temp >= 80.0:
            message += " (CRITICAL)"
        elif temp >= 70.0:
            message += " (HIGH)"

        return self._add_result(
            "CPU Temperature",
            passed,
            message,
            {"temperature": temp}
        )

    def check_memory_usage(self) -> DiagnosticResult:
        """Check available memory."""
        available_mb = get_available_memory()

        if available_mb < 0:
            return self._add_result(
                "Memory",
                True,
                "Cannot determine memory status"
            )

        # Warning if less than 100MB available
        passed = available_mb >= 100
        message = f"{available_mb:.0f} MB available"

        return self._add_result(
            "Memory",
            passed,
            message,
            {"available_mb": available_mb}
        )

    def check_disk_space(self) -> DiagnosticResult:
        """Check disk space."""
        total, used, free = get_disk_space("/")

        if free < 0:
            return self._add_result(
                "Disk Space",
                True,
                "Cannot determine disk status"
            )

        # Warning if less than 500MB free
        passed = free >= 500
        usage_pct = (used / total) * 100 if total > 0 else 0
        message = f"{free:.0f} MB free ({usage_pct:.1f}% used)"

        return self._add_result(
            "Disk Space",
            passed,
            message,
            {"total_mb": total, "used_mb": used, "free_mb": free}
        )

    def check_cpu_usage(self) -> DiagnosticResult:
        """Check CPU usage."""
        usage = get_cpu_usage()

        if usage is None:
            return self._add_result(
                "CPU Usage",
                True,
                "Cannot determine CPU usage"
            )

        passed = usage < 90.0
        message = f"{usage:.1f}%"

        return self._add_result(
            "CPU Usage",
            passed,
            message,
            {"usage": usage}
        )

    def check_throttling(self) -> DiagnosticResult:
        """Check for Raspberry Pi throttling."""
        if not is_raspberry_pi():
            return self._add_result(
                "Throttling",
                True,
                "N/A (not Raspberry Pi)"
            )

        rc, stdout, _ = run_command("vcgencmd get_throttled 2>/dev/null", suppress_errors=True)

        if rc != 0:
            return self._add_result(
                "Throttling",
                True,
                "Cannot check throttling status"
            )

        throttled = stdout.strip()
        passed = throttled == "throttled=0x0"

        if passed:
            message = "No throttling detected"
        else:
            message = f"Throttling active: {throttled}"

        return self._add_result(
            "Throttling",
            passed,
            message,
            {"raw": throttled}
        )

    # Comprehensive Diagnostics

    def run_network_diagnostics(self) -> List[DiagnosticResult]:
        """Run all network-related diagnostics."""
        self.clear_results()
        self.check_localhost_ping()
        self.check_gateway_ping()
        self.check_internet_connectivity()
        self.check_dns_resolution()
        self.check_meshtastic_api()
        return self.get_results()

    def run_hardware_diagnostics(self) -> List[DiagnosticResult]:
        """Run all hardware-related diagnostics."""
        self.clear_results()
        self.check_spi_interface()
        self.check_i2c_interface()
        self.check_gpio_access()
        self.check_serial_ports()
        self.check_lora_hardware()
        return self.get_results()

    def run_service_diagnostics(self) -> List[DiagnosticResult]:
        """Run all service-related diagnostics."""
        self.clear_results()
        self.check_meshtasticd_installed()
        self.check_meshtasticd_service()
        self.check_config_files()
        return self.get_results()

    def run_system_diagnostics(self) -> List[DiagnosticResult]:
        """Run all system resource diagnostics."""
        self.clear_results()
        self.check_cpu_temperature()
        self.check_cpu_usage()
        self.check_memory_usage()
        self.check_disk_space()
        self.check_throttling()
        return self.get_results()

    def run_full_diagnostics(self) -> Dict[str, Any]:
        """
        Run all diagnostics and return comprehensive report.

        Returns:
            Dictionary with all diagnostic results and summary
        """
        self.clear_results()

        # Run all checks
        self.check_localhost_ping()
        self.check_gateway_ping()
        self.check_internet_connectivity()
        self.check_dns_resolution()
        self.check_meshtastic_api()

        self.check_spi_interface()
        self.check_i2c_interface()
        self.check_gpio_access()
        self.check_serial_ports()
        self.check_lora_hardware()

        self.check_meshtasticd_installed()
        self.check_meshtasticd_service()
        self.check_config_files()

        self.check_cpu_temperature()
        self.check_cpu_usage()
        self.check_memory_usage()
        self.check_disk_space()
        self.check_throttling()

        results = self.get_results()
        passed = sum(1 for r in results if r.passed)
        failed = len(results) - passed

        return {
            "results": results,
            "summary": {
                "total": len(results),
                "passed": passed,
                "failed": failed,
                "health_percentage": self.get_health_percentage(),
            },
            "timestamp": time.time(),
            "board_model": get_board_model(),
            "is_raspberry_pi": is_raspberry_pi(),
        }
