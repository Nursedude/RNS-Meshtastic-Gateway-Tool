"""
Centralized logging configuration for the RNS-Meshtastic Gateway.

Call setup_logging() once at application startup (launcher.py or web_dashboard.py).
Individual modules obtain their own loggers via logging.getLogger(__name__) or
a descriptive name.
"""
import logging
import logging.handlers

_configured = False


def setup_logging(level=logging.INFO, log_file=None, console_level=None):
    """Configure project-wide logging.  Safe to call multiple times.

    Uses handler-level filtering (adopted from MeshForge) so the console
    can be quieter while the file handler captures full detail.

    Args:
        level: Root logger level (default INFO).
        log_file: Optional path to a rotating log file.
        console_level: Override console handler level independently
                       (e.g. WARNING for TUI mode).  Defaults to *level*.
    """
    global _configured
    if _configured:
        return
    _configured = True

    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"
    formatter = logging.Formatter(fmt, datefmt=datefmt)

    root = logging.getLogger()
    root.setLevel(level)

    # Console handler — level can be raised independently of root
    console = logging.StreamHandler()
    console.setLevel(console_level or level)
    console.setFormatter(formatter)
    root.addHandler(console)

    # Optional rotating file handler — always captures at root level
    if log_file:
        file_handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=1_000_000, backupCount=3,
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
