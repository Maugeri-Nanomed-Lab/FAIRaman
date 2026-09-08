"""
fairaman/validation.py

Post-write sanity check: verifies that the data written into an HDF5/NeXus
file is numerically identical to the in-memory spectral data that was
converted, before the user is told the conversion succeeded.
"""

from pathlib import Path

import h5py
import numpy as np

from fairaman.constant import COORDINATE_MODE_REGULAR, COORDINATE_MODE_POINTS


def verify_conversion(data: dict, h5_path: Path,
                       rtol: float = 1e-6, atol: float = 1e-9) -> tuple[bool, list[str]]:
    """
    Compare the spectral data just written to `h5_path` against the original
    in-memory canonical dictionary (`data`, as returned by `process_wdf` /
    `process_txt_spectrum`).

    Returns
    -------
    (ok, issues) : tuple[bool, list[str]]
        `ok` is True only if every check passes. `issues` lists every
        mismatch found, for reporting to the user.
    """
    issues: list[str] = []

    try:
        with h5py.File(h5_path, "r") as f:
            entry = f["ENTRY"]
            data_grp = entry["data"]

            # ── Raman shift axis ──────────────────────────────────────────
            rs_h5 = np.asarray(data_grp["raman_shift"][()], dtype=np.float64)
            rs_orig = np.asarray(data["raman_shift"], dtype=np.float64)
            if rs_h5.shape != rs_orig.shape:
                issues.append(
                    f"raman_shift shape mismatch: h5={rs_h5.shape} orig={rs_orig.shape}"
                )
            elif not np.allclose(rs_h5, rs_orig, rtol=rtol, atol=atol, equal_nan=True):
                issues.append("raman_shift values differ between HDF5 and original data")

            # ── Geometry mode ─────────────────────────────────────────────
            mode = data.get("coordinate_mode", COORDINATE_MODE_POINTS)
            h5_mode = data_grp.attrs.get("coordinate_mode")
            if h5_mode != mode:
                issues.append(f"coordinate_mode mismatch: h5='{h5_mode}' orig='{mode}'")

            if mode == COORDINATE_MODE_REGULAR:
                cube_orig = np.asarray(data["cube"], dtype=np.float64)
                cube_h5 = np.asarray(data_grp["intensity"][()], dtype=np.float64)
                if cube_h5.shape != cube_orig.shape:
                    issues.append(
                        f"intensity cube shape mismatch: h5={cube_h5.shape} orig={cube_orig.shape}"
                    )
                elif not np.allclose(cube_h5, cube_orig, rtol=rtol, atol=atol, equal_nan=True):
                    issues.append("intensity cube values differ between HDF5 and original data")

                x_h5 = np.asarray(data_grp["x"][()], dtype=np.float64)
                y_h5 = np.asarray(data_grp["y"][()], dtype=np.float64)
                x_orig = np.asarray(data["x_axis"], dtype=np.float64)
                y_orig = np.asarray(data["y_axis"], dtype=np.float64)
                if x_h5.shape != x_orig.shape or not np.allclose(x_h5, x_orig, rtol=rtol, atol=atol):
                    issues.append("x_axis mismatch between HDF5 and original data")
                if y_h5.shape != y_orig.shape or not np.allclose(y_h5, y_orig, rtol=rtol, atol=atol):
                    issues.append("y_axis mismatch between HDF5 and original data")

                expected_count = int(cube_orig.shape[0] * cube_orig.shape[1])

            else:  # point_coordinates
                spec_orig = np.asarray(data["spectra"], dtype=np.float64)
                spec_h5 = np.asarray(data_grp["intensity"][()], dtype=np.float64)
                if spec_h5.shape != spec_orig.shape:
                    issues.append(
                        f"spectra shape mismatch: h5={spec_h5.shape} orig={spec_orig.shape}"
                    )
                elif not np.allclose(spec_h5, spec_orig, rtol=rtol, atol=atol, equal_nan=True):
                    issues.append("spectra values differ between HDF5 and original data")

                x_h5 = np.asarray(data_grp["x"][()], dtype=np.float64)
                y_h5 = np.asarray(data_grp["y"][()], dtype=np.float64)
                x_orig = np.asarray(data["x"], dtype=np.float64)
                y_orig = np.asarray(data["y"], dtype=np.float64)
                if x_h5.shape != x_orig.shape or not np.allclose(x_h5, x_orig, rtol=rtol, atol=atol):
                    issues.append("x coordinates mismatch between HDF5 and original data")
                if y_h5.shape != y_orig.shape or not np.allclose(y_h5, y_orig, rtol=rtol, atol=atol):
                    issues.append("y coordinates mismatch between HDF5 and original data")

                expected_count = int(spec_orig.shape[0])

            h5_count = int(data_grp.attrs.get("spectral_count", -1))
            if h5_count != expected_count:
                issues.append(
                    f"spectral_count mismatch: h5={h5_count} expected={expected_count}"
                )

            # ── Auxiliary images (WDF only) ─────────────────────────────────
            if data.get("white_light") is not None:
                if "auxiliary" not in entry or "white_light" not in entry["auxiliary"]:
                    issues.append("white_light image missing from HDF5 output")
                else:
                    wl_h5 = np.asarray(entry["auxiliary"]["white_light"]["image"][()])
                    wl_orig = np.asarray(data["white_light"])
                    if wl_h5.shape != wl_orig.shape:
                        issues.append(
                            f"white_light image shape mismatch: h5={wl_h5.shape} orig={wl_orig.shape}"
                        )
                    elif not np.array_equal(wl_h5, wl_orig):
                        issues.append("white_light image pixel data differs from original")

    except Exception as exc:
        issues.append(f"Validation could not be completed: {exc}")

    return (len(issues) == 0, issues)