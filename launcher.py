#!/usr/bin/env python3
"""
RNS-Meshtastic Gateway Tool - Main Launcher

A comprehensive network operations suite bridging Meshtastic and Reticulum (RNS)
mesh networks with unified node tracking and AI-augmented diagnostics.

Usage:
    python launcher.py [options]

Options:
    --debug         Enable debug logging
    --daemon        Run bridge in background
    --status        Show quick status and exit
    --version       Show version and exit
"""

import sys
import argparse
from typing import Optional

# Local imports
from version import get_version
from ai_methods import DiagnosticEngine
from git_manager import GitManager

# Try to import integrated modules
try:
    from src.gateway import RNSMeshtasticBridge, UnifiedNodeTracker, GatewayConfig
    from src.diagnostics import SystemDiagnostics, SignalAnalyzer
    from src.config import HardwareDetector, RadioConfig, LoRaConfig
    from src.monitoring import NodeMonitor, StatusDashboard
    from src.utils import setup_logger, get_logger, get_system_info
    FULL_INTEGRATION = True
except ImportError:
    FULL_INTEGRATION = False


class SupervisorNOC:
    """
    RNS-Meshtastic Gateway Supervisor Network Operations Center.

    Provides a unified interface for managing gateway operations,
    diagnostics, and configuration.
    """

    def __init__(self, debug: bool = False):
        """
        Initialize the Supervisor NOC.

        Args:
            debug: Enable debug logging
        """
        self.debug = debug
        self.ai = DiagnosticEngine()
        self.git = GitManager()

        # Initialize integrated components if available
        if FULL_INTEGRATION:
            self.logger = setup_logger(debug=debug)
            self.system_diag = SystemDiagnostics()
            self.signal_analyzer = SignalAnalyzer()
            self.hardware_detector = HardwareDetector()
            self.node_tracker = UnifiedNodeTracker()
            self.gateway_config = GatewayConfig.load()
            self.bridge: Optional[RNSMeshtasticBridge] = None
            self.dashboard = StatusDashboard(node_tracker=self.node_tracker)
        else:
            self.logger = None

    def show_banner(self) -> None:
        """Display the application banner."""
        print()
        print("=" * 60)
        print(f"  RNS-MESHTASTIC GATEWAY TOOL | v{get_version()}")
        print("  MeshForge Integration - Supervisor NOC")
        print("=" * 60)
        if FULL_INTEGRATION:
            print("  [Full Integration Mode]")
        else:
            print("  [Basic Mode - Run 'pip install -r requirements.txt']")
        print()

    def main_menu(self) -> None:
        """Display and handle the main menu."""
        while True:
            self.show_banner()
            print("  MAIN MENU")
            print("-" * 40)
            print("  [1] Quick Status Dashboard")
            print("  [2] System Diagnostics")
            print("  [3] Signal Analysis")
            print("  [4] Gateway Bridge Control")
            print("  [5] Node Tracker")
            print("  [6] Hardware Configuration")
            print("  [7] Radio Settings")
            print("  [8] Update Tool")
            print("  [0] Exit")
            print("-" * 40)

            choice = input("  Select option: ").strip()

            if choice == "1":
                self.show_dashboard()
            elif choice == "2":
                self.run_diagnostics()
            elif choice == "3":
                self.run_signal_analysis()
            elif choice == "4":
                self.bridge_control_menu()
            elif choice == "5":
                self.node_tracker_menu()
            elif choice == "6":
                self.hardware_config_menu()
            elif choice == "7":
                self.radio_settings_menu()
            elif choice == "8":
                self.update_tool()
            elif choice == "0":
                print("\n  Goodbye!\n")
                break
            else:
                print("\n  Invalid option. Please try again.\n")
                input("  Press Enter to continue...")

    def show_dashboard(self) -> None:
        """Display the status dashboard."""
        print("\n" + "=" * 60)
        print("  STATUS DASHBOARD")
        print("=" * 60)

        if FULL_INTEGRATION:
            print(self.dashboard.format_text_dashboard())
        else:
            print(f"\n  System: {self.ai.run_context_check()}")
            print("  [Install full dependencies for complete dashboard]")

        input("\n  Press Enter to continue...")

    def run_diagnostics(self) -> None:
        """Run system diagnostics."""
        print("\n" + "=" * 60)
        print("  SYSTEM DIAGNOSTICS")
        print("=" * 60)

        if FULL_INTEGRATION:
            print("\n  Running comprehensive diagnostics...\n")

            # Run full diagnostics
            report = self.system_diag.run_full_diagnostics()

            print(f"  Results: {report['summary']['passed']}/{report['summary']['total']} checks passed")
            print(f"  Health: {report['summary']['health_percentage']:.0f}%")
            print()

            # Show results
            for result in report['results']:
                icon = "[+]" if result.passed else "[-]"
                print(f"  {icon} {result.name}: {result.message}")
        else:
            print(f"\n  {self.ai.run_context_check()}")
            print("\n  [Install full dependencies for complete diagnostics]")

        input("\n  Press Enter to continue...")

    def run_signal_analysis(self) -> None:
        """Run RF signal analysis."""
        print("\n" + "=" * 60)
        print("  SIGNAL ANALYSIS")
        print("=" * 60)

        if FULL_INTEGRATION:
            print("\n  Enter signal measurements (or press Enter for demo):\n")

            snr_input = input("  SNR (dB) [-20 to +20]: ").strip()
            rssi_input = input("  RSSI (dBm) [-130 to -50]: ").strip()

            # Use demo values if empty
            snr = float(snr_input) if snr_input else -5.0
            rssi = float(rssi_input) if rssi_input else -95.0

            # Analyze
            result = self.signal_analyzer.analyze(snr, rssi)

            print(f"\n  Quality: {result.quality.value.upper()}")
            print(f"  Diagnosis: {result.diagnosis}")
            print("\n  Recommendations:")
            for rec in result.recommendations:
                print(f"    - {rec}")
        else:
            # Basic analysis
            snr_input = input("\n  Enter SNR (dB): ").strip()
            rssi_input = input("  Enter RSSI (dBm): ").strip()

            try:
                snr = float(snr_input) if snr_input else 0
                rssi = float(rssi_input) if rssi_input else -100
                print(f"\n  {self.ai.analyze_signal(snr, rssi)}")
            except ValueError:
                print("\n  Invalid input. Please enter numeric values.")

        input("\n  Press Enter to continue...")

    def bridge_control_menu(self) -> None:
        """Bridge control submenu."""
        if not FULL_INTEGRATION:
            print("\n  Bridge control requires full integration.")
            print("  Run: pip install -r requirements.txt")
            input("\n  Press Enter to continue...")
            return

        while True:
            print("\n" + "=" * 60)
            print("  GATEWAY BRIDGE CONTROL")
            print("=" * 60)
            print("\n  [1] Start Bridge")
            print("  [2] Stop Bridge")
            print("  [3] View Bridge Status")
            print("  [4] Configure Bridge")
            print("  [0] Back to Main Menu")

            choice = input("\n  Select option: ").strip()

            if choice == "1":
                self._start_bridge()
            elif choice == "2":
                self._stop_bridge()
            elif choice == "3":
                self._show_bridge_status()
            elif choice == "4":
                self._configure_bridge()
            elif choice == "0":
                break

    def _start_bridge(self) -> None:
        """Start the gateway bridge."""
        if self.bridge is None:
            self.bridge = RNSMeshtasticBridge(
                config=self.gateway_config,
                node_tracker=self.node_tracker
            )
            self.dashboard.bridge = self.bridge

        if self.bridge.start():
            print("\n  Bridge started successfully!")
        else:
            print("\n  Failed to start bridge.")
        input("\n  Press Enter to continue...")

    def _stop_bridge(self) -> None:
        """Stop the gateway bridge."""
        if self.bridge:
            self.bridge.stop()
            print("\n  Bridge stopped.")
        else:
            print("\n  Bridge is not running.")
        input("\n  Press Enter to continue...")

    def _show_bridge_status(self) -> None:
        """Show bridge status."""
        if self.bridge:
            status = self.bridge.get_status()
            print(f"\n  Running: {status['running']}")
            print(f"  Meshtastic: {'Connected' if status['meshtastic_connected'] else 'Disconnected'}")
            print(f"  RNS: {'Connected' if status['rns_connected'] else 'Disconnected'}")
            print(f"  Messages Bridged: {status['messages_bridged']}")
            print(f"  Uptime: {status['uptime_seconds']:.0f}s")
        else:
            print("\n  Bridge not initialized.")
        input("\n  Press Enter to continue...")

    def _configure_bridge(self) -> None:
        """Configure bridge settings."""
        print("\n  Current Configuration:")
        print(f"    Meshtastic Host: {self.gateway_config.meshtastic.host}")
        print(f"    Meshtastic Port: {self.gateway_config.meshtastic.port}")
        print(f"    Bridge Enabled: {self.gateway_config.bridge_enabled}")
        print("\n  (Configuration editing coming soon)")
        input("\n  Press Enter to continue...")

    def node_tracker_menu(self) -> None:
        """Node tracker submenu."""
        if not FULL_INTEGRATION:
            print("\n  Node tracker requires full integration.")
            input("\n  Press Enter to continue...")
            return

        while True:
            print("\n" + "=" * 60)
            print("  NODE TRACKER")
            print("=" * 60)
            print("\n  [1] List All Nodes")
            print("  [2] Node Statistics")
            print("  [3] Export to GeoJSON")
            print("  [0] Back to Main Menu")

            choice = input("\n  Select option: ").strip()

            if choice == "1":
                self._list_nodes()
            elif choice == "2":
                self._show_node_stats()
            elif choice == "3":
                self._export_geojson()
            elif choice == "0":
                break

    def _list_nodes(self) -> None:
        """List all tracked nodes."""
        nodes = self.node_tracker.get_all()
        if not nodes:
            print("\n  No nodes tracked yet.")
        else:
            print(f"\n  Tracked Nodes ({len(nodes)}):")
            print("-" * 50)
            for node in nodes:
                name = node.long_name or node.short_name or "Unknown"
                status = "Online" if node.is_online else "Offline"
                print(f"  {node.unified_id[:20]:<20} {name:<15} [{status}]")
        input("\n  Press Enter to continue...")

    def _show_node_stats(self) -> None:
        """Show node statistics."""
        stats = self.node_tracker.get_statistics()
        print(f"\n  Total Nodes: {stats['total']}")
        print(f"  Online: {stats['online']}")
        print(f"  Offline: {stats['offline']}")
        print(f"  Meshtastic: {stats['meshtastic']}")
        print(f"  RNS: {stats['rns']}")
        print(f"  With Position: {stats['with_position']}")
        print(f"  Gateways: {stats['gateways']}")
        input("\n  Press Enter to continue...")

    def _export_geojson(self) -> None:
        """Export nodes to GeoJSON."""
        import json
        geojson = self.node_tracker.to_geojson()
        filename = "nodes_export.geojson"
        with open(filename, "w") as f:
            json.dump(geojson, f, indent=2)
        print(f"\n  Exported to {filename}")
        input("\n  Press Enter to continue...")

    def hardware_config_menu(self) -> None:
        """Hardware configuration submenu."""
        if not FULL_INTEGRATION:
            print("\n  Hardware detection requires full integration.")
            input("\n  Press Enter to continue...")
            return

        print("\n" + "=" * 60)
        print("  HARDWARE CONFIGURATION")
        print("=" * 60)
        print("\n  Scanning for hardware...\n")

        summary = self.hardware_detector.get_device_summary()

        print(f"  Board: {summary['board_model'] or 'Unknown'}")
        print(f"  Raspberry Pi: {'Yes' if summary['is_raspberry_pi'] else 'No'}")
        print(f"  Devices Found: {summary['total_devices']}")
        print(f"    USB Serial: {summary['usb_devices']}")
        print(f"    SPI: {summary['spi_devices']}")

        if summary['devices']:
            print("\n  Detected Devices:")
            for dev in summary['devices']:
                print(f"    - {dev['type']}: {dev['path']} ({dev['description']})")

        input("\n  Press Enter to continue...")

    def radio_settings_menu(self) -> None:
        """Radio settings submenu."""
        if not FULL_INTEGRATION:
            print("\n  Radio settings requires full integration.")
            input("\n  Press Enter to continue...")
            return

        print("\n" + "=" * 60)
        print("  RADIO SETTINGS")
        print("=" * 60)

        # Show current LoRa preset info
        from src.config.lora import get_preset_list
        presets = get_preset_list()

        print("\n  Available LoRa Presets:")
        for i, preset in enumerate(presets, 1):
            print(f"    [{i}] {preset['name']}")
            print(f"        BW: {preset['bandwidth_khz']}kHz, SF: {preset['spreading_factor']}, CR: {preset['coding_rate']}")
            print(f"        Data Rate: {preset['data_rate_bps']:.0f} bps")

        input("\n  Press Enter to continue...")

    def update_tool(self) -> None:
        """Update the tool via git."""
        print("\n" + "=" * 60)
        print("  UPDATE TOOL")
        print("=" * 60)
        print("\n  Checking for updates...")

        result = self.git.update_tool()
        print(f"\n  {result}")

        input("\n  Press Enter to continue...")

    def quick_status(self) -> None:
        """Show quick status and exit."""
        self.show_banner()
        if FULL_INTEGRATION:
            print(self.dashboard.format_text_dashboard())
        else:
            print(f"  {self.ai.run_context_check()}")

    # Legacy menu method for backwards compatibility
    def menu(self) -> None:
        """Legacy menu entry point."""
        self.main_menu()


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="RNS-Meshtastic Gateway Tool - MeshForge Integration"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Run bridge in background mode"
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show quick status and exit"
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Show version and exit"
    )
    return parser.parse_args()


def main() -> int:
    """Main entry point."""
    args = parse_args()

    if args.version:
        print(f"RNS-Meshtastic Gateway Tool v{get_version()}")
        return 0

    noc = SupervisorNOC(debug=args.debug)

    if args.status:
        noc.quick_status()
        return 0

    if args.daemon:
        if FULL_INTEGRATION:
            print("Starting bridge in daemon mode...")
            noc._start_bridge()
            print("Bridge running. Press Ctrl+C to stop.")
            try:
                import time
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                noc._stop_bridge()
        else:
            print("Daemon mode requires full integration.")
            return 1
        return 0

    # Interactive mode
    try:
        noc.main_menu()
    except KeyboardInterrupt:
        print("\n\n  Interrupted. Goodbye!\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
