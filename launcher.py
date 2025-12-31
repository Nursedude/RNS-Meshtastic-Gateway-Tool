import os
import sys
import time
import subprocess

# Colors
CYAN = '\033[96m'
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
RESET = '\033[0m'

def clear_screen():
    os.system('clear')

def print_header():
    clear_screen()
    print(f"{CYAN}=========================================={RESET}")
    print(f"{CYAN}   RNS Meshtastic Gateway - Control Panel {RESET}")
    print(f"{CYAN}=========================================={RESET}")
    print("")

def check_dependencies():
    print(f"{YELLOW}[*] Checking dependencies...{RESET}")
    try:
        import RNS
        import meshtastic
        print(f"{GREEN}[+] Dependencies found.{RESET}")
        time.sleep(1)
        return True
    except ImportError:
        print(f"{RED}[!] Missing libraries.{RESET}")
        choice = input("Install requirements now? (y/n): ")
        if choice.lower() == 'y':
            os.system("pip install -r requirements.txt")
            return True
        return False

def setup_config():
    print_header()
    print(f"{YELLOW}--- Configuration Wizard ---{RESET}")
    current_aspect = "meshtastic_bridge"
    if os.path.exists("config.py"):
        print("Existing config found.")
    
    new_aspect = input(f"Enter RNS Aspect Name (default: {current_aspect}): ") or current_aspect
    if "." in new_aspect:
        print(f"{RED}[!] Error: Aspect names cannot contain dots.{RESET}")
        time.sleep(2)
        return setup_config()

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
    os.system("ls -l /dev/ttyACM* /dev/ttyUSB* 2>/dev/null")
    print("\nAttempting Meshtastic Info check:")
    os.system("meshtastic --info")
    print("\n-----------------------------")
    input("Press Enter to return to menu...")

def start_gateway():
    print_header()
    print(f"{GREEN}>>> Starting Gateway... (Press Ctrl+C to stop){RESET}")
    time.sleep(1)
    os.system("sudo python3 main.py")
    input("\nGateway stopped. Press Enter to continue...")

def main_menu():
    while True:
        print_header()
        print("1. Run Setup Wizard (Configure)")
        print("2. Run Hardware Diagnostics")
        print("3. START Gateway")
        print("4. Install Dependencies")
        print("5. Exit")
        print("")
        choice = input(f"{CYAN}Select an option [1-5]: {RESET}")
        
        if choice == '1': setup_config()
        elif choice == '2': run_diagnostics()
        elif choice == '3': start_gateway()
        elif choice == '4': 
            os.system("pip install -r requirements.txt")
            input("Press Enter...")
        elif choice == '5': sys.exit()

if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        print("\nExiting...")
        sys.exit()
