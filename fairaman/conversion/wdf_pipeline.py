"""
Renishaw WDF Raman spectrum reader.

This module reads WDF files, extracts Raman spectra, spatial coordinates,
white-light images, and acquisition maps.
"""
# ── Standard library ──────────────────────────────────────────────────────────
import ctypes
import json
import sys
import traceback
from io import BytesIO
from pathlib import Path

# ── Third-party ───────────────────────────────────────────────────────────────
import h5py
import re
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image

# ── Internal party ───────────────────────────────────────────────────────────────
from fairaman.readers import wdf_reader, ascii_reader
from fairaman.metadata_management import _normalise_stem, _assemble_flat_data, \
    _get_excel_row, _load_metadata_sources
from fairaman.readers.wdf_reader import process_wdf
from fairaman.writers.hdf5_writer import write_hdf5_nexus
from fairaman.writers.hdf5_writer import export_json, export_csv

# ── Optional: Renishaw WDF reader ─────────────────────────────────────────────
try:
    from renishawWiRE import WDFReader
    HAS_WDF = True
except ImportError:
    HAS_WDF = False
    print(
        "[FAIRaman] INFO: renishawWiRE is not installed — WDF mode unavailable.\n"
        "           To enable: pip install renishawWiRE"
    )

# ── Windows DPI awareness ─────────────────────────────────────────────────────
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

COORDINATE_MODE_REGULAR = "regular_grid"
COORDINATE_MODE_POINTS  = "point_coordinates"

def _run_conversion_wdf(state: dict, frames: dict,
                        var_hdf5: tk.BooleanVar, var_json: tk.BooleanVar,
                        var_csv: tk.BooleanVar, progress_var: tk.StringVar,
                        progress_bar: ttk.Progressbar, root: tk.Tk) -> None:
    """
    Performs batch conversion of WDF files into the FAIRaman HDF5/NeXus format.

    For each WDF file found in the input directory, the function:
        1) normalizes the filename (without its extension) and searches for the
        corresponding row in the Excel file using `_get_excel_row`
        (first attempting an exact match, then a more permissive lookup);
        2) builds the metadata dictionary by combining information from the TXT
        file (Investigation/Assay levels) with metadata from the Excel file
        (Sample level), according to the mappings defined in the GUI;
        3) reads the spectral cube from the WDF file together with the optional
        white-light image;
        4) generates the selected output files (HDF5, JSON, and/or CSV).

    Files for which no corresponding row is found in the Excel file are
    skipped and reported in the final summary. If no Excel file is provided,
    all files are still converted using only the metadata from the TXT file.
    """
    if not HAS_WDF:
        messagebox.showerror(
            "Error",
            "renishawWiRE is not installed.\nInstall it with: pip install renishawWiRE"
        )
        return

    if not all(state["paths"].get(k) for k in ("wdf", "txt", "out")):
        messagebox.showerror(
            "Error", "Please select: WDF folder, Metadata TXT file, Output folder."
        )
        return

    wdf_dir = state["paths"]["wdf"]
    if not wdf_dir.is_dir():
        messagebox.showerror("Error", f"Invalid WDF directory:\n{wdf_dir}")
        return

    try:
        txt_meta, _, excel_map, filename_col, empty_row = (
            _load_metadata_sources(state, frames)
        )
    except Exception as exc:
        messagebox.showerror("Error", f"Could not load metadata:\n{exc}")
        return

    out_dir = state["paths"]["out"]
    out_dir.mkdir(parents=True, exist_ok=True)

    wdf_files = sorted({f for f in wdf_dir.glob("*") if f.suffix.lower() == ".wdf"})
    if not wdf_files:
        messagebox.showwarning("Warning", f"No WDF files found in:\n{wdf_dir}")
        return

    total, success_count, failed = len(wdf_files), 0, []
    progress_bar["maximum"] = total
    progress_bar["value"]   = 0

    for idx, wdf_path in enumerate(wdf_files, 1):
        try:
            progress_var.set(f"Processing {idx}/{total}: {wdf_path.name}")
            root.update_idletasks()

            stem = wdf_path.stem

            if filename_col:
                # Robust lookup: exact normalised match, then fuzzy fallback
                excel_row = _get_excel_row(stem, excel_map)
                if excel_row is None:
                    available = list(excel_map.keys())[:5]
                    msg = (
                        f"{wdf_path.name}: no Excel row matched stem='{stem}'. "
                        f"First 5 available keys: {available}"
                    )
                    failed.append(msg)
                    print(f"[FAIRaman] SKIP {stem}: {msg}")
                    continue
            else:
                # No Excel file loaded — convert with TXT metadata only
                excel_row = empty_row

            flat_data = _assemble_flat_data(txt_meta, excel_row, frames)
            metadata  = {"flat_data": flat_data, "excel_row": excel_row,
                         "txt_meta": txt_meta}
            spec_data = process_wdf(wdf_path)

            if var_hdf5.get():
                write_hdf5_nexus(out_dir / f"{stem}.h5", spec_data, metadata)
            if var_json.get():
                export_json(metadata, out_dir / f"{stem}.json")
            if var_csv.get():
                export_csv(spec_data, out_dir / f"{stem}.csv")

            success_count += 1
            progress_bar["value"] = idx

        except Exception as exc:
            failed.append(f"{wdf_path.name}: {exc}")
            print(f"[FAIRaman] ERROR processing {wdf_path.name}:")
            traceback.print_exc()

    _show_completion_report(progress_var, success_count, total, failed, out_dir)

def _show_completion_report(progress_var: tk.StringVar, success: int,
                            total: int, failed: list, out_dir: Path) -> None:
        
        """Display a modal summary dialog at the end of a batch conversion."""
        progress_var.set("Conversion complete.")
        msg = f"Conversion complete.\n\n✅ Files processed: {success}/{total}\n"
        if failed:
            msg += f"\n❌ Files with errors: {len(failed)}\n"
            msg += "\n".join(f"  • {e}" for e in failed[:5])
            if len(failed) > 5:
                msg += f"\n  … and {len(failed) - 5} more"
        msg += f"\n\n📁 Output written to:\n{out_dir}"
        messagebox.showinfo("FAIRaman — Conversion complete", msg)
