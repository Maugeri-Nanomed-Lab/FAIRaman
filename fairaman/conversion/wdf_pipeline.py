"""
Conversion pipeline — WDF batch mode.

Two layers:
    convert_wdf_batch()  — pure logic. Takes plain paths/booleans, returns a
                            ConversionResult. No Tkinter dependency — usable
                            from a script, notebook, or another GUI.
    run_conversion_wdf() — thin GUI wrapper. Reads Tkinter widgets/state,
                            calls convert_wdf_batch(), updates the progress
                            bar, and shows dialogs.
"""

import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import tkinter as tk
from tkinter import ttk, messagebox

from fairaman.metadata_management import _assemble_flat_data, _get_excel_row, _load_metadata_sources
from fairaman.readers.wdf_reader import process_wdf
from fairaman.validation import verify_conversion
from fairaman.writers.hdf5_writer import write_hdf5_nexus, export_json, export_csv
from fairaman.gui_helpers import _show_completion_report


@dataclass
class ConversionResult:
    """Outcome of a batch conversion run."""
    total: int
    success_count: int
    failed: list = field(default_factory=list)
    out_dir: Optional[Path] = None


def convert_wdf_batch(
    wdf_dir: Path,
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
    Convert every WDF file in `wdf_dir` into the requested output formats.

    Parameters
    ----------
    wdf_dir
        Folder containing the .wdf files to convert.
    out_dir
        Folder where outputs are written (created if missing).
    txt_meta, excel_map, filename_col, empty_row, frames
        Metadata already loaded via `_load_metadata_sources` (or assembled
        by hand for non-GUI use).
    write_hdf5, write_json, write_csv
        Which output formats to produce for each file.
    progress_callback
        Optional callable `(index, total, filename) -> None`, invoked before
        each file is processed. Pass `None` for silent operation (e.g. in a
        script). A GUI wrapper can use this to update a progress bar.

    Returns
    -------
    ConversionResult
        Summary of the run: total files, successes, and per-file failures.

    Raises
    ------
    ValueError
        If `wdf_dir` doesn't exist or contains no .wdf files.
    """
    wdf_dir = Path(wdf_dir)
    out_dir = Path(out_dir)

    if not wdf_dir.is_dir():
        raise ValueError(f"Invalid WDF directory: {wdf_dir}")

    out_dir.mkdir(parents=True, exist_ok=True)

    wdf_files = sorted({f for f in wdf_dir.glob("*") if f.suffix.lower() == ".wdf"})
    if not wdf_files:
        raise ValueError(f"No WDF files found in: {wdf_dir}")

    total, success_count, failed = len(wdf_files), 0, []

    for idx, wdf_path in enumerate(wdf_files, 1):
        try:
            if progress_callback is not None:
                progress_callback(idx, total, wdf_path.name)

            stem = wdf_path.stem

            if filename_col:
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
                excel_row = empty_row

            flat_data = _assemble_flat_data(txt_meta, excel_row, frames)
            metadata  = {"flat_data": flat_data, "excel_row": excel_row,
                         "txt_meta": txt_meta}
            spec_data = process_wdf(wdf_path)

            if write_hdf5:
                h5_path = out_dir / f"{stem}.h5"
                write_hdf5_nexus(h5_path, spec_data, metadata)

                ok, issues = verify_conversion(spec_data, h5_path)
                if not ok:
                    raise ValueError(
                        "HDF5 round-trip validation failed:\n  - "
                        + "\n  - ".join(issues)
                    )
                print(f"[FAIRaman] ✅ {wdf_path.name} → {h5_path.name}")

            if write_json:
                export_json(metadata, out_dir / f"{stem}.json")
            if write_csv:
                export_csv(spec_data, out_dir / f"{stem}.csv")

            success_count += 1

        except Exception as exc:
            failed.append(f"{wdf_path.name}: {exc}")
            print(f"[FAIRaman] ERROR processing {wdf_path.name}:")
            traceback.print_exc()

    return ConversionResult(total=total, success_count=success_count,
                             failed=failed, out_dir=out_dir)


def run_conversion_wdf(state: dict, frames: dict,
                        var_hdf5: tk.BooleanVar, var_json: tk.BooleanVar,
                        var_csv: tk.BooleanVar, progress_var: tk.StringVar,
                        progress_bar: ttk.Progressbar, root: tk.Tk) -> None:
    """
    GUI wrapper: reads Tkinter state/widgets, runs `convert_wdf_batch`,
    and reports the outcome via the progress bar and dialogs.
    """
    if not all(state["paths"].get(k) for k in ("wdf", "txt", "out")):
        messagebox.showerror(
            "Error", "Please select: WDF folder, Metadata TXT file, Output folder."
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
        result = convert_wdf_batch(
            wdf_dir=state["paths"]["wdf"],
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