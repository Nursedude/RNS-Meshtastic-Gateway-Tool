"""
Logging utilities for RNS-Meshtastic Gateway Tool.

Provides consistent logging across all modules with file and console output,
debug mode support, and specialized logging for command execution.
"""

import logging
import os
import sys
import traceback
from pathlib import Path
from typing import Optional

# Global logger instance
_logger: Optional[logging.Logger] = None


def setup_logger(
    debug: bool = False,
    log_file: Optional[str] = None,
    name: str = "rns-meshtastic-gateway"
) -> logging.Logger:
    """
    Initialize and configure the application logger.

    Args:
        debug: Enable debug-level logging
        log_file: Custom log file path (default: /var/log/rns-gateway.log)
        name: Logger name

    Returns:
        Configured logger instance
    """
    global _logger

    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG if debug else logging.INFO)

    # Clear existing handlers
    logger.handlers.clear()

    # Console handler with simple format
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG if debug else logging.INFO)
    console_format = logging.Formatter("%(levelname)s: %(message)s")
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)

    # File handler with detailed format
    if log_file is None:
        log_file = "/var/log/rns-gateway.log"

    try:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        file_format = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        file_handler.setFormatter(file_format)
        logger.addHandler(file_handler)
    except PermissionError:
        # Fall back to user home directory
        home_log = Path.home() / ".rns-gateway.log"
        try:
            file_handler = logging.FileHandler(home_log)
            file_handler.setLevel(logging.DEBUG)
            file_format = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            file_handler.setFormatter(file_format)
            logger.addHandler(file_handler)
            logger.debug(f"Using fallback log location: {home_log}")
        except Exception as e:
            logger.warning(f"Could not create log file: {e}")

    _logger = logger
    return logger


def get_logger() -> logging.Logger:
    """
    Get the global logger instance, initializing if necessary.

    Returns:
        Logger instance
    """
    global _logger
    if _logger is None:
        _logger = setup_logger()
    return _logger


def log(message: str, level: str = "info") -> None:
    """
    Log a message at the specified level.

    Args:
        message: Message to log
        level: Log level (debug, info, warning, error, critical)
    """
    logger = get_logger()
    level_map = {
        "debug": logger.debug,
        "info": logger.info,
        "warning": logger.warning,
        "warn": logger.warning,
        "error": logger.error,
        "critical": logger.critical,
    }
    log_func = level_map.get(level.lower(), logger.info)
    log_func(message)


def log_command(command: str, result: "subprocess.CompletedProcess") -> None:
    """
    Log command execution with return code and output.

    Args:
        command: The command that was executed
        result: subprocess.CompletedProcess result
    """
    logger = get_logger()

    if result.returncode == 0:
        logger.debug(f"Command succeeded: {command}")
        if result.stdout:
            logger.debug(f"stdout: {result.stdout}")
    else:
        logger.warning(f"Command failed (rc={result.returncode}): {command}")
        if result.stderr:
            logger.warning(f"stderr: {result.stderr}")


def log_exception(exception: Exception, context: Optional[str] = None) -> None:
    """
    Log an exception with stack trace and optional context.

    Args:
        exception: The exception to log
        context: Optional context description
    """
    logger = get_logger()

    if context:
        logger.error(f"Exception in {context}: {type(exception).__name__}: {exception}")
    else:
        logger.error(f"Exception: {type(exception).__name__}: {exception}")

    logger.debug(f"Stack trace:\n{traceback.format_exc()}")
