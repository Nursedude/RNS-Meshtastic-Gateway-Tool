"""
System utilities for RNS-Meshtastic Gateway Tool.

Provides OS detection, hardware identification, system commands,
and resource monitoring capabilities.

Security Note: All command execution functions validate inputs to prevent
command injection attacks.
"""

import ipaddress
import os
import platform
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List, Union

from .logger import get_logger


# Regex patterns for input validation
SERVICE_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9_.-]+$')
HOSTNAME_PATTERN = re.compile(r'^[a-zA-Z0-9.-]+$')


def _validate_service_name(service_name: str) -> bool:
    """Validate service name to prevent injection."""
    return bool(SERVICE_NAME_PATTERN.match(service_name)) and len(service_name) < 256


def _validate_host(host: str) -> bool:
    """Validate host address (IP or hostname)."""
    # Allow localhost variants
    if host in ('localhost', '127.0.0.1', '::1'):
        return True
    # Try as IP address
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        pass
    # Validate as hostname
    return bool(HOSTNAME_PATTERN.match(host)) and len(host) < 256


def get_system_info() -> Dict[str, Any]:
    """
    Gather comprehensive system information.

    Returns:
        Dictionary containing OS, architecture, Python version, and compatibility info
    """
    info = {
        "os_name": platform.system(),
        "os_version": platform.version(),
        "os_release": platform.release(),
        "architecture": platform.machine(),
        "python_version": sys.version,
        "python_version_info": sys.version_info[:3],
        "hostname": platform.node(),
        "is_raspberry_pi": is_raspberry_pi(),
        "board_model": get_board_model(),
        "is_linux_native_compatible": is_linux_native_compatible(),
        "architecture_bits": get_architecture_bits(),
    }
    return info


def check_root() -> bool:
    """
    Check if running with root/administrator privileges.

    Returns:
        True if running as root, False otherwise
    """
    if platform.system() == "Windows":
        try:
            import ctypes
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            return False
    else:
        return os.geteuid() == 0


def is_raspberry_pi() -> bool:
    """
    Detect if running on a Raspberry Pi.

    Returns:
        True if running on Raspberry Pi, False otherwise
    """
    # Check device tree model
    model_path = Path("/proc/device-tree/model")
    if model_path.exists():
        try:
            model = model_path.read_text().lower()
            if "raspberry pi" in model:
                return True
        except Exception:
            pass

    # Check cpuinfo as fallback
    cpuinfo_path = Path("/proc/cpuinfo")
    if cpuinfo_path.exists():
        try:
            cpuinfo = cpuinfo_path.read_text().lower()
            if "raspberry pi" in cpuinfo or "bcm" in cpuinfo:
                return True
        except Exception:
            pass

    return False


def get_board_model() -> Optional[str]:
    """
    Get the board model string for Raspberry Pi or similar SBCs.

    Returns:
        Board model string or None
    """
    model_path = Path("/proc/device-tree/model")
    if model_path.exists():
        try:
            return model_path.read_text().strip().rstrip("\x00")
        except Exception:
            pass
    return None


def get_architecture_bits() -> int:
    """
    Determine if the system is 32-bit or 64-bit.

    Returns:
        32 or 64
    """
    return 64 if sys.maxsize > 2**32 else 32


def is_linux_native_compatible() -> bool:
    """
    Check if the system supports native Linux binaries for Meshtastic.

    Returns:
        True if compatible architecture on Linux
    """
    if platform.system() != "Linux":
        return False

    machine = platform.machine().lower()
    compatible_archs = ["aarch64", "arm64", "armv7l", "armhf", "x86_64", "amd64"]
    return any(arch in machine for arch in compatible_archs)


def get_os_type() -> str:
    """
    Get the OS type for package installation.

    Returns:
        'arm64', 'armhf', 'x86_64', or 'unknown'
    """
    machine = platform.machine().lower()
    if machine in ("aarch64", "arm64"):
        return "arm64"
    elif machine in ("armv7l", "armhf"):
        return "armhf"
    elif machine in ("x86_64", "amd64"):
        return "x86_64"
    return "unknown"


def run_command(
    command: Union[str, List[str]],
    shell: bool = False,
    capture_output: bool = True,
    timeout: int = 30,
    suppress_errors: bool = False
) -> Tuple[int, str, str]:
    """
    Execute a system command with timeout and error handling.

    Security: Defaults to shell=False to prevent command injection.
    Use list format for commands when possible.

    Args:
        command: Command as list of strings (preferred) or string
        shell: Execute through shell (use with caution)
        capture_output: Capture stdout/stderr
        timeout: Timeout in seconds
        suppress_errors: Don't log errors

    Returns:
        Tuple of (return_code, stdout, stderr)
    """
    logger = get_logger()

    try:
        # If string provided and shell=False, try to split safely
        if isinstance(command, str) and not shell:
            try:
                command = shlex.split(command)
            except ValueError:
                # If shlex.split fails, log warning and return error
                if not suppress_errors:
                    logger.warning("Invalid command format")
                return -1, "", "Invalid command format"

        result = subprocess.run(
            command,
            shell=shell,
            capture_output=capture_output,
            text=True,
            timeout=timeout
        )
        return result.returncode, result.stdout or "", result.stderr or ""
    except subprocess.TimeoutExpired:
        if not suppress_errors:
            logger.warning(f"Command timed out after {timeout}s")
        return -1, "", f"Timeout after {timeout}s"
    except FileNotFoundError:
        if not suppress_errors:
            logger.warning("Command not found")
        return -1, "", "Command not found"
    except Exception as e:
        if not suppress_errors:
            logger.error(f"Command failed: {e}")
        return -1, "", str(e)


