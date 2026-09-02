# ─────────────────────────────────────────────────────────────────────────────
# CONVERSION PIPELINE — ASCII TXT MODE
# ─────────────────────────────────────────────────────────────────────────────

import traceback
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk
from fairaman.metadata_management import _load_metadata_sources, _assemble_flat_data, _get_excel_row
from fairaman.readers.ascii_reader import process_txt_spectrum
from fairaman.writers.hdf5_writer import write_hdf5_nexus, export_json, export_csv

def _run_conversion_txt(state: dict, frames: dict,
                        var_hdf5: tk.BooleanVar, var_json: tk.BooleanVar,
                        var_csv: tk.BooleanVar, progress_var: tk.StringVar,
                        progress_bar: ttk.Progressbar, root: tk.Tk) -> None:
    """
    Performs batch conversion of ASCII spectral files into the FAIRaman
    HDF5/NeXus format.

    The workflow is identical to `_run_conversion_wdf`, but is applied to
    two-column ASCII spectral files (`.txt`, `.csv`, `.dat`). The TXT metadata
    file is automatically excluded from the list of input spectra, even if it is
    located in the same directory.

    To associate metadata from the Excel file, the same `_get_excel_row`
    function used by the WDF pipeline is employed, ensuring consistent
    filename-matching behavior across both workflows.

    Files for which no corresponding row is found in the Excel file are
    skipped and reported in the final summary. If no Excel file is provided,
    all files are still converted using only the metadata from the TXT file.
    """
    if not all(state["paths"].get(k) for k in ("spectra_dir", "txt", "out")):
        messagebox.showerror(
            "Error",
            "Please select: Spectra folder, Metadata TXT file, Output folder."
        )
        return

    spectra_dir = state["paths"]["spectra_dir"]
    if not spectra_dir.is_dir():
        messagebox.showerror("Error", f"Invalid spectra directory:\n{spectra_dir}")
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

    # Collect input spectra, excluding the metadata TXT file if co-located
    meta_resolved = state["paths"]["txt"].resolve()
    spectra_files = [
        p for p in spectra_dir.glob("*.txt") if p.resolve() != meta_resolved
    ]
    spectra_files += sorted(spectra_dir.glob("*.csv"))
    spectra_files += sorted(spectra_dir.glob("*.dat"))

    if not spectra_files:
        messagebox.showwarning(
            "Warning", f"No spectral files (.txt/.csv/.dat) found in:\n{spectra_dir}"
        )
        return

    total, success_count, failed = len(spectra_files), 0, []
    progress_bar["maximum"] = total
    progress_bar["value"]   = 0

    for idx, sp_path in enumerate(spectra_files, 1):
        try:
            progress_var.set(f"Processing {idx}/{total}: {sp_path.name}")
            root.update_idletasks()

            stem = sp_path.stem

            if filename_col:
                excel_row = _get_excel_row(stem, excel_map)
                if excel_row is None:
                    available = list(excel_map.keys())[:5]
                    msg = (
                        f"{sp_path.name}: no Excel row matched stem='{stem}'. "
                        f"First 5 available keys: {available}"
                    )
                    failed.append(msg)
                    print(f"[FAIRaman] SKIP {stem}: {msg}")
                    continue
            else:
                excel_row = empty_row

            flat_data = _assemble_flat_data(txt_meta, excel_row, frames)
            metadata  = {"flat_data": flat_data, "excel_row": excel_row,
                         "txt_meta": txt_meta}
            spec_data = process_txt_spectrum(sp_path)

            if var_hdf5.get():
                write_hdf5_nexus(out_dir / f"{stem}.h5", spec_data, metadata)
            if var_json.get():
                export_json(metadata, out_dir / f"{stem}.json")
            if var_csv.get():
                export_csv(spec_data, out_dir / f"{stem}.csv")

            success_count += 1
            progress_bar["value"] = idx

        except Exception as exc:
            failed.append(f"{sp_path.name}: {exc}")
            print(f"[FAIRaman] ERROR processing {sp_path.name}:")
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
