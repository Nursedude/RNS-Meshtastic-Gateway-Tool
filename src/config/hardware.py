"""
Hardware configuration and detection for RNS-Meshtastic Gateway Tool.

Provides automatic hardware detection, configuration management,
and support for various LoRa devices and SBCs.
"""

import os
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict, Any

from ..utils.system import (
    is_raspberry_pi,
    get_board_model,
    run_command,
)


class DeviceType(Enum):
    """Supported device types."""

    UNKNOWN = "unknown"
    RAK4631 = "rak4631"
    RAK13302 = "rak13302"
    TBEAM = "tbeam"
    TBEAM_S3 = "tbeam_s3"
    HELTEC_V3 = "heltec_v3"
    TLORA = "tlora"
    WAVESHARE = "waveshare"
    DIY = "diy"


class ConnectionType(Enum):
    """Device connection types."""

    USB_SERIAL = "usb_serial"
    SPI = "spi"
    I2C = "i2c"
    GPIO = "gpio"
    NETWORK = "network"


@dataclass
class HardwareDevice:
    """Represents a detected hardware device."""

    device_type: DeviceType
    connection_type: ConnectionType
    device_path: Optional[str] = None
    vendor_id: Optional[str] = None
    product_id: Optional[str] = None
    serial_number: Optional[str] = None
    description: str = ""
    is_verified: bool = False


@dataclass
class HardwareConfig:
    """
    Hardware configuration for gateway devices.

    Stores detected hardware, connection settings,
    and device-specific parameters.
    """

    # Primary device
    primary_device: Optional[HardwareDevice] = None

    # SPI settings
    spi_bus: int = 0
    spi_device: int = 0
    spi_speed: int = 2000000

    # I2C settings
    i2c_bus: int = 1
    i2c_address: int = 0x3C  # Common OLED address

    # GPIO settings (BCM numbering)
    gpio_reset: int = 17
    gpio_dio0: int = 22
    gpio_dio1: int = 23

    # Serial settings
    serial_port: Optional[str] = None
    serial_baudrate: int = 115200

    # Board info
    board_model: Optional[str] = None
    is_raspberry_pi: bool = False

    def __post_init__(self):
        """Initialize board detection."""
        self.board_model = get_board_model()
        self.is_raspberry_pi = is_raspberry_pi()


