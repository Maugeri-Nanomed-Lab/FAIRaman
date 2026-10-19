"""
Command-line / GUI entry point for FAIRaman.
"""

import ctypes

from fairaman.gui import launch_gui


def _set_dpi_awareness() -> None:
    """Enable DPI awareness on Windows when available."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass


def main() -> None:
    """Launch the FAIRaman graphical user interface."""
    _set_dpi_awareness()
    launch_gui()


if __name__ == "__main__":
    main()