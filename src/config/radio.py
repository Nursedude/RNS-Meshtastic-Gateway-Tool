"""
Radio configuration for RNS-Meshtastic Gateway Tool.

Provides configuration management for radio settings,
channel configuration, and modem parameters.
"""

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, List, Dict, Any
import json
from pathlib import Path


class ModemPreset(Enum):
    """Meshtastic modem presets."""

    LONG_FAST = "LONG_FAST"
    LONG_SLOW = "LONG_SLOW"
    LONG_MODERATE = "LONG_MODERATE"
    VERY_LONG_SLOW = "VERY_LONG_SLOW"
    MEDIUM_FAST = "MEDIUM_FAST"
    MEDIUM_SLOW = "MEDIUM_SLOW"
    SHORT_FAST = "SHORT_FAST"
    SHORT_SLOW = "SHORT_SLOW"
    SHORT_TURBO = "SHORT_TURBO"


class RegionCode(Enum):
    """LoRa frequency regions."""

    UNSET = "UNSET"
    US = "US"
    EU_433 = "EU_433"
    EU_868 = "EU_868"
    CN = "CN"
    JP = "JP"
    ANZ = "ANZ"
    KR = "KR"
    TW = "TW"
    RU = "RU"
    IN = "IN"
    NZ_865 = "NZ_865"
    TH = "TH"
    LORA_24 = "LORA_24"
    UA_433 = "UA_433"
    UA_868 = "UA_868"


# Region frequency ranges (MHz)
REGION_FREQUENCIES = {
    RegionCode.US: (902.0, 928.0),
    RegionCode.EU_868: (869.4, 869.65),
    RegionCode.EU_433: (433.05, 434.79),
    RegionCode.CN: (470.0, 510.0),
    RegionCode.JP: (920.0, 923.0),
    RegionCode.ANZ: (915.0, 928.0),
    RegionCode.KR: (920.0, 923.0),
    RegionCode.TW: (920.0, 925.0),
    RegionCode.RU: (864.0, 870.0),
    RegionCode.IN: (865.0, 867.0),
    RegionCode.LORA_24: (2400.0, 2483.5),
}


