#!/usr/bin/env python3
import sys
import os
import time
import subprocess
import shutil

# Ensure we can find the src directory for the driver
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

class GatewayLauncher:
    def __init__(self):
        self.rns_config_path = os.path.expanduser("~/.reticulum/config")
        self.interface_source = os.path.join("src", "Meshtastic_Interface.py")
        self.interface_dest = os.path.expanduser("~/.reticulum/interfaces/Meshtastic_Interface.py")
        self.is_windows = os.name == 'nt'

    def clear_screen(self):
        os.system('cls' if self.is_windows else 'clear')

    def print_header(self):
        self.clear_screen()
        print("============================================================")
        print("  RNS-MESHTASTIC GATEWAY TOOL | v2.2 (STABLE)")
        print("  Architecture: TCP Hub + Client Mute + Perms Fix")
        print("============================================================")

    def check_driver(self):
        print("\n[1/3] Checking Driver Integration...")
        if not os.path.exists(self.interface_source):
            print("  [ERROR] src/Meshtastic_Interface.py missing!")
            return False
        
        os.makedirs(os.path.dirname(self.interface_dest), exist_ok=True)
        try:
            shutil.copy(self.interface_source, self.interface_dest)
            print("  [OK] Meshtastic Driver installed to ~/.reticulum/interfaces/")
            return True
        except Exception as e:
            print(f"  [ERROR] Could not copy driver: {e}")
            return False

    def fix_rns_config(self):
        print("\n[2/3] Applying Windows Socket Fix...")
        config_block = """
[reticulum]
  enable_transport = yes
  share_instance = yes
  shared_instance_port = 37428
  instance_control_port = 37429
  panic_on_interface_error = no

[logging]
  loglevel = 4

[[Local Hub]]
  type = TCPServerInterface
  interface_enabled = yes
  listen_ip = 0.0.0.0
  listen_port = 4242

[[Meshtastic Radio]]
  type = MeshtasticInterface
  interface_enabled = yes
  port = COM3
  bitrate = 9600 
"""
        try:
            os.makedirs(os.path.dirname(self.rns_config_path), exist_ok=True)
            with open(self.rns_config_path, "w") as f:
                f.write(config_block)
            print("  [OK] Config written with TCPServerInterface (Port 4242).")
            return True
        except Exception as e:
            print(f"  [ERROR] Could not write config: {e}")
            return False

    def start_gateway(self):
        print("\n[3/3] Starting RNS Gateway Daemon...")
        print("  - Press CTRL+C to stop the gateway.")
        try:
            # subprocess.run([sys.executable, "-m", "RNS.Utilities.rnsd", "-vv"])
            print("  (Simulation: RNS Daemon would start here)")
        except KeyboardInterrupt:
            print("\n  [STOP] Gateway stopped by user.")

    def run(self):
        self.print_header()
        if self.check_driver() and self.fix_rns_config():
            print("\nReady to launch.")
            self.start_gateway()

if __name__ == "__main__":
    app = GatewayLauncher()
    app.run()