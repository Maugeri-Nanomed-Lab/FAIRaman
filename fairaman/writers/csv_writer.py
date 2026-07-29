
# ─────────────────────────────────────────────────────────────────────────────
# DATASET CSV GENERATION (interpolated, multi-file)
# ─────────────────────────────────────────────────────────────────────────────
#
# Design:
#   1. Each file is loaded and its mean spectrum computed (spatial average for
#      WDF maps, identity for single-point ASCII).
#   2. Files are split into LW and CH groups:
#        a. If the filename contains "CH" (case-insensitive) -> CH group.
#        b. Otherwise -> LW group, but the spectral centre of mass is also
#           checked: if it is above 2200 cm-1 while the file was classified as
#           LW (or below 2200 cm-1 while classified as CH), a warning is printed
#           and the filename-based classification is kept.
#   3. Each group builds its own common grid (intersection of all member axes)
#      at the user-chosen step, so LW and CH CSVs have independent column sets.
#   4. Every spectrum is interpolated (np.interp) onto its group grid.
#   5. Two CSVs are written: LW_dataset.csv and CH_dataset.csv.
#      Structure: filename | <int wavenumber> | ... | <int wavenumber>
# ─────────────────────────────────────────────────────────────────────────────

# Threshold (cm-1) used for spectral centre-of-mass classification.
# Spectra whose energy centre of mass is above this value are considered CH.
import traceback
from pathlib import Path
import numpy as np
import pandas as pd
import tkinter as tk
from tkinter import messagebox, ttk
from readers.wdf_reader import process_wdf
from readers.ascii_reader import process_txt_spectrum

_CH_CENTROID_THRESHOLD = 2200.0

class DatasetConfig:
    """
    Parameters controlling the interpolated dataset export.

    Attributes
    ----------
    step : float
        Wavenumber step of the common interpolation grid (cm-1).
        Applied independently to the LW and CH groups.
    """
    def __init__(self, step: float = 2.0):
        self.step = step

def _mean_spectrum(data: dict) -> tuple:
    """
    Return the spatially averaged spectrum from a spectral data dict.

    For single-point acquisitions (cube shape 1x1xN) this is the raw
    spectrum. For 2-D maps (ny x nx x N) the mean is taken over all
    spatial pixels, collapsing the spatial dimensions into one vector.

    Returns
    -------
    raman_shift : np.ndarray, shape (N,)
    mean_intensity : np.ndarray, shape (N,)
    """
    cube = data["cube"]
    ny, nx, n = cube.shape
    return data["raman_shift"], cube.reshape(ny * nx, n).mean(axis=0)

def _spectral_centroid(shift: np.ndarray, intensity: np.ndarray) -> float:
    """
    Computes the intensity-weighted center of mass of a Raman spectrum.

    Parameters
    ----------
    shift : np.ndarray
        Raman shift axis (cm⁻¹).

    intensity : np.ndarray
        Corresponding spectral intensity values. Negative values are clipped
        to zero before computing the center of mass.

    Returns
    -------
    float
        Intensity-weighted center-of-mass position (cm⁻¹).
    """
    w = np.clip(intensity, 0, None)
    total = w.sum()
    if total == 0:
        return float(shift.mean())
    return float((shift * w).sum() / total)

def _classify_file(filename: str, shift: np.ndarray,
                   intensity: np.ndarray) -> str:
    """
    Classify a spectrum file as 'CH' or 'LW'.

    Rule: if the filename contains the string 'CH' (case-insensitive) the
    file is classified as CH. Every other file is classified as LW.
    The spectral centre of mass is computed only for logging purposes — it
    does NOT affect the classification result.

    Parameters
    ----------
    filename : str
        Bare filename.
    shift : np.ndarray
        Wavenumber axis of the spectrum.
    intensity : np.ndarray
        Mean intensity of the spectrum.

    Returns
    -------
    str
        'CH' or 'LW'.
    """
    label    = "CH" if "CH" in filename.upper() else "LW"
    centroid = _spectral_centroid(shift, intensity)
    print(f"[FAIRaman] Dataset: '{filename}' -> {label} (centroid {centroid:.0f} cm-1)")
    return label

