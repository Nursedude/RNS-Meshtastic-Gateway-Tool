"""
RNS-Meshtastic Gateway Tool - MeshForge Integration

A comprehensive network operations suite bridging Meshtastic and Reticulum (RNS)
mesh networks with unified node tracking and AI-augmented diagnostics.

This package integrates MeshForge capabilities for:
- RNS-Meshtastic bidirectional gateway bridging
- Unified node tracking across heterogeneous networks
- System diagnostics and RF signal analysis
- Hardware configuration management
- Real-time monitoring and telemetry

Version: 2.0.0-Alpha
License: GPL-3.0
"""

__version__ = "2.0.0-Alpha"
__author__ = "nursedude"
__license__ = "GPL-3.0"

from .utils import get_logger, setup_logger
from .gateway import RNSMeshtasticBridge, UnifiedNodeTracker, GatewayConfig
from .diagnostics import SystemDiagnostics, SignalAnalyzer
from .config import HardwareConfig, RadioConfig, LoRaConfig

__all__ = [
    "get_logger",
    "setup_logger",
    "RNSMeshtasticBridge",
    "UnifiedNodeTracker",
    "GatewayConfig",
    "SystemDiagnostics",
    "SignalAnalyzer",
    "HardwareConfig",
    "RadioConfig",
    "LoRaConfig",
]
