@"
import sys

# The specific text we know exists in the file (Partial match to ignore indentation)
target_text = 'Simulation: RNS Daemon'

# The code we want to run instead (Live RNS Daemon)
# We use 12 spaces of indentation to align with the rest of the file
live_code = '            print("  [GO] Spawning RNS Daemon (Live)...")\n            self.safe_subprocess([sys.executable, "-m", "RNS.Utilities.rnsd", "-vv"])'

print("Scanning launcher.py...")

with open("launcher.py", "r") as f:
    lines = f.readlines()

new_lines = []
patched = False

for line in lines:
    if target_text in line:
        # We found the simulation line! Replace it with the live code.
        new_lines.append(live_code + "\n")
        patched = True
        print(" -> Found and replaced simulation block.")
    else:
        # Keep original line
        new_lines.append(line)

if patched:
    with open("launcher.py", "w") as f:
        f.writelines(new_lines)
    print("[SUCCESS] launcher.py is now LIVE.")
else:
    print("[ERROR] Could not find the simulation text. Please check the file manually.")
"@ | Out-File -Encoding UTF8 force_live.py