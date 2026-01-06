import RNS
import os
import sys
import time

# Add src folder to path so we can import the driver
sys.path.insert(0, os.path.join(os.getcwd(), 'src'))

# Import the custom driver
try:
    from Meshtastic_Interface import MeshtasticInterface
except ImportError as e:
    print("[CRITICAL] Could not import Meshtastic Driver.")
    print(f"Error: {e}")
    sys.exit(1)

def start_gateway():
    print("============================================================")
    print("  SUPERVISOR NOC | RNS-MESHTASTIC GATEWAY v2.4")
    print("============================================================")

    # 1. Initialize Reticulum
    # This automatically loads the default config from ~/.reticulum
    rns_connection = RNS.Reticulum()

    print("\n[GO] Loading Interface 'Meshtastic Radio'...")
    
    # 2. Instantiate the Driver
    # We pass the RNS instance (owner) and a name.
    # The driver handles the hardware connection internally.
    mesh_interface = MeshtasticInterface(rns_connection, "Meshtastic Radio")
    
    # 3. Register the Interface with Reticulum
    # This tells RNS to start routing traffic through our driver.
    # Note: Modern RNS automatically picks up interfaces if added to config,
    # but for a custom standalone script, we might need to hold the reference.
    
    if mesh_interface.online:
        print(" [SUCCESS] Interface Loaded! Waiting for traffic...")
        
        # Keep the main thread alive
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[STOP] Shutting down gateway...")
            mesh_interface.detach()
            sys.exit(0)
    else:
        print(" [FAIL] Interface failed to initialize.")
        sys.exit(1)

if __name__ == "__main__":
    start_gateway()