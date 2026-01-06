import os
import sys
import time

# 1. Define paths to find the driver
driver_path = os.path.expanduser("~/.reticulum/interfaces")
local_src = os.path.join(os.getcwd(), "src")

# Add paths so Python can find the file
sys.path.append(local_src)
sys.path.append(driver_path)

print("==================================================")
print(" RNS MESH GATEWAY - DIRECT LAUNCHER")
print("==================================================")

try:
    # 2. Import Reticulum Core
    import RNS
    print("[OK] Reticulum Core Loaded.")
    
    # 3. Import the Custom Driver
    # This is the magic step rnsd was missing!
    from Meshtastic_Interface import MeshtasticInterface
    print("[OK] Meshtastic Driver Loaded.")
    
except ImportError as e:
    print(f"\n[CRITICAL ERROR] Missing Component: {e}")
    print(f"Searched in:\n - {driver_path}\n - {local_src}")
    input("Press Enter to exit...")
    sys.exit(1)

def main():
    # 4. Initialize Reticulum
    # We allow it to read the standard config for identity, etc.
    rns_instance = RNS.Reticulum()
    
    print("\n[GO] Initializing Radio Interface on COM3...")
    
    # 5. Manually Attach the Radio
    # We do this in code to ensure it loads, bypassing config ambiguities
    try:
        radio_interface = MeshtasticInterface(
            owner=rns_instance,
            name="Meshtastic_Radio",
            port="COM3"  # Change this if your radio is on a different port!
        )
        
        # Turn on output so we see traffic
        radio_interface.OUT = True
        
        # Register it with Reticulum
        # (Depending on driver version, it might auto-register, but this is safe)
        if radio_interface not in RNS.Transport.interfaces:
            RNS.Transport.interfaces.append(radio_interface)
            
        print("[SUCCESS] Radio Interface Attached!")
        print("gateway is running. Press CTRL+C to stop.")
        
        # 6. Keep the gateway alive
        while True:
            time.sleep(1)
            
    except Exception as e:
        print(f"\n[ERROR] Could not connect to Radio: {e}")
        print("Check: Is the radio plugged in? Is it definitely COM3?")

if __name__ == "__main__":
    main()