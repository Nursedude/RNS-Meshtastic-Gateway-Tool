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
        print(f"{CYAN}[SIM] Adding user '{os.getenv('USER', 'user')}' to dialout group...{RESET}")
        time.sleep(0.5)
        print(f"\n{GREEN}[+] (Simulated) System optimized.{RESET}")
    else:
        print("1. Disabling ModemManager (fixes USB conflicts)...")
        os.system("sudo systemctl stop ModemManager 2>/dev/null")
        os.system("sudo systemctl disable ModemManager 2>/dev/null")
        print("2. Setting USB permissions (dialout group)...")
        user = os.getenv("USER")
        if user:
            os.system(f"sudo usermod -a -G dialout {user}")
        print(f"\n{GREEN}[+] System optimized.{RESET}")
        print(f"{RED}[!] YOU MUST REBOOT YOUR PI FOR THESE CHANGES TO WORK.{RESET}")
    input("Press Enter to return to menu...")

def setup_config():
    print_header()
    print(f"{YELLOW}--- Configuration Wizard ---{RESET}")
    current_aspect = "meshtastic_bridge"
    if os.path.exists("config.py"):
        print("Existing config found.")
    elif SIM_MODE:
         print(f"{CYAN}[SIM] No config found, creating new default.{RESET}")
    new_aspect = input(f"Enter RNS Aspect Name (default: {current_aspect}): ") or current_aspect
    if "." in new_aspect:
        print(f"{RED}[!] Error: Aspect names cannot contain dots.{RESET}")
        time.sleep(2)
        return setup_config()
    if SIM_MODE:
        print(f"{CYAN}[SIM] Writing to virtual config...{RESET}")
        time.sleep(1)
    else:
        with open("config.py", "w") as f:
            f.write("# RNS Meshtastic Gateway Configuration\n")
            f.write(f"RNS_ASPECT = '{new_aspect}'\n")
            f.write("RADIO_PORT = None\n")
    print(f"\n{GREEN}[+] Configuration saved!{RESET}")
    time.sleep(1.5)

def run_diagnostics():
    print_header()
    print(f"{YELLOW}--- Hardware Diagnostics ---{RESET}")
    print("Scanning USB ports...")
    if SIM_MODE:
        time.sleep(1)
        print(f"crw-rw---- 1 root dialout 166, 0 {time.strftime('%b %d %H:%M')} /dev/ttyACM0 (SIMULATED)")
        print("\nAttempting Meshtastic Info check...")
        time.sleep(1.5)
        print(f"{GREEN}Owner: Simulation_User (Sim), id: !12345678")
        print("Nodes in Mesh: 5")
        print("Battery: 85%")
        print(f"Firmware: 2.5.0.35{RESET}")
    else:
        os.system("ls -l /dev/ttyACM* /dev/ttyUSB* 2>/dev/null")
        print("\nAttempting Meshtastic Info check (Ctrl+C to cancel)...")
        try:
            os.system("meshtastic --info")
        except:
            print("Check failed.")
    print("\n-----------------------------")
    input("Press Enter to return to menu...")

def start_gateway():
    print_header()
    if SIM_MODE:
        print(f"{GREEN}>>> Starting Gateway (SIMULATION)... (Press Ctrl+C to stop){RESET}")
        try:
            while True:
                print(f"[Info] Received packet from Meshtastic !{random.randint(1000,9999)}")
                time.sleep(2)
                print(f"[Info] Sent packet to Reticulum...")
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    else:
        print(f"{GREEN}>>> Starting Gateway... (Press Ctrl+C to stop){RESET}")
        time.sleep(1)
        os.system("sudo python3 main.py")
    input("\nGateway stopped. Press Enter to continue...")

def toggle_sim():
    global SIM_MODE
    SIM_MODE = not SIM_MODE

def main_menu():
    while True:
        print_header()
        print("1. System Setup (Run First - Fixes USB)")
        print("2. Configure Settings")
        print("3. Run Hardware Diagnostics")
        print("4. START Gateway")
        print("5. Install Dependencies")
        print("6. Exit")
        sim_state = "DISABLE" if SIM_MODE else "ENABLE"
        print(f"7. {sim_state} Simulation Mode")
        print("")
        choice = input(f"{CYAN}Select an option [1-7]: {RESET}")
        if choice == '1': optimize_system()
        elif choice == '2': setup_config()
        elif choice == '3': run_diagnostics()
        elif choice == '4': start_gateway()
        elif choice == '5': 
            if SIM_MODE:
                print(f"{CYAN}[SIM] Dependencies installed.{RESET}")
                time.sleep(1)
            else:
                os.system("pip install -r requirements.txt")
                input("Press Enter...")
        elif choice == '6': sys.exit()
        elif choice == '7': toggle_sim()

if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        print("\nExiting...")
        sys.exit()
