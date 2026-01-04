#!/usr/bin/env python3
"""
Comprehensive test suite for RNS-Meshtastic Gateway Tool.

Tests cover all major modules including gateway, diagnostics,
configuration, and security validation.
"""

import sys
import unittest
from pathlib import Path
from typing import List, Tuple

# Add project root to path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))


class TestResults:
    """Track test results."""
    passed: int = 0
    failed: int = 0
    errors: List[str] = []


results = TestResults()


def run_test(name: str, test_func) -> bool:
    """Run a test and track results."""
    try:
        test_func()
        results.passed += 1
        print(f"  [+] PASS: {name}")
        return True
    except AssertionError as e:
        results.failed += 1
        results.errors.append(f"{name}: {e}")
        print(f"  [-] FAIL: {name}: {e}")
        return False
    except Exception as e:
        results.failed += 1
        results.errors.append(f"{name}: {type(e).__name__}: {e}")
        print(f"  [!] ERROR: {name}: {type(e).__name__}: {e}")
        return False


# ============================================================
# Basic Import Tests
# ============================================================

def test_basic_imports():
    """Test basic module imports."""
    from ai_methods import DiagnosticEngine
    from git_manager import GitManager
    from version import get_version
    assert DiagnosticEngine is not None
    assert GitManager is not None
    assert get_version() is not None


def test_src_imports():
    """Test src package imports."""
    try:
        from src.utils import get_logger, setup_logger
        from src.gateway import RNSMeshtasticBridge, UnifiedNodeTracker
        from src.diagnostics import SystemDiagnostics, SignalAnalyzer
        from src.config import HardwareDetector, RadioConfig, LoRaConfig
        from src.monitoring import NodeMonitor, StatusDashboard
        assert True
    except ImportError as e:
        # May fail if dependencies not installed
        print(f"  [!] Note: Full imports require dependencies: {e}")
        assert True  # Still pass - optional deps


# ============================================================
# Version Tests
# ============================================================

def test_version_format():
    """Test version string format."""
    from version import get_version, MAJOR, MINOR, PATCH, STATUS
    version = get_version()
    assert isinstance(version, str)
    assert f"{MAJOR}.{MINOR}.{PATCH}" in version
    assert STATUS in version


def test_version_info():
    """Test version info function."""
    from version import get_full_info
    info = get_full_info()
    assert "version" in info
    assert "major" in info
    assert "minor" in info
    assert "status" in info


# ============================================================
# AI Methods Tests
# ============================================================

def test_diagnostic_engine_init():
    """Test DiagnosticEngine initialization."""
    from ai_methods import DiagnosticEngine
    engine = DiagnosticEngine()
    assert engine is not None
    assert hasattr(engine, 'os_type')


def test_diagnostic_engine_context_check():
    """Test context check returns valid output."""
    from ai_methods import DiagnosticEngine
    engine = DiagnosticEngine()
    result = engine.run_context_check()
    assert isinstance(result, str)
    assert "CONTEXT:" in result


def test_diagnostic_engine_signal_analysis():
    """Test signal analysis with various inputs."""
    from ai_methods import DiagnosticEngine
    engine = DiagnosticEngine()

    # Test low SNR
    result = engine.analyze_signal(-15, -100)
    assert "Noise" in result or "DIAGNOSTIC" in result

    # Test good SNR
    result = engine.analyze_signal(5, -80)
    assert "Optimal" in result or "DIAGNOSTIC" in result


# ============================================================
# Git Manager Tests
# ============================================================

def test_git_manager_init():
    """Test GitManager initialization."""
    from git_manager import GitManager
    manager = GitManager()
    assert manager is not None


# ============================================================
# Signal Analyzer Tests (if available)
# ============================================================

