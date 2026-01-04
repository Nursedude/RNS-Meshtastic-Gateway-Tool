"""
Utility modules for RNS-Meshtastic Gateway Tool.

Provides system utilities, logging, configuration management,
and CLI helpers.
"""

from .logger import setup_logger, get_logger, log, log_command, log_exception
from .system import (
    get_system_info,
    check_root,
    is_raspberry_pi,
    get_board_model,
    is_linux_native_compatible,
    run_command,
    check_internet_connection,
    enable_service,
    restart_service,
    is_service_running,
    get_available_memory,
    get_disk_space,
)
from .config import ConfigManager, load_config, save_config

__all__ = [
    "setup_logger",
    "get_logger",
    "log",
    "log_command",
    "log_exception",
    "get_system_info",
    "check_root",
    "is_raspberry_pi",
    "get_board_model",
    "is_linux_native_compatible",
    "run_command",
    "check_internet_connection",
    "enable_service",
    "restart_service",
    "is_service_running",
    "get_available_memory",
    "get_disk_space",
    "ConfigManager",
    "load_config",
    "save_config",
]
