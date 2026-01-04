"""
RF Signal Analysis for RNS-Meshtastic Gateway Tool.

Provides signal quality analysis, noise floor detection,
and AI-augmented diagnostics for mesh network optimization.
"""

import time
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple
from enum import Enum


class SignalQuality(Enum):
    """Signal quality classification."""

    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    CRITICAL = "critical"


@dataclass
class SignalReading:
    """Single signal measurement reading."""

    snr: float  # Signal-to-Noise Ratio in dB
    rssi: float  # Received Signal Strength Indicator in dBm
    timestamp: float = field(default_factory=time.time)
    node_id: Optional[str] = None
    channel: int = 0
    frequency: Optional[float] = None  # MHz


@dataclass
class SignalAnalysisResult:
    """Result of signal analysis."""

    quality: SignalQuality
    snr: float
    rssi: float
    diagnosis: str
    recommendations: List[str]
    details: Dict[str, Any] = field(default_factory=dict)


class SignalAnalyzer:
    """
    RF signal analyzer with AI-augmented diagnostics.

    Provides signal quality assessment, trend analysis,
    and optimization recommendations for mesh networks.
    """

    # SNR thresholds (dB)
    SNR_EXCELLENT = 10.0
    SNR_GOOD = 0.0
    SNR_FAIR = -5.0
    SNR_POOR = -10.0
    # Below -10 is CRITICAL

    # RSSI thresholds (dBm)
    RSSI_EXCELLENT = -90.0
    RSSI_GOOD = -100.0
    RSSI_FAIR = -110.0
    RSSI_POOR = -120.0
    # Below -120 is CRITICAL

    def __init__(self):
        """Initialize the signal analyzer."""
        self._history: List[SignalReading] = []
        self._max_history = 1000

    def add_reading(self, reading: SignalReading) -> None:
        """
        Add a signal reading to history.

        Args:
            reading: Signal reading to add
        """
        self._history.append(reading)

        # Trim history if needed
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

    def classify_snr(self, snr: float) -> SignalQuality:
        """
        Classify SNR into quality level.

        Args:
            snr: Signal-to-Noise Ratio in dB

        Returns:
            SignalQuality classification
        """
        if snr >= self.SNR_EXCELLENT:
            return SignalQuality.EXCELLENT
        elif snr >= self.SNR_GOOD:
            return SignalQuality.GOOD
        elif snr >= self.SNR_FAIR:
            return SignalQuality.FAIR
        elif snr >= self.SNR_POOR:
            return SignalQuality.POOR
        else:
            return SignalQuality.CRITICAL

    def classify_rssi(self, rssi: float) -> SignalQuality:
        """
        Classify RSSI into quality level.

        Args:
            rssi: RSSI in dBm

        Returns:
            SignalQuality classification
        """
        if rssi >= self.RSSI_EXCELLENT:
            return SignalQuality.EXCELLENT
        elif rssi >= self.RSSI_GOOD:
            return SignalQuality.GOOD
        elif rssi >= self.RSSI_FAIR:
            return SignalQuality.FAIR
        elif rssi >= self.RSSI_POOR:
            return SignalQuality.POOR
        else:
            return SignalQuality.CRITICAL

    def analyze(self, snr: float, rssi: float) -> SignalAnalysisResult:
        """
        Analyze signal quality and provide recommendations.

        Args:
            snr: Signal-to-Noise Ratio in dB
            rssi: RSSI in dBm

        Returns:
            SignalAnalysisResult with diagnosis and recommendations
        """
        snr_quality = self.classify_snr(snr)
        rssi_quality = self.classify_rssi(rssi)

        # Overall quality is the worse of the two
        quality_order = [
            SignalQuality.EXCELLENT,
            SignalQuality.GOOD,
            SignalQuality.FAIR,
            SignalQuality.POOR,
            SignalQuality.CRITICAL
        ]

        snr_idx = quality_order.index(snr_quality)
        rssi_idx = quality_order.index(rssi_quality)
        overall_quality = quality_order[max(snr_idx, rssi_idx)]

        # Generate diagnosis
        diagnosis = self._generate_diagnosis(snr, rssi, snr_quality, rssi_quality)

        # Generate recommendations
        recommendations = self._generate_recommendations(
            snr, rssi, snr_quality, rssi_quality
        )

        return SignalAnalysisResult(
            quality=overall_quality,
            snr=snr,
            rssi=rssi,
            diagnosis=diagnosis,
            recommendations=recommendations,
            details={
                "snr_quality": snr_quality.value,
                "rssi_quality": rssi_quality.value,
                "snr_db": snr,
                "rssi_dbm": rssi,
            }
        )

    def _generate_diagnosis(
        self,
        snr: float,
        rssi: float,
        snr_quality: SignalQuality,
        rssi_quality: SignalQuality
    ) -> str:
        """Generate diagnostic message based on signal parameters."""
        parts = []

        # SNR diagnosis
        if snr_quality == SignalQuality.CRITICAL:
            parts.append(f"CRITICAL: High noise floor detected (SNR: {snr:.1f}dB)")
        elif snr_quality == SignalQuality.POOR:
            parts.append(f"WARNING: Elevated noise levels (SNR: {snr:.1f}dB)")
        elif snr_quality == SignalQuality.EXCELLENT:
            parts.append(f"Excellent SNR: {snr:.1f}dB")
        else:
            parts.append(f"SNR: {snr:.1f}dB ({snr_quality.value})")

        # RSSI diagnosis
        if rssi_quality == SignalQuality.CRITICAL:
            parts.append(f"CRITICAL: Very weak signal (RSSI: {rssi:.1f}dBm)")
        elif rssi_quality == SignalQuality.POOR:
            parts.append(f"WARNING: Weak signal (RSSI: {rssi:.1f}dBm)")
        elif rssi_quality == SignalQuality.EXCELLENT:
            parts.append(f"Strong signal (RSSI: {rssi:.1f}dBm)")
        else:
            parts.append(f"RSSI: {rssi:.1f}dBm ({rssi_quality.value})")

        return " | ".join(parts)

    def _generate_recommendations(
        self,
        snr: float,
        rssi: float,
        snr_quality: SignalQuality,
        rssi_quality: SignalQuality
    ) -> List[str]:
        """Generate optimization recommendations."""
        recommendations = []

        # SNR-based recommendations
        if snr_quality in (SignalQuality.CRITICAL, SignalQuality.POOR):
            recommendations.extend([
                "Check antenna connections and cabling for damage",
                "Move antenna away from sources of RF interference",
                "Consider using a bandpass filter to reduce noise",
                "Check for nearby electronics causing interference",
            ])
        elif snr_quality == SignalQuality.FAIR:
            recommendations.append("SNR is marginal - monitor for degradation")

        # RSSI-based recommendations
        if rssi_quality in (SignalQuality.CRITICAL, SignalQuality.POOR):
            recommendations.extend([
                "Increase antenna height or improve line of sight",
                "Consider using a higher-gain antenna",
                "Reduce distance between nodes or add repeaters",
                "Check for obstacles blocking signal path",
            ])
        elif rssi_quality == SignalQuality.FAIR:
            recommendations.append("Signal strength is marginal - consider antenna improvements")

        # Combined recommendations
        if snr_quality == SignalQuality.CRITICAL and rssi_quality == SignalQuality.CRITICAL:
            recommendations.insert(0, "URGENT: Both noise and signal strength are critical")

        if not recommendations:
            recommendations.append("Signal quality is optimal - no changes recommended")

        return recommendations

    def analyze_reading(self, reading: SignalReading) -> SignalAnalysisResult:
        """
        Analyze a signal reading.

        Args:
            reading: SignalReading to analyze

        Returns:
            SignalAnalysisResult
        """
        self.add_reading(reading)
        return self.analyze(reading.snr, reading.rssi)

    def get_statistics(
        self,
        node_id: Optional[str] = None,
        time_window: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Get signal statistics from history.

        Args:
            node_id: Filter by node ID (optional)
            time_window: Only include readings from last N seconds (optional)

        Returns:
            Dictionary with min/max/avg statistics
        """
        readings = self._history

        # Filter by node
        if node_id:
            readings = [r for r in readings if r.node_id == node_id]

        # Filter by time
        if time_window:
            cutoff = time.time() - time_window
            readings = [r for r in readings if r.timestamp >= cutoff]

        if not readings:
            return {"count": 0}

        snr_values = [r.snr for r in readings]
        rssi_values = [r.rssi for r in readings]

        return {
            "count": len(readings),
            "snr": {
                "min": min(snr_values),
                "max": max(snr_values),
                "avg": sum(snr_values) / len(snr_values),
            },
            "rssi": {
                "min": min(rssi_values),
                "max": max(rssi_values),
                "avg": sum(rssi_values) / len(rssi_values),
            },
            "time_range": {
                "start": min(r.timestamp for r in readings),
                "end": max(r.timestamp for r in readings),
            }
        }

    def detect_anomalies(
        self,
        threshold_std: float = 2.0
    ) -> List[Tuple[SignalReading, str]]:
        """
        Detect anomalous signal readings.

        Args:
            threshold_std: Number of standard deviations for anomaly detection

        Returns:
            List of (reading, reason) tuples for anomalous readings
        """
        if len(self._history) < 10:
            return []

        snr_values = [r.snr for r in self._history]
        rssi_values = [r.rssi for r in self._history]

        # Calculate statistics
        snr_mean = sum(snr_values) / len(snr_values)
        rssi_mean = sum(rssi_values) / len(rssi_values)

        snr_std = (sum((x - snr_mean) ** 2 for x in snr_values) / len(snr_values)) ** 0.5
        rssi_std = (sum((x - rssi_mean) ** 2 for x in rssi_values) / len(rssi_values)) ** 0.5

        anomalies = []

        for reading in self._history[-50:]:  # Check last 50 readings
            reasons = []

            if snr_std > 0 and abs(reading.snr - snr_mean) > threshold_std * snr_std:
                reasons.append(f"SNR deviation: {reading.snr:.1f}dB (mean: {snr_mean:.1f}dB)")

            if rssi_std > 0 and abs(reading.rssi - rssi_mean) > threshold_std * rssi_std:
                reasons.append(f"RSSI deviation: {reading.rssi:.1f}dBm (mean: {rssi_mean:.1f}dBm)")

            if reasons:
                anomalies.append((reading, "; ".join(reasons)))

        return anomalies

    def estimate_link_budget(
        self,
        tx_power_dbm: float = 20.0,
        antenna_gain_db: float = 0.0,
        rssi: float = -100.0
    ) -> Dict[str, float]:
        """
        Estimate link budget based on measurements.

        Args:
            tx_power_dbm: Transmit power in dBm
            antenna_gain_db: Combined antenna gain in dB
            rssi: Measured RSSI in dBm

        Returns:
            Link budget parameters
        """
        # EIRP = TX Power + Antenna Gain
        eirp = tx_power_dbm + antenna_gain_db

        # Path Loss = EIRP - RSSI
        path_loss = eirp - rssi

        # Fade margin (assuming -120 dBm sensitivity)
        sensitivity = -120.0
        fade_margin = rssi - sensitivity

        return {
            "eirp_dbm": eirp,
            "path_loss_db": path_loss,
            "fade_margin_db": fade_margin,
            "link_viable": fade_margin > 10.0,
        }

    def clear_history(self) -> None:
        """Clear signal reading history."""
        self._history.clear()
