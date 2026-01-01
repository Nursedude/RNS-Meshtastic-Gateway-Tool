import os
import sys
import time
import random
import subprocess

# Colors
CYAN = '\033[96m'
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
RESET = '\033[0m'

SIM_MODE = False

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def print_header():
    clear_screen()
    sim_tag = f" {RED}[SIMULATION MODE]{RESET}" if SIM_MODE else ""
    print(f"{CYAN}=========================================={RESET}")
    print(f"{CYAN}   RNS Meshtastic Gateway - Control Panel {RESET}{sim_tag}")
    print(f"{CYAN}=========================================={RESET}")

def git_sync():
    """Automated Git Push logic"""
    print_header()
    print(f"{YELLOW}--- Automated Cloud Sync ---{RESET}")
    try:
        print("[*] Adding changes...")
        subprocess.run(["git", "add", "."], check=True)
        
        commit_msg = f"Auto-sync from Launcher: {time.strftime('%Y-%m-%d %H:%M:%S')}"
        print(f"[*] Committing: {commit_msg}")
        subprocess.run(["git", "commit", "-m", commit_msg], check=True)
        
        print("[*] Pushing to GitHub...")
        # Note: This will use your saved SSH key
        subprocess.run(["git", "push"], check=True)
        
        print(f"\n{GREEN}[+] Repository Updated Successfully!{RESET}")
    except subprocess.CalledProcessError as e:
        print(f"\n{RED}[!] Sync Failed. Ensure you have no conflicts.{RESET}")
        print(f"Error: {e}")
    
    input("\nPress Enter to return to menu...")

def start_gateway():
    print_header()
    print(f"{GREEN}>>> Launching Gateway Sequence...{RESET}\n")
    
    # Progress Bar Handshake
    for i in range(0, 101, 5):
        width = 30
        filled = int(width * i / 100)
        bar = "█" * filled + "-" * (width - filled)
        print(f"\r{YELLOW}Initializing: [{bar}] {i}%{RESET}", end="")
        time.sleep(0.05)
    
    print(f"\n\n{GREEN}[+] Gateway Active. Monitoring Traffic...{RESET}")
    print(f"{YELLOW}(Press Ctrl+C to Stop){RESET}\n")

    try:
        while True:
            # Mock Activity for Sim
            packet = random.choice(["MESH_DATA", "NODE_ANNOUNCE", "POSITION"])
            print(f"[{time.strftime('%H:%M:%S')}] {packet} -> RNS Destination <0f4e...>")
            time.sleep(random.uniform(1, 3))
    except KeyboardInterrupt:
        print(f"\n{RED}Gateway Stopped.{RESET}")
        time.sleep(1)

def toggle_sim():
    global SIM_MODE
    SIM_MODE = not SIM_MODE

def main_menu():
    while True:
        print_header()
        print(f"Mode: {'SIMULATION' if SIM_MODE else 'HARDWARE'}")
        print("-" * 42)
        print("1. START Gateway (with Progress & Info)")
        print("2. Run Hardware Diagnostics")
        print("3. System Setup (Fix USB/Perms)")
        print("4. Toggle Simulation Mode")
        print(f"{GREEN}5. CLOUD SYNC (Git Push Changes){RESET}")
        print("6. Exit")
        print("")
        
        choice = input(f"{CYAN}Select an option [1-6]: {RESET}")
        
        if choice == '1': start_gateway()
        elif choice == '2': input("Diagnostics coming soon...")
        elif choice == '3': input("Setup coming soon...")
        elif choice == '4': toggle_sim()
        elif choice == '5': git_sync()
        elif choice == '6': sys.exit()

if __name__ == "__main__":
    main_menu()
