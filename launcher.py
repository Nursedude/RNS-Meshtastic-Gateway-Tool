import os
import sys
import time
import random

# Colors
CYAN = '\033[96m'
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
RESET = '\033[0m'

# Global State
SIM_MODE = False

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def print_header():
    clear_screen()
    sim_tag = f" {RED}[SIMULATION MODE]{RESET}" if SIM_MODE else ""
    print(f"{CYAN}=========================================={RESET}")
    print(f"{CYAN}   RNS Meshtastic Gateway - Control Panel {RESET}{sim_tag}")
    print(f"{CYAN}=========================================={RESET}")
    print("")

def optimize_system():
    print_header()
    print(f"{YELLOW}--- System Optimization & Permissions ---{RESET}")
    if SIM_MODE:
        print(f"{CYAN}[SIM] Stopping ModemManager service...{RESET}")
        time.sleep(0.5)
        print(f"{CYAN}[SIM] Disabling ModemManager...{RESET}")
        time.sleep(0.5)
        print(f"\n{GREEN}[+] (Simulated) System optimized.{RESET}")
    else:
        print("1. Disabling ModemManager...")
        os.system("sudo systemctl stop ModemManager 2>/dev/null")
        os.system("sudo systemctl disable ModemManager 2>/dev/null")
        print("2. Setting USB permissions...")
        user = os.getenv("USER")
        if user:
            os.system(f"sudo usermod -a -G dialout {user}")
        print(f"\n{GREEN}[+] System optimized.{RESET}")
    input("Press Enter to return to menu...")

def run_diagnostics():
    print_header()
    print(f"{YELLOW}--- Hardware Diagnostics ---{RESET}")
    if SIM_MODE:
        time.sleep(1)
        print(f"/dev/ttyACM0 (SIMULATED)")
        print(f"{GREEN}Battery: 85% | Nodes: 5 | Status: Online{RESET}")
    else:
        os.system("ls -l /dev/ttyACM* /dev/ttyUSB* 2>/dev/null")
        os.system("meshtastic --info")
    print("\n-----------------------------")
    input("Press Enter to return to menu...")

def toggle_sim():
    global SIM_MODE
    SIM_MODE = not SIM_MODE

def main_menu():
    while True:
        print_header()
        print("1. System Setup (Run First)")
        print("2. Run Hardware Diagnostics")
        print("3. START Gateway")
        print("4. Exit")
        sim_state = "DISABLE" if SIM_MODE else "ENABLE"
        print(f"5. {sim_state} Simulation Mode")
        print("")
        choice = input(f"{CYAN}Select an option [1-5]: {RESET}")
        if choice == '1': optimize_system()
        elif choice == '2': run_diagnostics()
        elif choice == '3': 
            print("Starting...")
            time.sleep(1)
            if not SIM_MODE: os.system("sudo python3 main.py")
        elif choice == '4': sys.exit()
        elif choice == '5': toggle_sim()

if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        sys.exit()