def run_command_safe(
    args: List[str],
    timeout: int = 30,
    suppress_errors: bool = False
) -> Tuple[int, str, str]:
    """
    Execute a system command safely without shell.

    This is the preferred method for running system commands.

    Args:
        args: Command as list of strings
        timeout: Timeout in seconds
        suppress_errors: Don't log errors

    Returns:
        Tuple of (return_code, stdout, stderr)
    """
    return run_command(args, shell=False, timeout=timeout, suppress_errors=suppress_errors)


def check_internet_connection(host: str = "8.8.8.8", timeout: int = 5) -> bool:
    """
    Check internet connectivity by pinging a host.

    Args:
        host: Host to ping (validated for safety)
        timeout: Timeout in seconds

    Returns:
        True if connection available
    """
    # Validate host to prevent command injection
    if not _validate_host(host):
        return False

    if platform.system() == "Windows":
        cmd = ["ping", "-n", "1", "-w", str(timeout * 1000), host]
    else:
        cmd = ["ping", "-c", "1", "-W", str(timeout), host]

    rc, _, _ = run_command_safe(cmd, suppress_errors=True)
    return rc == 0


def enable_service(service_name: str) -> bool:
    """
    Enable a systemd service.

    Args:
        service_name: Name of the service (validated for safety)

    Returns:
        True if successful
    """
    if not _validate_service_name(service_name):
        return False

    rc, _, _ = run_command_safe(["systemctl", "enable", service_name])
    return rc == 0


def restart_service(service_name: str) -> bool:
    """
    Restart a systemd service.

    Args:
        service_name: Name of the service (validated for safety)

    Returns:
        True if successful
    """
    if not _validate_service_name(service_name):
        return False

    rc, _, _ = run_command_safe(["systemctl", "restart", service_name])
    return rc == 0


def is_service_running(service_name: str) -> bool:
    """
    Check if a systemd service is running.

    Args:
        service_name: Name of the service (validated for safety)

    Returns:
        True if service is active
    """
    if not _validate_service_name(service_name):
        return False

    rc, stdout, _ = run_command_safe(
        ["systemctl", "is-active", service_name],
        suppress_errors=True
    )
    return rc == 0 and "active" in stdout.lower()


def get_available_memory() -> float:
    """
    Get available memory in MB.

    Returns:
        Available memory in MB, or -1 on error
    """
    try:
        import psutil
        return psutil.virtual_memory().available / (1024 * 1024)
    except ImportError:
        pass

    # Fallback to /proc/meminfo
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    kb = int(line.split()[1])
                    return kb / 1024
    except Exception:
        pass

    return -1


def get_disk_space(path: str = "/") -> Tuple[float, float, float]:
    """
    Get disk space information for a path.

    Args:
        path: Filesystem path to check

    Returns:
        Tuple of (total_mb, used_mb, free_mb)
    """
    # Validate path exists
    if not Path(path).exists():
        return -1, -1, -1

    try:
        import psutil
        usage = psutil.disk_usage(path)
        return (
            usage.total / (1024 * 1024),
            usage.used / (1024 * 1024),
            usage.free / (1024 * 1024)
        )
    except ImportError:
        pass

    # Fallback to os.statvfs
    try:
        stat = os.statvfs(path)
        total = stat.f_blocks * stat.f_frsize / (1024 * 1024)
        free = stat.f_bavail * stat.f_frsize / (1024 * 1024)
        used = total - free
        return total, used, free
    except Exception:
        pass

    return -1, -1, -1


def get_cpu_temperature() -> Optional[float]:
    """
    Get CPU temperature in Celsius.

    Returns:
        Temperature in Celsius or None if unavailable
    """
    # Try thermal zone (no command execution needed)
    thermal_path = Path("/sys/class/thermal/thermal_zone0/temp")
    if thermal_path.exists():
        try:
            temp = int(thermal_path.read_text().strip())
            return temp / 1000.0
        except Exception:
            pass

    # Try vcgencmd for Raspberry Pi (safe - no user input)
    if is_raspberry_pi():
        rc, stdout, _ = run_command_safe(
            ["vcgencmd", "measure_temp"],
            suppress_errors=True
        )
        if rc == 0 and "temp=" in stdout:
            try:
                temp_str = stdout.split("=")[1].replace("'C", "").strip()
                return float(temp_str)
            except Exception:
                pass

    return None


def get_cpu_usage() -> Optional[float]:
    """
    Get current CPU usage percentage.

    Returns:
        CPU usage percentage or None if unavailable
    """
    try:
        import psutil
        return psutil.cpu_percent(interval=0.1)
    except ImportError:
        pass

    # Fallback using /proc/stat (no command execution)
    try:
        with open("/proc/stat") as f:
            line = f.readline()
            fields = line.split()
            total = sum(int(x) for x in fields[1:8])
            idle = int(fields[4])
            return 100 * (1 - idle / total) if total > 0 else None
    except Exception:
        pass

    return None
