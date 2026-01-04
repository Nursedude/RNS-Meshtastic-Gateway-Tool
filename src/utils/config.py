"""
Configuration management utilities for RNS-Meshtastic Gateway Tool.

Provides persistent configuration storage, loading, and management
with JSON-based configuration files.
"""

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, Dict, Any, TypeVar, Type

from .logger import get_logger

T = TypeVar("T")

# Default configuration directory
DEFAULT_CONFIG_DIR = Path.home() / ".config" / "rns-meshtastic-gateway"


@dataclass
class AppConfig:
    """Application-wide configuration settings."""

    # General settings
    debug: bool = False
    log_file: Optional[str] = None

    # UI preferences
    interface: str = "cli"  # cli, tui, web, gtk
    auto_launch: bool = False
    theme: str = "dark"

    # Network defaults
    meshtastic_host: str = "localhost"
    meshtastic_port: int = 4403
    rns_config_dir: Optional[str] = None

    # Update settings
    auto_update_check: bool = True
    update_channel: str = "stable"  # stable, beta, alpha


class ConfigManager:
    """
    Manages application configuration with file persistence.

    Provides loading, saving, and default configuration handling
    with support for nested configuration structures.
    """

    def __init__(
        self,
        config_dir: Optional[Path] = None,
        config_file: str = "config.json"
    ):
        """
        Initialize the configuration manager.

        Args:
            config_dir: Configuration directory path
            config_file: Configuration file name
        """
        self.config_dir = config_dir or DEFAULT_CONFIG_DIR
        self.config_file = self.config_dir / config_file
        self._config: Dict[str, Any] = {}
        self._ensure_config_dir()

    def _ensure_config_dir(self) -> None:
        """Create configuration directory if it doesn't exist."""
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def load(self) -> Dict[str, Any]:
        """
        Load configuration from file.

        Returns:
            Configuration dictionary
        """
        logger = get_logger()

        if self.config_file.exists():
            try:
                with open(self.config_file) as f:
                    self._config = json.load(f)
                logger.debug(f"Loaded configuration from {self.config_file}")
            except json.JSONDecodeError as e:
                logger.warning(f"Invalid config file, using defaults: {e}")
                self._config = {}
            except Exception as e:
                logger.error(f"Error loading config: {e}")
                self._config = {}
        else:
            logger.debug("No config file found, using defaults")
            self._config = {}

        return self._config

    def save(self, config: Optional[Dict[str, Any]] = None) -> bool:
        """
        Save configuration to file.

        Args:
            config: Configuration dictionary (uses internal if not provided)

        Returns:
            True if save successful
        """
        logger = get_logger()

        if config is not None:
            self._config = config

        try:
            self._ensure_config_dir()
            with open(self.config_file, "w") as f:
                json.dump(self._config, f, indent=2)
            logger.debug(f"Saved configuration to {self.config_file}")
            return True
        except Exception as e:
            logger.error(f"Error saving config: {e}")
            return False

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value.

        Args:
            key: Configuration key (supports dot notation)
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        if not self._config:
            self.load()

        # Support dot notation for nested keys
        keys = key.split(".")
        value = self._config
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value

    def set(self, key: str, value: Any) -> None:
        """
        Set a configuration value.

        Args:
            key: Configuration key (supports dot notation)
            value: Value to set
        """
        if not self._config:
            self.load()

        # Support dot notation for nested keys
        keys = key.split(".")
        target = self._config
        for k in keys[:-1]:
            if k not in target or not isinstance(target[k], dict):
                target[k] = {}
            target = target[k]
        target[keys[-1]] = value

    def get_app_config(self) -> AppConfig:
        """
        Get the application configuration as a dataclass.

        Returns:
            AppConfig instance
        """
        if not self._config:
            self.load()

        app_data = self._config.get("app", {})
        return AppConfig(**{
            k: v for k, v in app_data.items()
            if k in AppConfig.__dataclass_fields__
        })

    def save_app_config(self, config: AppConfig) -> bool:
        """
        Save application configuration.

        Args:
            config: AppConfig instance

        Returns:
            True if save successful
        """
        self._config["app"] = asdict(config)
        return self.save()


# Module-level convenience functions
_default_manager: Optional[ConfigManager] = None


def get_config_manager() -> ConfigManager:
    """Get or create the default configuration manager."""
    global _default_manager
    if _default_manager is None:
        _default_manager = ConfigManager()
    return _default_manager


def load_config() -> Dict[str, Any]:
    """Load configuration using the default manager."""
    return get_config_manager().load()


def save_config(config: Dict[str, Any]) -> bool:
    """Save configuration using the default manager."""
    return get_config_manager().save(config)


def get_config_value(key: str, default: Any = None) -> Any:
    """Get a configuration value using the default manager."""
    return get_config_manager().get(key, default)


def set_config_value(key: str, value: Any) -> None:
    """Set a configuration value using the default manager."""
    get_config_manager().set(key, value)