def _read_sample_type_from_hdf5(h5_path: Path) -> str:
    """
    Read the SAMPLE/SAMPLE_INFO/sample_type field from a FAIRaman HDF5 file.

    Parameters
    ----------
    h5_path : Path
        Path to the .h5 file produced by a previous FAIRaman conversion.

    Returns
    -------
    str
        The sample_type value, or 'Unknown' if the file does not exist,
        cannot be opened, or the field is absent / empty.
    """
    if not h5_path.exists():
        return "Unknown"
    try:
        import h5py
        with h5py.File(h5_path, "r") as f:
            val = f.get("SAMPLE/SAMPLE_INFO/sample_type")
            if val is None:
                return "Unknown"
            decoded = val[()].decode("utf-8") if isinstance(val[()], bytes) else str(val[()])
            return decoded.strip() or "Unknown"
    except Exception as exc:
        print(f"[FAIRaman] Dataset: cannot read sample_type from '{h5_path.name}': {exc}")
        return "Unknown"

def _safe_label(text: str) -> str:
    """
    Convert an arbitrary string into a safe filename component.

    Spaces and slashes are replaced with underscores; other non-alphanumeric
    characters (except hyphens) are removed.
    """
    import re as _re
    s = str(text).strip().replace(" ", "_").replace("/", "_")
    s = _re.sub(r"[^\w\-]", "", s)
    return s or "Unknown"

def _collect_and_classify(file_paths: list, mode: str,
                          out_dir: Path,
                          progress_cb=None) -> dict:
    """
    Load all spectral files, compute mean spectra, and group them by
    (spectral_region, sample_type).

    Spectral region ('LW' or 'CH') is determined by _classify_file.
    sample_type is read from the HDF5 file with the same stem located in
    out_dir. If no HDF5 exists or the field is absent, 'Unknown' is used.

    Parameters
    ----------
    file_paths : list[Path]
        Ordered list of input spectrum files.
    mode : str
        'wdf' or 'txt'.
    out_dir : Path
        Directory where HDF5 outputs were previously written.
    progress_cb : callable or None
        Optional callback f(i, total, name).

    Returns
    -------
    dict
        Mapping of group_key -> list[dict], where group_key is a string
        like 'LW_Plasma' or 'CH_Lipoprotein', and each record dict has
        keys: filename, shift, intensity.
    """
    groups: dict = {}
    total = len(file_paths)

    for i, fp in enumerate(file_paths, 1):
        try:
            data        = process_wdf(fp) if mode == "wdf" else process_txt_spectrum(fp)
            shift, intensity = _mean_spectrum(data)
            region      = _classify_file(fp.name, shift, intensity)

            # Look for co-located HDF5 with same stem
            h5_path     = out_dir / (fp.stem + ".h5")
            sample_type = _read_sample_type_from_hdf5(h5_path)
            safe_type   = _safe_label(sample_type)

            group_key = f"{region}_{safe_type}"
            print(
                f"[FAIRaman] Dataset: '{fp.name}' -> {region} | "
                f"sample_type='{sample_type}' | group='{group_key}'"
            )

            rec = {"filename": fp.name, "shift": shift, "intensity": intensity}
            groups.setdefault(group_key, []).append(rec)

        except Exception as exc:
            print(f"[FAIRaman] Dataset: skipping '{fp.name}': {exc}")

        if progress_cb:
            progress_cb(i, total, fp.name)

    # Summary
    for gk, recs in sorted(groups.items()):
        print(f"[FAIRaman] Dataset: group '{gk}' -> {len(recs)} file(s)")

    return groups