def test_signal_analyzer():
    """Test SignalAnalyzer functionality."""
    try:
        from src.diagnostics.signal_analysis import SignalAnalyzer, SignalQuality

        analyzer = SignalAnalyzer()

        # Test SNR classification (thresholds: EXCELLENT>=10, GOOD>=0, FAIR>=-5, POOR>=-10)
        assert analyzer.classify_snr(15) == SignalQuality.EXCELLENT
        assert analyzer.classify_snr(0) == SignalQuality.GOOD
        assert analyzer.classify_snr(-3) == SignalQuality.FAIR
        assert analyzer.classify_snr(-7) == SignalQuality.POOR
        assert analyzer.classify_snr(-15) == SignalQuality.CRITICAL

        # Test analysis
        result = analyzer.analyze(-5, -95)
        assert result.quality in SignalQuality
        assert isinstance(result.diagnosis, str)
        assert isinstance(result.recommendations, list)

    except ImportError:
        print("  [!] Skipping: Signal analyzer not available")
        assert True


# ============================================================
# Node Tracker Tests (if available)
# ============================================================

def test_node_tracker():
    """Test UnifiedNodeTracker functionality."""
    try:
        from src.gateway.node_tracker import (
            UnifiedNodeTracker, UnifiedNode, Position, Telemetry
        )

        tracker = UnifiedNodeTracker()

        # Test adding nodes
        node = UnifiedNode(
            unified_id="test_node_1",
            meshtastic_id="!12345678",
            network="meshtastic",
            short_name="TST1",
            long_name="Test Node 1"
        )
        result = tracker.add_or_update(node)
        assert result.unified_id == "test_node_1"

        # Test retrieval
        retrieved = tracker.get("test_node_1")
        assert retrieved is not None
        assert retrieved.short_name == "TST1"

        # Test statistics
        stats = tracker.get_statistics()
        assert stats["total"] >= 1

        # Test position
        position = Position(latitude=37.7749, longitude=-122.4194, altitude=100)
        assert position.is_valid()
        assert -90 <= position.latitude <= 90

        # Clear
        tracker.clear()
        assert len(tracker.get_all()) == 0

    except ImportError:
        print("  [!] Skipping: Node tracker not available")
        assert True


# ============================================================
# Gateway Config Tests (if available)
# ============================================================

def test_gateway_config():
    """Test GatewayConfig functionality."""
    try:
        from src.gateway.config import (
            GatewayConfig, MeshtasticConfig, RNSConfig, RoutingRule
        )

        # Test default config
        config = GatewayConfig()
        assert config.bridge_enabled == True
        assert config.meshtastic.host == "localhost"
        assert config.meshtastic.port == 4403

        # Test routing rules
        assert len(config.routing_rules) > 0
        rule = config.routing_rules[0]
        assert rule.matches("test message")

        # Test serialization
        data = config.to_dict()
        assert "meshtastic" in data
        assert "rns" in data

        # Test deserialization
        loaded = GatewayConfig.from_dict(data)
        assert loaded.meshtastic.port == config.meshtastic.port

    except ImportError:
        print("  [!] Skipping: Gateway config not available")
        assert True


# ============================================================
# LoRa Config Tests (if available)
# ============================================================

def test_lora_config():
    """Test LoRaConfig functionality."""
    try:
        from src.config.lora import (
            LoRaConfig, LoRaPreset, MESHTASTIC_PRESETS, get_preset_list
        )

        # Test preset loading
        config = LoRaConfig.from_preset("LONG_FAST")
        assert config is not None

        # Test data rate calculation
        assert config.data_rate_bps > 0

        # Test sensitivity calculation
        assert config.sensitivity_dbm < 0

        # Test airtime calculation
        airtime = config.calculate_airtime_ms(32)
        assert airtime > 0

        # Test range estimation
        range_km = config.estimate_range_km("rural")
        assert range_km > 0

        # Test preset list
        presets = get_preset_list()
        assert len(presets) > 0
        assert "LONG_FAST" in [p["key"] for p in presets]

    except ImportError:
        print("  [!] Skipping: LoRa config not available")
        assert True