@dataclass
class ChannelSettings:
    """Channel configuration settings."""

    name: str = ""
    psk: bytes = field(default_factory=lambda: b"")  # Pre-shared key
    uplink_enabled: bool = True
    downlink_enabled: bool = True
    module_settings: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RadioConfig:
    """
    Radio transceiver configuration.

    Stores frequency, power, modem settings, and channel configuration.
    """

    # Region and frequency
    region: RegionCode = RegionCode.UNSET
    frequency_offset: float = 0.0  # MHz offset from default

    # Power settings
    tx_power: int = 20  # dBm (typically 0-30)
    tx_enabled: bool = True

    # Modem settings
    modem_preset: ModemPreset = ModemPreset.LONG_FAST
    use_preset: bool = True

    # Custom modem parameters (when use_preset=False)
    bandwidth: int = 250  # kHz
    spreading_factor: int = 11
    coding_rate: int = 5  # 4/5

    # Channel hop settings
    hop_limit: int = 3
    num_channels: int = 1
    channel_num: int = 0

    # Channel configurations
    channels: List[ChannelSettings] = field(default_factory=list)

    def __post_init__(self):
        """Initialize default channel if none provided."""
        if not self.channels:
            self.channels = [ChannelSettings(name="Primary")]

    def get_frequency_range(self) -> tuple:
        """Get frequency range for current region."""
        return REGION_FREQUENCIES.get(self.region, (0.0, 0.0))

    def validate(self) -> List[str]:
        """
        Validate radio configuration.

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        # Check TX power range
        if not 0 <= self.tx_power <= 30:
            errors.append(f"TX power {self.tx_power}dBm out of range (0-30)")

        # Check hop limit
        if not 0 <= self.hop_limit <= 7:
            errors.append(f"Hop limit {self.hop_limit} out of range (0-7)")

        # Check spreading factor
        if not 7 <= self.spreading_factor <= 12:
            errors.append(f"Spreading factor {self.spreading_factor} out of range (7-12)")

        # Check coding rate
        if not 5 <= self.coding_rate <= 8:
            errors.append(f"Coding rate {self.coding_rate} out of range (5-8)")

        # Check bandwidth
        valid_bandwidths = [31, 62, 125, 250, 500]
        if self.bandwidth not in valid_bandwidths:
            errors.append(f"Bandwidth {self.bandwidth}kHz not valid")

        return errors

    def calculate_airtime(self, payload_bytes: int) -> float:
        """
        Calculate approximate airtime for a packet.

        Args:
            payload_bytes: Payload size in bytes

        Returns:
            Airtime in milliseconds
        """
        # Simplified LoRa airtime calculation
        sf = self.spreading_factor
        bw = self.bandwidth * 1000  # Convert to Hz
        cr = self.coding_rate

        # Symbol time
        t_sym = (2 ** sf) / bw * 1000  # ms

        # Preamble symbols (8 default + 4.25)
        n_preamble = 8 + 4.25
        t_preamble = n_preamble * t_sym

        # Payload symbols (simplified)
        payload_symbols = 8 + max(
            ((8 * payload_bytes - 4 * sf + 44) / (4 * sf)) * cr,
            0
        )
        t_payload = payload_symbols * t_sym

        return t_preamble + t_payload

    def estimate_range_km(self) -> float:
        """
        Estimate approximate range in kilometers.

        Returns:
            Estimated range in km
        """
        # Very rough estimation based on settings
        base_range = {
            ModemPreset.LONG_FAST: 5.0,
            ModemPreset.LONG_SLOW: 10.0,
            ModemPreset.LONG_MODERATE: 7.5,
            ModemPreset.VERY_LONG_SLOW: 15.0,
            ModemPreset.MEDIUM_FAST: 3.0,
            ModemPreset.MEDIUM_SLOW: 5.0,
            ModemPreset.SHORT_FAST: 1.5,
            ModemPreset.SHORT_SLOW: 2.0,
            ModemPreset.SHORT_TURBO: 1.0,
        }.get(self.modem_preset, 5.0)

        # Adjust for TX power (rough +3dB = +40% range)
        power_factor = 1.0 + (self.tx_power - 20) * 0.04

        return base_range * power_factor

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = {
            "region": self.region.value,
            "frequency_offset": self.frequency_offset,
            "tx_power": self.tx_power,
            "tx_enabled": self.tx_enabled,
            "modem_preset": self.modem_preset.value,
            "use_preset": self.use_preset,
            "bandwidth": self.bandwidth,
            "spreading_factor": self.spreading_factor,
            "coding_rate": self.coding_rate,
            "hop_limit": self.hop_limit,
            "num_channels": self.num_channels,
            "channel_num": self.channel_num,
            "channels": [asdict(ch) for ch in self.channels],
        }
        # Convert bytes to hex for JSON serialization
        for ch in data["channels"]:
            if "psk" in ch and isinstance(ch["psk"], bytes):
                ch["psk"] = ch["psk"].hex()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RadioConfig":
        """Create from dictionary."""
        # Handle enums
        if "region" in data:
            data["region"] = RegionCode(data["region"])
        if "modem_preset" in data:
            data["modem_preset"] = ModemPreset(data["modem_preset"])

        # Handle channels
        if "channels" in data:
            channels = []
            for ch_data in data["channels"]:
                if "psk" in ch_data and isinstance(ch_data["psk"], str):
                    ch_data["psk"] = bytes.fromhex(ch_data["psk"])
                channels.append(ChannelSettings(**ch_data))
            data["channels"] = channels

        return cls(**data)

    def save(self, path: Path) -> bool:
        """Save configuration to file."""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w") as f:
                json.dump(self.to_dict(), f, indent=2)
            return True
        except Exception:
            return False

    @classmethod
    def load(cls, path: Path) -> "RadioConfig":
        """Load configuration from file."""
        if path.exists():
            try:
                with open(path) as f:
                    data = json.load(f)
                return cls.from_dict(data)
            except Exception:
                pass
        return cls()


def calculate_frequency_slot(name: str, num_channels: int = 104) -> int:
    """
    Calculate frequency slot using djb2 hash (matches Meshtastic firmware).

    Args:
        name: Channel name
        num_channels: Number of available slots

    Returns:
        Frequency slot index
    """
    # djb2 hash algorithm
    hash_value = 5381
    for char in name:
        hash_value = ((hash_value << 5) + hash_value) + ord(char)
        hash_value &= 0xFFFFFFFF  # Keep as 32-bit

    return hash_value % num_channels


def get_frequency_for_slot(slot: int, region: RegionCode) -> float:
    """
    Get frequency in MHz for a slot in a region.

    Args:
        slot: Frequency slot index
        region: Region code

    Returns:
        Frequency in MHz
    """
    freq_range = REGION_FREQUENCIES.get(region)
    if not freq_range:
        return 0.0

    start_freq, end_freq = freq_range
    bandwidth = end_freq - start_freq

    # Calculate channel spacing (simplified)
    channel_width = 0.5  # MHz per channel
    num_slots = int(bandwidth / channel_width)

    if num_slots <= 0:
        return start_freq

    slot_offset = (slot % num_slots) * channel_width
    return start_freq + slot_offset