def _build_common_grid(records: list, step: float) -> np.ndarray:
    """
    Build a uniform wavenumber grid as the UNION of all file ranges.

    Uses min(all minima) → max(all maxima) so that every file is included.
    Files whose range does not cover a given wavenumber point will receive
    intensity = 0 at that point (no extrapolation, no crash).

    Logs the range of every file in the group to help diagnose outliers.

    Parameters
    ----------
    records : list[dict]
        Records with 'shift' and 'filename' keys.
    step : float
        Grid spacing in cm-1.

    Returns
    -------
    np.ndarray
        Uniformly spaced wavenumber grid.
    """
    for r in records:
        print(
            f"[FAIRaman] Dataset:   '{r['filename']}' range "
            f"{r['shift'].min():.1f}-{r['shift'].max():.1f} cm-1 "
            f"({len(r['shift'])} pts)"
        )
    global_min = min(r["shift"].min() for r in records)
    global_max = max(r["shift"].max() for r in records)
    grid = np.arange(global_min, global_max + step * 0.5, step)
    print(
        f"[FAIRaman] Dataset: grid (union) {grid[0]:.1f}-{grid[-1]:.1f} cm-1, "
        f"step={step} cm-1, {len(grid)} points"
    )
    return grid

def _build_and_write_group(records: list, step: float,
                           out_path: Path) -> int:
    """
    Build the common grid, interpolate all spectra, and write the CSV.

    Output format (transposed):
      First column  : "raman_shift" — the common wavenumber grid values
      Other columns : one column per file (header = filename)

    This layout makes the CSV directly usable in tools like pandas, R, or
    Excel, where each sample is a variable (column) and each wavenumber
    is an observation (row).

    Parameters
    ----------
    records : list[dict]
        Non-empty list of spectral records for one group (LW or CH).
    step : float
        Grid spacing in cm-1.
    out_path : Path
        Destination CSV file.

    Returns
    -------
    int
        Number of wavenumber rows written (= grid length).
    """
    grid = _build_common_grid(records, step)

    # Safe interpolation: points outside a file's range → 0 (no extrapolation)
    def _safe_interp(grid, shift, intensity):
        out = np.zeros(len(grid), dtype=np.float64)
        mask = (grid >= shift.min()) & (grid <= shift.max())
        out[mask] = np.interp(grid[mask], shift, intensity)
        return out

    # matrix shape: (n_files, n_grid) — each row is one file
    matrix = np.empty((len(records), len(grid)), dtype=np.float64)
    for i, rec in enumerate(records):
        matrix[i] = _safe_interp(grid, rec["shift"], rec["intensity"])

    # Final layout:
    #   filename  | 700   | 701   | 702   | ...
    #   file1.wdf | 57.5  | 43.8  | 64.4  | ...
    #   file2.wdf | 49.8  | 47.2  | 54.7  | ...
    #
    # Rows = files, columns = wavenumber points (integers, cm-1)
    # First column header is "filename", others are integer wavenumbers.
    filenames   = [r["filename"] for r in records]
    col_headers = [str(int(round(w))) for w in grid]
    df = pd.DataFrame(matrix, columns=col_headers, index=filenames)
    df.index.name = "filename"
    df.to_csv(out_path)   # index=True writes filename as first column

    print(
        f"[FAIRaman] Dataset: wrote '{out_path.name}' "
        f"({len(records)} sample rows x {len(grid)} wavenumber columns, "
        f"{grid[0]:.0f}-{grid[-1]:.0f} cm-1)"
    )
    return len(grid)

def generate_dataset_csvs(input_paths: list, mode: str, out_dir: Path,
                          cfg: DatasetConfig, progress_cb=None) -> dict:
    """
    Full pipeline: load -> classify -> group by (region, sample_type) -> write CSVs.

    Each unique combination of spectral region (LW/CH) and sample_type produces
    one CSV file named:
        <region>_<sample_type>_dataset.csv
    e.g. LW_Plasma_dataset.csv, CH_Lipoprotein_dataset.csv.

    sample_type is read from the HDF5 file (same stem, in out_dir) produced by
    a prior FAIRaman conversion. Files without a matching HDF5 or with an empty
    sample_type field are placed in the 'Unknown' sample_type group.

    Each group is interpolated on its own common grid (intersection of member
    axes), so different sample types can have different wavenumber ranges.

    Parameters
    ----------
    input_paths : list[Path]
        Input spectrum files.
    mode : str
        'wdf' or 'txt'.
    out_dir : Path
        Output directory (also searched for HDF5 files); created if absent.
    cfg : DatasetConfig
        Grid step parameter.
    progress_cb : callable or None
        Optional f(i, total, name) progress callback.

    Returns
    -------
    dict
        {group_key: n_cols} for every group that was successfully written.
        n_cols is the number of wavenumber columns in that CSV.

    Raises
    ------
    ValueError
        If no files at all could be loaded.
    """
    if not input_paths:
        raise ValueError("No input files provided.")

    out_dir.mkdir(parents=True, exist_ok=True)

    groups = _collect_and_classify(input_paths, mode, out_dir, progress_cb)

    if not groups:
        raise ValueError("No files could be loaded successfully.")

    results: dict = {}
    for group_key, records in sorted(groups.items()):
        out_path = out_dir / f"{group_key}_dataset.csv"
        try:
            n = _build_and_write_group(records, cfg.step, out_path)
            results[group_key] = n
        except ValueError as exc:
            print(f"[FAIRaman] Dataset: group '{group_key}' skipped — {exc}")

    return results

