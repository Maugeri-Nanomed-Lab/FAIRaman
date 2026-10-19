"""
Shared GUI helper functions for FAIRaman.
"""

from pathlib import Path
import tkinter as tk
from tkinter import messagebox

def _show_completion_report(
    progress_var: tk.StringVar,
    success: int,
    total: int,
    failed: list,
    out_dir: Path,
) -> None:
    """Display a modal summary dialog at the end of a batch conversion."""

    progress_var.set("Conversion complete.")

    msg = (
        f"Conversion complete.\n\n"
        f"✅ Files processed: {success}/{total}\n"
    )

    if failed:
        msg += f"\n❌ Files with errors: {len(failed)}\n"
        msg += "\n".join(f"  • {e}" for e in failed[:5])

        if len(failed) > 5:
            msg += f"\n  … and {len(failed) - 5} more"

    msg += f"\n\n📁 Output written to:\n{out_dir}"

    messagebox.showinfo(
        "FAIRaman — Conversion complete",
        msg
    )