class HardwareDetector:
    """
    Automatic hardware detection for LoRa devices.

    Scans for USB serial devices, SPI interfaces,
    and known hardware configurations.
    """

    # Known USB VID:PID combinations for LoRa devices
    KNOWN_DEVICES = {
        # ESP32-S3 based
        ("303a", "1001"): DeviceType.TBEAM_S3,
        # CP210x USB to UART
        ("10c4", "ea60"): DeviceType.UNKNOWN,
        # CH340/CH341
        ("1a86", "7523"): DeviceType.UNKNOWN,
        # FTDI
        ("0403", "6001"): DeviceType.UNKNOWN,
        # RAK nRF52840
        ("239a", "8029"): DeviceType.RAK4631,
    }

    def __init__(self):
        """Initialize the hardware detector."""
        self._detected_devices: List[HardwareDevice] = []

    def scan_usb_devices(self) -> List[HardwareDevice]:
        """
        Scan for USB serial devices.

        Returns:
            List of detected HardwareDevice objects
        """
        devices = []

        # Scan /dev for serial ports
        serial_patterns = ["/dev/ttyUSB*", "/dev/ttyACM*"]

        for pattern in serial_patterns:
            rc, stdout, _ = run_command(f"ls {pattern} 2>/dev/null", suppress_errors=True)
            if rc == 0:
                for port in stdout.split():
                    port = port.strip()
                    if port:
                        device = self._identify_serial_device(port)
                        if device:
                            devices.append(device)

        return devices

    def _identify_serial_device(self, port: str) -> Optional[HardwareDevice]:
        """
        Identify a serial device.

        Args:
            port: Serial port path

        Returns:
            HardwareDevice or None
        """
        # Get device info via udevadm
        rc, stdout, _ = run_command(
            f"udevadm info --query=property --name={port} 2>/dev/null",
            suppress_errors=True
        )

        if rc != 0:
            return HardwareDevice(
                device_type=DeviceType.UNKNOWN,
                connection_type=ConnectionType.USB_SERIAL,
                device_path=port,
                description="Unknown serial device"
            )

        props = {}
        for line in stdout.split("\n"):
            if "=" in line:
                key, value = line.split("=", 1)
                props[key] = value

        vendor_id = props.get("ID_VENDOR_ID", "").lower()
        product_id = props.get("ID_MODEL_ID", "").lower()
        serial = props.get("ID_SERIAL_SHORT")

        # Try to identify device type
        device_type = DeviceType.UNKNOWN
        vid_pid = (vendor_id, product_id)
        if vid_pid in self.KNOWN_DEVICES:
            device_type = self.KNOWN_DEVICES[vid_pid]

        # Check product description for clues
        product = props.get("ID_MODEL", "").lower()
        if "rak" in product:
            device_type = DeviceType.RAK4631
        elif "tbeam" in product:
            device_type = DeviceType.TBEAM
        elif "heltec" in product:
            device_type = DeviceType.HELTEC_V3
        elif "t-lora" in product or "tlora" in product:
            device_type = DeviceType.TLORA

        return HardwareDevice(
            device_type=device_type,
            connection_type=ConnectionType.USB_SERIAL,
            device_path=port,
            vendor_id=vendor_id,
            product_id=product_id,
            serial_number=serial,
            description=props.get("ID_MODEL", "Unknown")
        )

    def scan_spi_devices(self) -> List[HardwareDevice]:
        """
        Scan for SPI LoRa devices.

        Returns:
            List of detected SPI devices
        """
        devices = []

        # Check for SPI device nodes
        spi_paths = ["/dev/spidev0.0", "/dev/spidev0.1", "/dev/spidev1.0"]

        for spi_path in spi_paths:
            if Path(spi_path).exists():
                # SPI device exists - could be a LoRa HAT
                bus, device = self._parse_spi_path(spi_path)

                device_obj = HardwareDevice(
                    device_type=DeviceType.DIY,  # Assume DIY/HAT setup
                    connection_type=ConnectionType.SPI,
                    device_path=spi_path,
                    description=f"SPI bus {bus} device {device}"
                )

                # Try to identify if it's a known HAT
                device_obj = self._identify_spi_hat(device_obj)
                devices.append(device_obj)

        return devices

    def _parse_spi_path(self, path: str) -> tuple:
        """Parse SPI device path to extract bus and device numbers."""
        # /dev/spidev0.0 -> bus=0, device=0
        name = Path(path).name
        if name.startswith("spidev"):
            parts = name[6:].split(".")
            if len(parts) == 2:
                return int(parts[0]), int(parts[1])
        return 0, 0

    def _identify_spi_hat(self, device: HardwareDevice) -> HardwareDevice:
        """
        Try to identify SPI HAT type.

        Args:
            device: HardwareDevice to update

        Returns:
            Updated HardwareDevice
        """
        # Check device tree for HAT info
        hat_info_path = Path("/proc/device-tree/hat")
        if hat_info_path.exists():
            product_path = hat_info_path / "product"
            if product_path.exists():
                try:
                    product = product_path.read_text().strip().rstrip("\x00")
                    device.description = product

                    if "waveshare" in product.lower():
                        device.device_type = DeviceType.WAVESHARE
                    elif "rak" in product.lower():
                        device.device_type = DeviceType.RAK13302
                except Exception:
                    pass

        return device

    def scan_all(self) -> List[HardwareDevice]:
        """
        Perform comprehensive hardware scan.

        Returns:
            List of all detected devices
        """
        self._detected_devices.clear()

        # Scan USB serial devices
        self._detected_devices.extend(self.scan_usb_devices())

        # Scan SPI devices (only on Raspberry Pi or similar)
        if is_raspberry_pi():
            self._detected_devices.extend(self.scan_spi_devices())

        return self._detected_devices

    def get_primary_device(self) -> Optional[HardwareDevice]:
        """
        Get the best candidate for primary device.

        Returns:
            Most likely primary device or None
        """
        if not self._detected_devices:
            self.scan_all()

        if not self._detected_devices:
            return None

        # Prefer verified devices
        verified = [d for d in self._detected_devices if d.is_verified]
        if verified:
            return verified[0]

        # Prefer known device types over unknown
        known = [d for d in self._detected_devices if d.device_type != DeviceType.UNKNOWN]
        if known:
            return known[0]

        # Return first available
        return self._detected_devices[0]

    def get_hardware_config(self) -> HardwareConfig:
        """
        Generate hardware configuration based on detected devices.

        Returns:
            HardwareConfig instance
        """
        config = HardwareConfig()

        primary = self.get_primary_device()
        if primary:
            config.primary_device = primary

            if primary.connection_type == ConnectionType.USB_SERIAL:
                config.serial_port = primary.device_path

            elif primary.connection_type == ConnectionType.SPI:
                bus, device = self._parse_spi_path(primary.device_path or "")
                config.spi_bus = bus
                config.spi_device = device

        return config

    def get_device_summary(self) -> Dict[str, Any]:
        """
        Get summary of detected hardware.

        Returns:
            Dictionary with hardware summary
        """
        if not self._detected_devices:
            self.scan_all()

        return {
            "total_devices": len(self._detected_devices),
            "usb_devices": sum(
                1 for d in self._detected_devices
                if d.connection_type == ConnectionType.USB_SERIAL
            ),
            "spi_devices": sum(
                1 for d in self._detected_devices
                if d.connection_type == ConnectionType.SPI
            ),
            "known_devices": sum(
                1 for d in self._detected_devices
                if d.device_type != DeviceType.UNKNOWN
            ),
            "devices": [
                {
                    "type": d.device_type.value,
                    "connection": d.connection_type.value,
                    "path": d.device_path,
                    "description": d.description,
                }
                for d in self._detected_devices
            ],
            "board_model": get_board_model(),
            "is_raspberry_pi": is_raspberry_pi(),
        }