def _run_dataset_generation(state: dict, mode_var: tk.StringVar,
                            cfg_vars: dict, progress_var: tk.StringVar,
                            progress_bar: ttk.Progressbar,
                            root: tk.Tk) -> None:
    """
    GUI handler: validate inputs, build DatasetConfig, run the pipeline,
    and report results in a completion dialog.
    """
    mode    = mode_var.get()
    dir_key = "wdf" if mode == "wdf" else "spectra_dir"
    in_dir  = state["paths"].get(dir_key)
    out_dir = state["paths"].get("out")

    if not in_dir or not out_dir:
        messagebox.showerror("Dataset generation",
                             "Please select an input folder and output folder first.")
        return

    in_dir  = Path(in_dir)
    out_dir = Path(out_dir)

    if not in_dir.is_dir():
        messagebox.showerror("Dataset generation",
                             f"Input directory not found:\n{in_dir}")
        return

    if mode == "wdf":
        file_paths = sorted({f for f in in_dir.glob("*") if f.suffix.lower() == ".wdf"})
    else:
        meta_resolved = (state["paths"]["txt"].resolve()
                         if state["paths"].get("txt") else None)
        file_paths = [p for p in in_dir.glob("*.txt")
                      if meta_resolved is None or p.resolve() != meta_resolved]
        file_paths += sorted(in_dir.glob("*.csv"))
        file_paths += sorted(in_dir.glob("*.dat"))

    if not file_paths:
        messagebox.showwarning("Dataset generation",
                               f"No spectrum files found in:\n{in_dir}")
        return

    try:
        cfg = DatasetConfig(step=float(cfg_vars["step"].get()))
    except ValueError as exc:
        messagebox.showerror("Dataset generation",
                             f"Invalid grid step:\n{exc}")
        return

    if cfg.step <= 0:
        messagebox.showerror("Dataset generation",
                             "Grid step must be > 0 cm⁻¹.")
        return

    total = len(file_paths)
    progress_bar["maximum"] = total
    progress_bar["value"]   = 0

    def _progress(i, _total, name):
        progress_var.set(f"Dataset: {i}/{_total} — {name}")
        progress_bar["value"] = i
        root.update_idletasks()

    try:
        progress_var.set("Dataset: starting\u2026")
        root.update_idletasks()
        results = generate_dataset_csvs(
            file_paths, mode, out_dir, cfg, progress_cb=_progress
        )
        progress_var.set("Dataset generation complete.")
        lines = [
            "Dataset generation complete.\n",
            f"Files processed: {total}",
            f"Groups written: {len(results)}\n",
        ]
        for group_key, n_cols in sorted(results.items()):
            lines.append(
                f"\u2705  {group_key}_dataset.csv  \u2014  {n_cols} wavenumber columns"
            )
        if not results:
            lines.append(
                "\u26a0\ufe0f  No groups written. Check console for details.\n"
                "Tip: run the HDF5 conversion first so sample_type can be read."
            )
        lines.append(f"\nOutput folder:\n{out_dir}")
        messagebox.showinfo("Dataset generation", "\n".join(lines))
    except Exception as exc:
        progress_var.set("Dataset generation failed.")
        messagebox.showerror("Dataset generation", f"Error:\n{exc}")
        traceback.print_exc()
