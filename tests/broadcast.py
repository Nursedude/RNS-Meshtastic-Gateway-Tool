import RNS
import time
import sys

reticulum = RNS.Reticulum()
identity = RNS.Identity()

def broadcast_test():
    print("==================================================")
    print("   BROADCAST TEST: SLOW MODE")
    print("==================================================")
    
    destination = RNS.Destination(identity, RNS.Destination.IN, RNS.Destination.SINGLE, "ping_test", "broadcast")
    
    print("\n[>] Packaging Announce Packet...")
    destination.announce()
    print("[>] Packet handed to Reticulum.")
    
    print("\n[WAIT] Keeping connection open for 5 seconds...")
    print("       WATCH THE RADIO LED NOW!")
    time.sleep(5)
    print("[DONE] Exiting.")

if __name__ == "__main__":
    broadcast_test()