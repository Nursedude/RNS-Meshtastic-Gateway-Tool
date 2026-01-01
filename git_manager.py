import subprocess
class GitManager:
    def update_tool(self):
        try:
            subprocess.run(["git", "pull", "origin", "main"], check=True)
            return "SUCCESS: System Updated."
        except: return "ERROR: Update failed."