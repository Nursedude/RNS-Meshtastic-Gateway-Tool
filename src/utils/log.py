"""
Centralized logging configuration for the RNS-Meshtastic Gateway.

Call setup_logging() once at application startup (launcher.py or web_dashboard.py).
Individual modules obtain their own loggers via logging.getLogger(__name__) or
a descriptive name.

Includes an optional JSON structured formatter (MeshForge pattern) for
machine-parseable log aggregation.
"""
import json
import logging
import logging.handlers
import time

_configured = False


class JsonFormatter(logging.Formatter):
    """Structured JSON log formatter for machine parsing.

    Each log record becomes a single JSON line::

        {"ts":"2025-01-15T12:00:00Z","level":"INFO","logger":"gateway","msg":"..."}
    """

    def format(self, record):
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0]:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def setup_logging(level=logging.INFO, log_file=None, console_level=None,
                  structured=False):
    """Configure project-wide logging.  Safe to call multiple times.

    Uses handler-level filtering (adopted from MeshForge) so the console
    can be quieter while the file handler captures full detail.

    Args:
        level: Root logger level (default INFO).
        log_file: Optional path to a rotating log file.
        console_level: Override console handler level independently
                       (e.g. WARNING for TUI mode).  Defaults to *level*.
        structured: Use JSON structured logging format (default False).
    """
    global _configured
    if _configured:
        return
    _configured = True

    if structured:
        formatter = JsonFormatter()
    else:
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
