"""
Version information for RNS-Meshtastic Gateway Tool.
"""

MAJOR = 2
MINOR = 0
PATCH = 0
STATUS = "Alpha"

# MeshForge integration version
MESHFORGE_VERSION = "1.0.0"


def get_version() -> str:
    """Get the full version string."""
    return f"{MAJOR}.{MINOR}.{PATCH}-{STATUS}"


def get_version_tuple() -> tuple:
    """Get version as tuple (major, minor, patch)."""
    return (MAJOR, MINOR, PATCH)


def get_full_info() -> dict:
    """Get complete version information."""
    return {
        "version": get_version(),
        "major": MAJOR,
        "minor": MINOR,
        "patch": PATCH,
        "status": STATUS,
        "meshforge_version": MESHFORGE_VERSION,
    }
