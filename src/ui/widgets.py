"""
Shared TUI box-drawing primitives for Supervisor NOC screens.

Provides ANSI color codes, Unicode box characters, and helper
functions used by both the menu and the terminal dashboard.
"""
import re
import shutil


# ── ANSI Styling ─────────────────────────────────────────────
class C:
    """Terminal color codes."""
    RST  = '\033[0m'
    BOLD = '\033[1m'
    DIM  = '\033[2m'
    # Foreground
    RED  = '\033[91m'
    GRN  = '\033[92m'
    YLW  = '\033[93m'
    BLU  = '\033[94m'
    MAG  = '\033[95m'
    CYN  = '\033[96m'
    WHT  = '\033[97m'
    # Background accents
    BG_GRN = '\033[42m'
    BG_RED = '\033[41m'


# ── Box-Drawing Characters ───────────────────────────────────
BOX_H  = '─'
BOX_V  = '│'
BOX_TL = '┌'
BOX_TR = '┐'
BOX_BL = '└'
BOX_BR = '┘'
BOX_LT = '├'
BOX_RT = '┤'

_ANSI_RE = re.compile(r'\033\[[0-9;]*m')


# ── Helpers ──────────────────────────────────────────────────
def strip_ansi(text):
    """Remove ANSI escape sequences from *text*."""
    return _ANSI_RE.sub('', text)


def cols():
    """Return terminal width, with a sane fallback."""
    return shutil.get_terminal_size((80, 24)).columns


def center(text, width, fill=' '):
    """Center-pad *text* within *width* (ignoring ANSI codes for length calc)."""
    visible = len(strip_ansi(text))
    pad = max(0, width - visible)
    left = pad // 2
    right = pad - left
    return fill * left + text + fill * right


# ── Box Functions ────────────────────────────────────────────
def box_top(w):
    return f"  {C.DIM}{BOX_TL}{BOX_H * (w - 2)}{BOX_TR}{C.RST}"


def box_mid(w):
    return f"  {C.DIM}{BOX_LT}{BOX_H * (w - 2)}{BOX_RT}{C.RST}"


def box_bot(w):
    return f"  {C.DIM}{BOX_BL}{BOX_H * (w - 2)}{BOX_BR}{C.RST}"


def box_row(content, w):
    """Wrap content in box side-bars, padded to width *w*."""
    visible = len(strip_ansi(content))
    inner = w - 4  # account for "│ " and " │"
    pad = max(0, inner - visible)
    return f"  {C.DIM}{BOX_V}{C.RST} {content}{' ' * pad} {C.DIM}{BOX_V}{C.RST}"


def box_section(label, w):
    """Section divider with embedded label."""
    inner = w - 4
    lbl = f" {label} "
    bar_len = max(0, inner - len(lbl))
    left = bar_len // 2
    right = bar_len - left
    return f"  {C.DIM}{BOX_LT}{BOX_H * left}{C.RST}{C.BOLD}{C.CYN}{lbl}{C.RST}{C.DIM}{BOX_H * right}{BOX_RT}{C.RST}"


def box_kv(key, value, w, key_color=C.CYN, val_color=C.WHT):
    """Key-value row inside a box."""
    return box_row(f"{key_color}{key}:{C.RST}  {val_color}{value}{C.RST}", w)
