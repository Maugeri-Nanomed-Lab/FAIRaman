"""
Command-line / GUI entry point for FAIRaman.
"""

import ctypes
from fairaman.gui import launch_gui

# ── Optional: Renishaw WDF reader check ─────────────────────────────────
try:
    from renishawWiRE import WDFReader
    HAS_WDF = True
except ImportError:
    HAS_WDF = False
    print(
        "[FAIRaman] INFO: renishawWiRE is not installed — WDF mode unavailable.\n"
        "           To enable: pip install renishawWiRE"
    )

# ── Windows DPI awareness ────────────────────────────────────────────────
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass


def main():
    """Entry point used by the console script and __main__.py."""
    launch_gui()


if __name__ == "__main__":
    main()