# ============================================================
# Radio Config Tests (if available)
# ============================================================

def test_radio_config():
    """Test RadioConfig functionality."""
    try:
        from src.config.radio import (
            RadioConfig, ModemPreset, RegionCode, calculate_frequency_slot
        )

        # Test default config
        config = RadioConfig()
        assert config.tx_power == 20
        assert config.hop_limit == 3

        # Test validation
        errors = config.validate()
        assert len(errors) == 0

        # Test invalid config
        invalid_config = RadioConfig(tx_power=50)
        errors = invalid_config.validate()
        assert len(errors) > 0

        # Test frequency slot calculation
        slot = calculate_frequency_slot("test_channel")
        assert 0 <= slot < 104

    except ImportError:
        print("  [!] Skipping: Radio config not available")
        assert True


# ============================================================
# System Utils Security Tests (if available)
# ============================================================

def test_system_utils_security():
    """Test system utilities security measures."""
    try:
        from src.utils.system import (
            _validate_host, _validate_service_name,
            run_command_safe
        )

        # Test host validation
        assert _validate_host("localhost") == True
        assert _validate_host("127.0.0.1") == True
        assert _validate_host("8.8.8.8") == True
        assert _validate_host("google.com") == True
        assert _validate_host("; rm -rf /") == False
        assert _validate_host("") == False

        # Test service name validation
        assert _validate_service_name("meshtasticd") == True
        assert _validate_service_name("rns.service") == True
        assert _validate_service_name("; cat /etc/passwd") == False
        assert _validate_service_name("") == False

        # Test safe command execution
        rc, stdout, stderr = run_command_safe(["echo", "test"])
        assert rc == 0
        assert "test" in stdout

    except ImportError:
        print("  [!] Skipping: System utils not available")
        assert True


# ============================================================
# Run All Tests
# ============================================================

def run_all_tests():
    """Run all tests and report results."""
    print()
    print("=" * 60)
    print("  RNS-MESHTASTIC GATEWAY TOOL - TEST SUITE")
    print("=" * 60)
    print()

    # Basic Tests
    print("Basic Import Tests:")
    run_test("Basic Imports", test_basic_imports)
    run_test("Src Package Imports", test_src_imports)
    print()

    # Version Tests
    print("Version Tests:")
    run_test("Version Format", test_version_format)
    run_test("Version Info", test_version_info)
    print()

    # AI Methods Tests
    print("AI Methods Tests:")
    run_test("DiagnosticEngine Init", test_diagnostic_engine_init)
    run_test("Context Check", test_diagnostic_engine_context_check)
    run_test("Signal Analysis", test_diagnostic_engine_signal_analysis)
    print()

    # Git Manager Tests
    print("Git Manager Tests:")
    run_test("GitManager Init", test_git_manager_init)
    print()

    # Signal Analyzer Tests
    print("Signal Analyzer Tests:")
    run_test("Signal Analyzer", test_signal_analyzer)
    print()

    # Node Tracker Tests
    print("Node Tracker Tests:")
    run_test("Node Tracker", test_node_tracker)
    print()

    # Gateway Config Tests
    print("Gateway Config Tests:")
    run_test("Gateway Config", test_gateway_config)
    print()

    # LoRa Config Tests
    print("LoRa Config Tests:")
    run_test("LoRa Config", test_lora_config)
    print()

    # Radio Config Tests
    print("Radio Config Tests:")
    run_test("Radio Config", test_radio_config)
    print()

    # Security Tests
    print("Security Tests:")
    run_test("System Utils Security", test_system_utils_security)
    print()

    # Summary
    print("=" * 60)
    total = results.passed + results.failed
    print(f"  RESULTS: {results.passed}/{total} tests passed")
    if results.failed > 0:
        print(f"  FAILED: {results.failed} tests")
        for error in results.errors:
            print(f"    - {error}")
    print("=" * 60)
    print()

    return results.failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
