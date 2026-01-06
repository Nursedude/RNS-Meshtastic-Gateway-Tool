import os
import sys

path = "launcher.py"
print(f"Reading {path}...")

with open(path, "r") as f:
    content = f.read()

# The specific block we want to replace
sim_block = '# In a real run: self.safe_subprocess([sys.executable, "-m", "RNS.Utilities.rnsd", "-vv"])\\n            print("  (Simulation: RNS Daemon would start here securely)")'
live_block = 'print("  [GO] Spawning RNS Daemon (Live)...")\\n            self.safe_subprocess([sys.executable, "-m", "RNS.Utilities.rnsd", "-vv"])'

if sim_block in content:
    new_content = content.replace(sim_block, live_block)
    with open(path, "w") as f:
        f.write(new_content)
    print("[SUCCESS] Gateway is now LIVE. Run 'python launcher.py' to start the radio.")
else:
    print("[INFO] Could not find simulation block. Already live?")
