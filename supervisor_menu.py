import os
import sys
import time
import subprocess
import threading
import webbrowser

# ANSI Colors for a Professional Look
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

# Global State
gateway_process = None

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def print_header():
    clear_screen()
    print(f"{Colors.HEADER}==================================================")
    print(f"   SUPERVISOR NOC | COMMAND CENTER | v3.0")
    print(f"=================================================={Colors.ENDC}")
    
    # Status Indicator
    if gateway_process and gateway_process.poll() is None:
        print(f"   GATEWAY STATUS: {Colors.GREEN}[ ONLINE ]{Colors.ENDC} (PID: {gateway_process.pid})")
    else:
        print(f"   GATEWAY STATUS: {Colors.FAIL}[ OFFLINE ]{Colors.ENDC}")
    print("--------------------------------------------------")

def start_gateway():
    global gateway_process
    if gateway_process and gateway_process.poll() is None:
        print(f"\n{Colors.WARNING}[!] Gateway is already running!{Colors.ENDC}")
        time.sleep(2)
        return

    print(f"\n{Colors.BLUE}[>] Launching Gateway Engine...{Colors.ENDC}")
    # We launch it in a separate window so logs don't clutter the menu
    if os.name == 'nt':
        gateway_process = subprocess.Popen(["start", "python", "launcher.py"], shell=True)
    else:
        gateway_process = subprocess.Popen(["x-terminal-emulator", "-e", "python launcher.py"])
    
    print(f"{Colors.GREEN}[OK] Gateway Launch Signal Sent.{Colors.ENDC}")
    time.sleep(2)

def stop_gateway():
    global gateway_process
    print(f"\n{Colors.WARNING}[!] Stopping Gateway...{Colors.ENDC}")
    # On Windows, killing a 'start' process is tricky, usually we let user close window
    # But we can try to kill the python process if we tracked it directly.
    # For now, we advise the user:
    print("   (Please close the Gateway Terminal Window manually to stop it securely)")
    
    # Reset state if they closed it
    gateway_process = None
    input("\nPress Enter after you have closed the window...")

def run_diagnostics():
    print(f"\n{Colors.BLUE}[>] Running Network Status (rnstatus)...{Colors.ENDC}")
    os.system("python -m RNS.Utilities.rnstatus")
    input(f"\n{Colors.BLUE}[Press Enter to return to menu]{Colors.ENDC}")

def run_update():
    print(f"\n{Colors.BLUE}[>] Checking for GitHub Updates...{Colors.ENDC}")
    os.system("git pull")
    input(f"\n{Colors.BLUE}[Press Enter to return to menu]{Colors.ENDC}")

def launch_dashboard():
    # This feature launches a simple web server to view logs/status
    print(f"\n{Colors.BLUE}[>] Starting Local Web Dashboard...{Colors.ENDC}")
    print("   Opening http://localhost:8080 in your browser...")
    
    # Create a simple dashboard file on the fly if missing
    if not os.path.exists("dashboard.html"):
        with open("dashboard.html", "w") as f:
            f.write("<h1>Supervisor NOC Dashboard</h1><p>Status: Monitoring...</p>")
            
    # Open browser
    webbrowser.open("http://localhost:8080")
    
    # Run simple server
    try:
        subprocess.run(["python", "-m", "http.server", "8080"])
    except KeyboardInterrupt:
        pass

def main():
    while True:
        print_header()
        print(" 1. [START]   Start Gateway (New Window)")
        print(" 2. [STOP]    Stop Gateway")
        print(" 3. [STATUS]  Network Diagnostics")
        print(" 4. [TEST]    Fire Broadcast Ping")
        print(" 5. [UPDATE]  Update Software (Git)")
        print(" 6. [WEB]     Launch Web Dashboard")
        print(" 0. [EXIT]    Exit Supervisor")
        
        choice = input(f"\n{Colors.BOLD}Select Command > {Colors.ENDC}")

        if choice == '1':
            start_gateway()
        elif choice == '2':
            stop_gateway()
        elif choice == '3':
            run_diagnostics()
        elif choice == '4':
            os.system("python tests/broadcast.py")
            input("\nPress Enter...")
        elif choice == '5':
            run_update()
        elif choice == '6':
            launch_dashboard()
        elif choice == '0':
            print("Exiting...")
            sys.exit()
        else:
            print("Invalid Selection.")
            time.sleep(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nExiting...")