"""
Conversion pipeline — ASCII/TXT batch mode.

Two layers:
    convert_ascii_batch() — pure logic. Takes plain paths/booleans, returns a
                             ConversionResult. No Tkinter dependency.
    run_conversion_txt()  — thin GUI wrapper around convert_ascii_batch().
"""

import traceback
from pathlib import Path
from typing import Callable, Optional

import tkinter as tk
from tkinter import ttk, messagebox

from fairaman.validation import verify_conversion
from fairaman.metadata_management import _load_metadata_sources, _assemble_flat_data, _get_excel_row
from fairaman.readers.ascii_reader import process_txt_spectrum
from fairaman.writers.hdf5_writer import write_hdf5_nexus, export_json, export_csv
from fairaman.gui_helpers import _show_completion_report
from fairaman.conversion.wdf_pipeline import ConversionResult


def convert_ascii_batch(
    spectra_dir: Path,
    txt_path: Path,
    out_dir: Path,
    txt_meta,
    excel_map,
    filename_col,
    empty_row,
    frames,
    write_hdf5: bool = True,
    write_json: bool = False,
    write_csv: bool = False,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> ConversionResult:
    """
    Convert every ASCII spectral file (.txt/.csv/.dat) in `spectra_dir` into
    the requested output formats. `txt_path` (the metadata TXT file) is
    excluded from the input list even if it lives in the same folder.

    See `convert_wdf_batch` for the meaning of the shared parameters.

    Raises
    ------
    ValueError
        If `spectra_dir` doesn't exist or contains no spectral files.
    """
    spectra_dir = Path(spectra_dir)
    out_dir = Path(out_dir)

    if not spectra_dir.is_dir():
        raise ValueError(f"Invalid spectra directory: {spectra_dir}")

    out_dir.mkdir(parents=True, exist_ok=True)

    meta_resolved = Path(txt_path).resolve()
    spectra_files = [
        p for p in spectra_dir.glob("*.txt") if p.resolve() != meta_resolved
    ]
    spectra_files += sorted(spectra_dir.glob("*.csv"))
    spectra_files += sorted(spectra_dir.glob("*.dat"))

    if not spectra_files:
        raise ValueError(
            f"No spectral files (.txt/.csv/.dat) found in: {spectra_dir}"
        )

    total, success_count, failed = len(spectra_files), 0, []

    for idx, sp_path in enumerate(spectra_files, 1):
        try:
            if progress_callback is not None:
                progress_callback(idx, total, sp_path.name)

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

            if write_hdf5:
                h5_path = out_dir / f"{stem}.h5"
                write_hdf5_nexus(h5_path, spec_data, metadata)

                ok, issues = verify_conversion(spec_data, h5_path)
                if not ok:
                    raise ValueError(
                        "HDF5 round-trip validation failed:\n  - "
                        + "\n  - ".join(issues)
                    )
                print(f"[FAIRaman] ✅ {sp_path.name} → {h5_path.name}")

            if write_json:
                export_json(metadata, out_dir / f"{stem}.json")
            if write_csv:
                export_csv(spec_data, out_dir / f"{stem}.csv")

            success_count += 1

        except Exception as exc:
            failed.append(f"{sp_path.name}: {exc}")
            print(f"[FAIRaman] ERROR processing {sp_path.name}:")
            traceback.print_exc()

    return ConversionResult(total=total, success_count=success_count,
                             failed=failed, out_dir=out_dir)


def run_conversion_txt(state: dict, frames: dict,
                        var_hdf5: tk.BooleanVar, var_json: tk.BooleanVar,
                        var_csv: tk.BooleanVar, progress_var: tk.StringVar,
                        progress_bar: ttk.Progressbar, root: tk.Tk) -> None:
    """
    GUI wrapper: reads Tkinter state/widgets, runs `convert_ascii_batch`,
    and reports the outcome via the progress bar and dialogs.
    """
    if not all(state["paths"].get(k) for k in ("spectra_dir", "txt", "out")):
        messagebox.showerror(
            "Error",
            "Please select: Spectra folder, Metadata TXT file, Output folder."
        )
        return

    try:
        txt_meta, _, excel_map, filename_col, empty_row = (
            _load_metadata_sources(state, frames)
        )
    except Exception as exc:
        messagebox.showerror("Error", f"Could not load metadata:\n{exc}")
        return

    def _on_progress(idx: int, total: int, filename: str) -> None:
        progress_bar["maximum"] = total
        progress_var.set(f"Processing {idx}/{total}: {filename}")
        progress_bar["value"] = idx
        root.update_idletasks()

    try:
        result = convert_ascii_batch(
            spectra_dir=state["paths"]["spectra_dir"],
            txt_path=state["paths"]["txt"],
            out_dir=state["paths"]["out"],
            txt_meta=txt_meta,
            excel_map=excel_map,
            filename_col=filename_col,
            empty_row=empty_row,
            frames=frames,
            write_hdf5=var_hdf5.get(),
            write_json=var_json.get(),
            write_csv=var_csv.get(),
            progress_callback=_on_progress,
        )
    except ValueError as exc:
        messagebox.showerror("Error", str(exc))
        return

    _show_completion_report(progress_var, result.success_count, result.total,
                             result.failed, result.out_dir)