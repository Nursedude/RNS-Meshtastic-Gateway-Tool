"""
Gateway configuration management for RNS-Meshtastic Bridge.

Provides persistent configuration for bridge settings, routing rules,
and network-specific parameters.
"""

import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, List, Dict, Any

# Default configuration directory
DEFAULT_CONFIG_DIR = Path.home() / ".config" / "rns-meshtastic-gateway"


@dataclass
class MeshtasticConfig:
    """Meshtastic network connection configuration."""

    host: str = "localhost"
    port: int = 4403
    channel: int = 0
    use_mqtt: bool = False
    mqtt_host: Optional[str] = None
    mqtt_topic: Optional[str] = None


@dataclass
class RNSConfig:
    """Reticulum Network Stack configuration."""

    config_dir: Optional[str] = None
    identity_name: str = "gateway"
    announce_interval: int = 300  # seconds
    lxmf_propagation: bool = True


@dataclass
class RoutingRule:
    """Message routing rule between networks."""

    name: str
    direction: str  # "meshtastic_to_rns", "rns_to_meshtastic", "bidirectional"
    pattern: str = ".*"  # Regex pattern to match messages
    priority: int = 10
    enabled: bool = True
    transform: Optional[str] = None  # Optional message transformation

    def matches(self, message: str) -> bool:
        """Check if a message matches this rule's pattern."""
        try:
            return bool(re.match(self.pattern, message))
        except re.error:
            return False


@dataclass
class TelemetryConfig:
    """Telemetry sharing configuration."""

    share_position: bool = True
    share_battery: bool = True
    share_environment: bool = True
    position_precision: int = 6  # Decimal places for lat/lon
    update_interval: int = 300  # seconds


@dataclass
class DiagnosticsConfig:
    """Diagnostics and AI analysis configuration."""

    enable_ai_analysis: bool = True
    snr_threshold: float = -10.0
    rssi_threshold: float = -120.0
    anomaly_detection: bool = True
    log_telemetry: bool = True


@dataclass
class GatewayConfig:
    """
    Main gateway configuration container.

    Aggregates all sub-configurations for the RNS-Meshtastic bridge.
    """

    meshtastic: MeshtasticConfig = field(default_factory=MeshtasticConfig)
    rns: RNSConfig = field(default_factory=RNSConfig)
    telemetry: TelemetryConfig = field(default_factory=TelemetryConfig)
    diagnostics: DiagnosticsConfig = field(default_factory=DiagnosticsConfig)
    routing_rules: List[RoutingRule] = field(default_factory=list)

    # Bridge behavior
    bridge_enabled: bool = True
    auto_start: bool = False
    retry_on_disconnect: bool = True
    max_retries: int = 5
    retry_delay: int = 30  # seconds

    def __post_init__(self):
        """Initialize with default routing rules if none provided."""
        if not self.routing_rules:
            self.routing_rules = self._default_routing_rules()

    @staticmethod
    def _default_routing_rules() -> List[RoutingRule]:
        """Generate default routing rules."""
        return [
            RoutingRule(
                name="broadcast_to_rns",
                direction="meshtastic_to_rns",
                pattern=".*",
                priority=10,
                enabled=True
            ),
            RoutingRule(
                name="broadcast_to_meshtastic",
                direction="rns_to_meshtastic",
                pattern=".*",
                priority=10,
                enabled=True
            ),
            RoutingRule(
                name="direct_bidirectional",
                direction="bidirectional",
                pattern="^!.*",  # Direct messages starting with !
                priority=5,
                enabled=True
            ),
        ]

    def add_rule(self, rule: RoutingRule) -> None:
        """Add a routing rule, sorted by priority."""
        self.routing_rules.append(rule)
        self.routing_rules.sort(key=lambda r: r.priority)

    def remove_rule(self, name: str) -> bool:
        """Remove a routing rule by name."""
        original_len = len(self.routing_rules)
        self.routing_rules = [r for r in self.routing_rules if r.name != name]
        return len(self.routing_rules) < original_len

    def get_matching_rules(
        self,
        message: str,
        direction: str
    ) -> List[RoutingRule]:
        """Get all enabled rules matching a message and direction."""
        matching = []
        for rule in self.routing_rules:
            if not rule.enabled:
                continue
            if rule.direction not in (direction, "bidirectional"):
                continue
            if rule.matches(message):
                matching.append(rule)
        return matching

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        data = {
            "meshtastic": asdict(self.meshtastic),
            "rns": asdict(self.rns),
            "telemetry": asdict(self.telemetry),
            "diagnostics": asdict(self.diagnostics),
            "routing_rules": [asdict(r) for r in self.routing_rules],
            "bridge_enabled": self.bridge_enabled,
            "auto_start": self.auto_start,
            "retry_on_disconnect": self.retry_on_disconnect,
            "max_retries": self.max_retries,
            "retry_delay": self.retry_delay,
        }
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GatewayConfig":
        """Create configuration from dictionary."""
        config = cls()

        if "meshtastic" in data:
            config.meshtastic = MeshtasticConfig(**data["meshtastic"])
        if "rns" in data:
            config.rns = RNSConfig(**data["rns"])
        if "telemetry" in data:
            config.telemetry = TelemetryConfig(**data["telemetry"])
        if "diagnostics" in data:
            config.diagnostics = DiagnosticsConfig(**data["diagnostics"])
        if "routing_rules" in data:
            config.routing_rules = [
                RoutingRule(**r) for r in data["routing_rules"]
            ]

        config.bridge_enabled = data.get("bridge_enabled", True)
        config.auto_start = data.get("auto_start", False)
        config.retry_on_disconnect = data.get("retry_on_disconnect", True)
        config.max_retries = data.get("max_retries", 5)
        config.retry_delay = data.get("retry_delay", 30)

        return config

    def save(self, config_file: Optional[Path] = None) -> bool:
        """
        Save configuration to file.

        Args:
            config_file: Path to config file

        Returns:
            True if successful
        """
        if config_file is None:
            config_file = DEFAULT_CONFIG_DIR / "gateway.json"

        try:
            config_file.parent.mkdir(parents=True, exist_ok=True)
            with open(config_file, "w") as f:
                json.dump(self.to_dict(), f, indent=2)
            return True
        except Exception:
            return False

    @classmethod
    def load(cls, config_file: Optional[Path] = None) -> "GatewayConfig":
        """
        Load configuration from file.

        Args:
            config_file: Path to config file

        Returns:
            GatewayConfig instance
        """
        if config_file is None:
            config_file = DEFAULT_CONFIG_DIR / "gateway.json"

        if config_file.exists():
            try:
                with open(config_file) as f:
                    data = json.load(f)
                return cls.from_dict(data)
            except Exception:
                pass

        return cls()
