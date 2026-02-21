"""
Centralized logging configuration for the RNS-Meshtastic Gateway.

Call setup_logging() once at application startup (launcher.py or web_dashboard.py).
Individual modules obtain their own loggers via logging.getLogger(__name__) or
a descriptive name.
"""
import logging
import logging.handlers

_configured = False


def setup_logging(level=logging.INFO, log_file=None):
    """Configure project-wide logging.  Safe to call multiple times.

    Args:
        level: Logging level (default INFO).
        log_file: Optional path to a rotating log file.
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

    # Console handler — preserves existing stdout behaviour
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)

    # Optional rotating file handler
    if log_file:
        file_handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=1_000_000, backupCount=3,
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
