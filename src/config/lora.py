"""
LoRa-specific configuration for RNS-Meshtastic Gateway Tool.

Provides LoRa modulation parameters, presets, and
physical layer configuration.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any, List
import math


class LoRaBandwidth(Enum):
    """LoRa bandwidth options in kHz."""

    BW_7_8 = 7.8
    BW_10_4 = 10.4
    BW_15_6 = 15.6
    BW_20_8 = 20.8
    BW_31_25 = 31.25
    BW_41_7 = 41.7
    BW_62_5 = 62.5
    BW_125 = 125.0
    BW_250 = 250.0
    BW_500 = 500.0


class SpreadingFactor(Enum):
    """LoRa spreading factors."""

    SF7 = 7
    SF8 = 8
    SF9 = 9
    SF10 = 10
    SF11 = 11
    SF12 = 12


class CodingRate(Enum):
    """LoRa coding rates (4/x)."""

    CR_4_5 = 5
    CR_4_6 = 6
    CR_4_7 = 7
    CR_4_8 = 8


@dataclass
class LoRaPreset:
    """
    Predefined LoRa configuration preset.

    Matches Meshtastic firmware presets for compatibility.
    """

    name: str
    bandwidth: LoRaBandwidth
    spreading_factor: SpreadingFactor
    coding_rate: CodingRate
    description: str = ""

    @property
    def data_rate_bps(self) -> float:
        """Calculate theoretical data rate in bits per second."""
        sf = self.spreading_factor.value
        bw = self.bandwidth.value * 1000  # Convert to Hz
        cr = self.coding_rate.value

        # LoRa data rate formula
        return sf * (4 / cr) * (bw / (2 ** sf))

    @property
    def symbol_time_ms(self) -> float:
        """Calculate symbol time in milliseconds."""
        sf = self.spreading_factor.value
        bw = self.bandwidth.value * 1000  # Hz
        return (2 ** sf) / bw * 1000


# Standard Meshtastic presets
MESHTASTIC_PRESETS = {
    "LONG_FAST": LoRaPreset(
        name="Long Range - Fast",
        bandwidth=LoRaBandwidth.BW_250,
        spreading_factor=SpreadingFactor.SF11,
        coding_rate=CodingRate.CR_4_5,
        description="Balance of range and speed for general use"
    ),
    "LONG_SLOW": LoRaPreset(
        name="Long Range - Slow",
        bandwidth=LoRaBandwidth.BW_125,
        spreading_factor=SpreadingFactor.SF12,
        coding_rate=CodingRate.CR_4_8,
        description="Maximum range, minimum speed"
    ),
    "LONG_MODERATE": LoRaPreset(
        name="Long Range - Moderate",
        bandwidth=LoRaBandwidth.BW_125,
        spreading_factor=SpreadingFactor.SF11,
        coding_rate=CodingRate.CR_4_8,
        description="Good range with moderate speed"
    ),
    "VERY_LONG_SLOW": LoRaPreset(
        name="Very Long Range - Slow",
        bandwidth=LoRaBandwidth.BW_62_5,
        spreading_factor=SpreadingFactor.SF12,
        coding_rate=CodingRate.CR_4_8,
        description="Extreme range, very slow"
    ),
    "MEDIUM_FAST": LoRaPreset(
        name="Medium Range - Fast",
        bandwidth=LoRaBandwidth.BW_250,
        spreading_factor=SpreadingFactor.SF10,
        coding_rate=CodingRate.CR_4_5,
        description="Medium range with good speed"
    ),
    "MEDIUM_SLOW": LoRaPreset(
        name="Medium Range - Slow",
        bandwidth=LoRaBandwidth.BW_250,
        spreading_factor=SpreadingFactor.SF11,
        coding_rate=CodingRate.CR_4_6,
        description="Medium range, more reliable"
    ),
    "SHORT_FAST": LoRaPreset(
        name="Short Range - Fast",
        bandwidth=LoRaBandwidth.BW_250,
        spreading_factor=SpreadingFactor.SF9,
        coding_rate=CodingRate.CR_4_5,
        description="Short range, high throughput"
    ),
    "SHORT_SLOW": LoRaPreset(
        name="Short Range - Slow",
        bandwidth=LoRaBandwidth.BW_250,
        spreading_factor=SpreadingFactor.SF10,
        coding_rate=CodingRate.CR_4_5,
        description="Short range, more reliable"
    ),
    "SHORT_TURBO": LoRaPreset(
        name="Short Range - Turbo",
        bandwidth=LoRaBandwidth.BW_500,
        spreading_factor=SpreadingFactor.SF7,
        coding_rate=CodingRate.CR_4_5,
        description="Maximum speed, minimum range"
    ),
}


@dataclass
class LoRaConfig:
    """
    Complete LoRa physical layer configuration.

    Provides modulation settings, timing calculations,
    and link budget parameters.
    """

    # Modulation parameters
    frequency_mhz: float = 915.0
    bandwidth: LoRaBandwidth = LoRaBandwidth.BW_250
    spreading_factor: SpreadingFactor = SpreadingFactor.SF11
    coding_rate: CodingRate = CodingRate.CR_4_5

    # Power settings
    tx_power_dbm: int = 20
    antenna_gain_dbi: float = 0.0

    # Timing
    preamble_length: int = 8
    sync_word: int = 0x12  # LoRa sync word

    # Features
    implicit_header: bool = False
    crc_enabled: bool = True
    low_data_rate_optimize: bool = False

    def __post_init__(self):
        """Auto-enable LDRO if needed."""
        # LDRO should be enabled when symbol time > 16ms
        if self.symbol_time_ms > 16.0:
            self.low_data_rate_optimize = True

    @property
    def symbol_time_ms(self) -> float:
        """Calculate symbol time in milliseconds."""
        sf = self.spreading_factor.value
        bw = self.bandwidth.value * 1000  # Hz
        return (2 ** sf) / bw * 1000

    @property
    def data_rate_bps(self) -> float:
        """Calculate theoretical data rate in bits per second."""
        sf = self.spreading_factor.value
        bw = self.bandwidth.value * 1000  # Hz
        cr = self.coding_rate.value
        return sf * (4 / cr) * (bw / (2 ** sf))

    @property
    def sensitivity_dbm(self) -> float:
        """Estimate receiver sensitivity in dBm."""
        # Approximate sensitivity based on SF and BW
        # Higher SF = better sensitivity, Higher BW = worse sensitivity
        base_sensitivity = -174  # Thermal noise floor dBm/Hz
        noise_figure = 6  # Typical LoRa NF in dB

        bw_hz = self.bandwidth.value * 1000
        sf = self.spreading_factor.value

        # SNR requirement per SF (approximate)
        snr_required = {7: -7.5, 8: -10, 9: -12.5, 10: -15, 11: -17.5, 12: -20}

        snr = snr_required.get(sf, -15)

        # Sensitivity = -174 + 10*log10(BW) + NF + SNR_required
        sensitivity = base_sensitivity + 10 * math.log10(bw_hz) + noise_figure + snr

        return round(sensitivity, 1)

    @property
    def eirp_dbm(self) -> float:
        """Calculate Effective Isotropic Radiated Power."""
        return self.tx_power_dbm + self.antenna_gain_dbi

    @property
    def link_budget_db(self) -> float:
        """Calculate maximum link budget."""
        return self.eirp_dbm - self.sensitivity_dbm

    def calculate_airtime_ms(self, payload_bytes: int) -> float:
        """
        Calculate packet airtime in milliseconds.

        Args:
            payload_bytes: Payload size in bytes

        Returns:
            Airtime in milliseconds
        """
        sf = self.spreading_factor.value
        bw = self.bandwidth.value * 1000  # Hz
        cr = self.coding_rate.value

        # Symbol time
        t_sym = (2 ** sf) / bw * 1000  # ms

        # Preamble time
        n_preamble = self.preamble_length + 4.25
        t_preamble = n_preamble * t_sym

        # Header and payload symbols
        pl = payload_bytes
        ih = 1 if self.implicit_header else 0
        crc = 1 if self.crc_enabled else 0
        de = 1 if self.low_data_rate_optimize else 0

        # Payload symbol calculation (from LoRa spec)
        numerator = 8 * pl - 4 * sf + 28 + 16 * crc - 20 * ih
        denominator = 4 * (sf - 2 * de)

        n_payload = 8 + max(math.ceil(numerator / denominator) * cr, 0)
        t_payload = n_payload * t_sym

        return t_preamble + t_payload

    def estimate_range_km(self, environment: str = "rural") -> float:
        """
        Estimate maximum range in kilometers.

        Args:
            environment: "urban", "suburban", or "rural"

        Returns:
            Estimated range in km
        """
        # Path loss exponents for different environments
        path_loss_exp = {"urban": 3.5, "suburban": 3.0, "rural": 2.5}
        n = path_loss_exp.get(environment, 3.0)

        # Free space path loss at 1km reference
        freq_hz = self.frequency_mhz * 1e6
        c = 3e8  # Speed of light

        # Path loss at 1km
        pl_1km = 20 * math.log10(4 * math.pi * 1000 * freq_hz / c)

        # Maximum allowed path loss
        max_pl = self.link_budget_db

        # Calculate range
        # PL = PL_1km + 10*n*log10(d)
        # d = 10^((PL - PL_1km) / (10*n))

        range_km = 10 ** ((max_pl - pl_1km) / (10 * n))

        return round(range_km, 2)

    def get_duty_cycle_limit(self, region: str = "US") -> float:
        """
        Get regulatory duty cycle limit as percentage.

        Args:
            region: Region code

        Returns:
            Maximum duty cycle percentage
        """
        limits = {
            "US": 100.0,  # No duty cycle limit in US
            "EU_868": 1.0,  # 1% in EU 868
            "EU_433": 10.0,  # 10% in EU 433
        }
        return limits.get(region, 100.0)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "frequency_mhz": self.frequency_mhz,
            "bandwidth": self.bandwidth.value,
            "spreading_factor": self.spreading_factor.value,
            "coding_rate": self.coding_rate.value,
            "tx_power_dbm": self.tx_power_dbm,
            "antenna_gain_dbi": self.antenna_gain_dbi,
            "preamble_length": self.preamble_length,
            "sync_word": self.sync_word,
            "implicit_header": self.implicit_header,
            "crc_enabled": self.crc_enabled,
            "low_data_rate_optimize": self.low_data_rate_optimize,
        }

    @classmethod
    def from_preset(cls, preset_name: str) -> "LoRaConfig":
        """
        Create configuration from a preset name.

        Args:
            preset_name: Preset name (e.g., "LONG_FAST")

        Returns:
            LoRaConfig instance
        """
        preset = MESHTASTIC_PRESETS.get(preset_name)
        if not preset:
            preset = MESHTASTIC_PRESETS["LONG_FAST"]

        return cls(
            bandwidth=preset.bandwidth,
            spreading_factor=preset.spreading_factor,
            coding_rate=preset.coding_rate,
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LoRaConfig":
        """Create from dictionary."""
        if "bandwidth" in data:
            data["bandwidth"] = LoRaBandwidth(data["bandwidth"])
        if "spreading_factor" in data:
            data["spreading_factor"] = SpreadingFactor(data["spreading_factor"])
        if "coding_rate" in data:
            data["coding_rate"] = CodingRate(data["coding_rate"])
        return cls(**data)


def get_preset_list() -> List[Dict[str, Any]]:
    """
    Get list of available presets with details.

    Returns:
        List of preset information dictionaries
    """
    presets = []
    for key, preset in MESHTASTIC_PRESETS.items():
        presets.append({
            "key": key,
            "name": preset.name,
            "description": preset.description,
            "bandwidth_khz": preset.bandwidth.value,
            "spreading_factor": preset.spreading_factor.value,
            "coding_rate": f"4/{preset.coding_rate.value}",
            "data_rate_bps": round(preset.data_rate_bps, 1),
            "symbol_time_ms": round(preset.symbol_time_ms, 2),
        })
    return presets
