import sys, platform
from ai_methods import DiagnosticEngine
from git_manager import GitManager
import version
class SupervisorNOC:
    def __init__(self):
        self.ai = DiagnosticEngine()
        self.git = GitManager()
    def menu(self):
        print(f"🛰️ RNS SUPERVISOR | v{version.get_version()}")
        print("[1] AI Diagnostics")
        print("[2] Update Tool")
        c = input("Select: ")
        if c=='1': print(self.ai.run_context_check())
        if c=='2': print(self.git.update_tool())
if __name__ == "__main__":
    SupervisorNOC().menu()