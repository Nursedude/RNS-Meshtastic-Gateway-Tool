import platform
class DiagnosticEngine:
    def __init__(self): self.os_type = platform.system()
    def analyze_signal(self, snr, rssi):
        if snr < -10: return "DIAGNOSTIC: High Noise Floor. Check cabling."
        return "DIAGNOSTIC: Signal Integrity Optimal."
    def run_context_check(self):
        return f"CONTEXT: {self.os_type} detected. Optimization active."