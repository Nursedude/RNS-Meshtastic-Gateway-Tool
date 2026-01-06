import os
import sys
import json
import time
import subprocess
import webbrowser

# Path Setup
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_PATH = os.path.join(BASE_DIR, 'config.json')
RNS_CONFIG = os.path.join(os.path.expanduser("~"), ".reticulum", "config")
NOMAD_CONFIG = os.path.join(os.path.expanduser("~"), ".nomadnet", "config")

def load_config():
    try:
        with open(CONFIG_PATH, 'r') as f:
            return json.load(f)
    except:
        return {"gateway": {"name": "Supervisor NOC", "port": "COM3"}, "dashboard": {"port": 5000}}

class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def print_banner(cfg):
    os.system('cls' if os.name == 'nt' else 'clear')
    print(f"{Colors.HEADER} SUPERVISOR NOC | COMMAND CENTER v4.0{Colors.ENDC}")
    print(f"")
    print(f"  Radio: {Colors.BLUE}{cfg['gateway']['port']}{Colors.ENDC} |  Dash: {Colors.BLUE}{cfg['dashboard']['port']}{Colors.ENDC}")
    print(f"")

def edit_file(path):
    if os.path.exists(path):
        print(f"{Colors.WARNING} Opening {os.path.basename(path)}...{Colors.ENDC}")
        subprocess.run(["notepad.exe", path])
    else:
        print(f"{Colors.FAIL} File not found: {path}{Colors.ENDC}")
        time.sleep(2)

def main_menu():
    while True:
        cfg = load_config()
        print_banner(cfg)
        print(f" {Colors.BOLD} LAUNCHERS{Colors.ENDC}")
        print("  1.  Start Mesh Gateway")
        print("  2.   Start NomadNet")
        print("  3.  Open Web Deep-Dive")
        
        print(f"\n {Colors.BOLD}  CONFIGURATORS (Deep Dive){Colors.ENDC}")
        print("  4.   Edit Gateway Config (JSON)")
        print("  5.   Edit Reticulum Config")
        print("  6.  Edit NomadNet Config")
        
        print(f"\n {Colors.BOLD}  TOOLS & MAINTENANCE{Colors.ENDC}")
        print("  7.  Run RNS Status")
        print("  8.  Fire Test Ping")
        print("  9.  Git Update (Conservative)")
        print("  0.  Exit")
        
        choice = input(f"\n{Colors.BLUE}Supervisor > {Colors.ENDC}")

        if choice == '1': 
            subprocess.Popen(["start", "python", "launcher.py"], shell=True)
        elif choice == '2':
            subprocess.Popen(["start", "nomadnet"], shell=True)
        elif choice == '3':
            webbrowser.open(f"http://localhost:{cfg['dashboard']['port']}")
        elif choice == '4': edit_file(CONFIG_PATH)
        elif choice == '5': edit_file(RNS_CONFIG)
        elif choice == '6': edit_file(NOMAD_CONFIG)
        elif choice == '7': 
            os.system("python -m RNS.Utilities.rnstatus")
            input("\nPress Enter...")
        elif choice == '8': 
            os.system("python tests/broadcast.py")
            input("\nPress Enter...")
        elif choice == '9': 
            os.system("git pull")
            input("\nUpdate complete. Press Enter...")
        elif choice == '0': sys.exit()

if __name__ == "__main__":
    main_menu()
