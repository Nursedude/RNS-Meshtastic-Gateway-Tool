import os
import sys
import time
import inspect
import RNS

# 1. Setup Paths
driver_path = os.path.expanduser("~/.reticulum/interfaces")
sys.path.append(os.getcwd() + "/src")
sys.path.append(driver_path)

print("==================================================")
print("   MESHFORGE SMART DIAGNOSTIC LAUNCHER")
print("==================================================")

def boot_sequence():
    # 2. Load the Driver
    try:
        from Meshtastic_Interface import MeshtasticInterface
        print("[OK] Driver Class Loaded: MeshtasticInterface")
    except ImportError as e:
        print(f"[FAIL] Could not load driver: {e}")
        return

    # 3. DIAGNOSTIC: Inspect the Constructor
    # This tells us exactly what the driver is asking for
    sig = inspect.signature(MeshtasticInterface.__init__)
    print(f"[DIAGNOSTIC] Driver expects: {sig}")

    # 4. Attempt to Construct
    rns_instance = RNS.Reticulum()
    
    # Create the config bundle (Standard Reticulum format)
    radio_config = {
        "port": "COM3",
        "bitrate": 9600,
        "name": "Meshtastic_Radio"
    }

    print(f"\n[GO] Attempting launch with config: {radio_config}")

    try:
        # ATTEMPT A: Standard Reticulum Signature (owner, config)
        if "configuration" in str(sig) or "config" in str(sig):
            print(" -> Detected Standard Signature (owner, config)")
            interface = MeshtasticInterface(rns_instance, radio_config)

        # ATTEMPT B: Direct Signature (owner, name, port...)
        else:
            print(" -> Detected Direct Signature. Unpacking config...")
            # We try to pass the config dict as kwargs if the signature allows
            interface = MeshtasticInterface(rns_instance, name="Meshtastic_Radio", port="COM3")

        # 5. Activate
        interface.OUT = True
        if interface not in RNS.Transport.interfaces:
            RNS.Transport.interfaces.append(interface)
        
        print("\n[SUCCESS] Radio Interface is LIVE!")
        print("-----------------------------------")
        while True:
            time.sleep(1)

    except TypeError as e:
        print(f"\n[CRITICAL ERROR] Argument Mismatch: {e}")
        print("Tip: The driver code might need 'owner, configuration' format.")
    except Exception as e:
        print(f"\n[ERROR] Runtime Failure: {e}")

if __name__ == "__main__":
    boot_sequence()