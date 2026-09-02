"""
Renishaw WDF spectrum reader for FAIRaman.

This module reads Raman spectral data, spatial coordinates, and optional
white-light images from Renishaw WDF files.

The ``renishawWiRE`` dependency is optional. ASCII functionality remains
available even when the package is not installed.
"""

from __future__ import annotations

import struct
from io import BytesIO
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from PIL import Image

try:
    from renishawWiRE import WDFReader

    HAS_WDF = True

except ImportError:
    WDFReader = None
    HAS_WDF = False

    print(
        "[FAIRaman] INFO: renishawWiRE is not installed — "
        "WDF mode unavailable.\n"
        "           To enable it, run: pip install renishawWiRE"
    )

# ─────────────────────────────────────────────────────────────────────────────
# FAIRAMAN CANONICAL DATA MODEL
# ─────────────────────────────────────────────────────────────────────────────
# Contratto unico tra QUALSIASI importer (oggi WDF/ASCII; domani RamanSPy per
# Horiba/WiTec/MATLAB) e il writer HDF5/NeXus. Il writer non deve sapere da dove
# vengono i dati: legge solo i campi qui sotto.
#
# Due geometrie spaziali, distinte da `coordinate_mode`:
#   "regular_grid"       cube:    (ny, nx, nw)   x_axis: (nx,)  y_axis: (ny,)
#                        assi indipendenti, combinabili con meshgrid.
#   "point_coordinates"  spectra: (n_points, nw) x: (n_pts,)    y: (n_pts,)
#                        una coordinata reale per spettro; NON usare meshgrid.
#
# Regola di onestà FAIR:
#   coordinate fisiche  → corrette e coerenti con gli spettri (validate);
#   coordinate assenti  → dichiarate come 'synthetic' / 'index'.
#
# CAMPI (None se assente):
#   cube / spectra        np.ndarray   (vedi coordinate_mode)
#   raman_shift           np.ndarray   (nw,)
#   x_axis,y_axis / x,y   np.ndarray   coordinate
#   coordinate_mode       str          "regular_grid" | "point_coordinates"
#   coordinate_source     str          "Renishaw ORGN/map_shape" | "synthetic"...
#   coordinate_units      str          "micrometers" | "index"
#   coordinate_validated  bool         True se coordinate coerenti con spettri
#   reshape_applied       bool         True se il cubo è stato rimodellato
#   reshape_source        str          "map_shape" | "none" | ...
#   geometry_warning      str          "" se nessun problema
#   source_format         str          "wdf" | "txt" | "ramanspy" | ...
#   white_light           np.ndarray   immagine RGB opzionale
#   acquisition_map       np.ndarray   overlay RGB opzionale
# ─────────────────────────────────────────────────────────────────────────────

COORDINATE_MODE_REGULAR = "regular_grid"
COORDINATE_MODE_POINTS  = "point_coordinates"

def _canonical_defaults() -> dict:
    """Campi di provenance coordinate al loro default 'sintetico/non validato'.
    Ogni importer parte da qui e sovrascrive solo ciò che può garantire."""
    return {
        "coordinate_mode":      COORDINATE_MODE_POINTS,
        "coordinate_source":    "synthetic",
        "coordinate_units":     "index",
        "coordinate_validated": False,
        "reshape_applied":      False,
        "reshape_source":       "none",
        "geometry_warning":     "",
    }

def validate_canonical(data: dict) -> None:
    """Verifica minima di coerenza geometrica prima della scrittura su disco.
    Solleva ValueError se spettri e coordinate non descrivono la stessa geometria."""
    mode = data.get("coordinate_mode", COORDINATE_MODE_POINTS)
    rs   = np.atleast_1d(np.asarray(data["raman_shift"]))

    if mode == COORDINATE_MODE_REGULAR:
        cube = np.asarray(data["cube"])
        if cube.ndim != 3:
            raise ValueError(f"regular_grid richiede un cubo 3D, shape {cube.shape}")
        ny, nx, nw = cube.shape
        if len(np.atleast_1d(data["x_axis"])) != nx:
            raise ValueError(f"len(x_axis) != nx ({len(data['x_axis'])} != {nx})")
        if len(np.atleast_1d(data["y_axis"])) != ny:
            raise ValueError(f"len(y_axis) != ny ({len(data['y_axis'])} != {ny})")
        if len(rs) != nw:
            raise ValueError(f"len(raman_shift) != nw ({len(rs)} != {nw})")

    elif mode == COORDINATE_MODE_POINTS:
        spec = np.asarray(data["spectra"])
        if spec.ndim != 2:
            raise ValueError(f"point_coordinates richiede spectra 2D, shape {spec.shape}")
        n_pts, nw = spec.shape
        if len(np.atleast_1d(data["x"])) != n_pts:
            raise ValueError(f"len(x) != n_points ({len(data['x'])} != {n_pts})")
        if len(np.atleast_1d(data["y"])) != n_pts:
            raise ValueError(f"len(y) != n_points ({len(data['y'])} != {n_pts})")
        if len(rs) != nw:
            raise ValueError(f"len(raman_shift) != nw ({len(rs)} != {nw})")
    else:
        raise ValueError(f"coordinate_mode sconosciuto: {mode!r}")

def _extract_white_light_image(reader) -> tuple:
    """
    Extracts the white-light image and its physical-coordinate metadata from
    a WDFReader instance.

    The image coordinate system is converted from a pixel grid to real
    micrometre coordinates using the scan origin and physical dimensions
    stored in the WDF file. This produces calibrated spatial axes.

    Parameters
    ----------
    reader : WDFReader
        Open instance of the Renishaw WiRE `WDFReader`.

    Returns
    -------
    img_arr : numpy.ndarray or None
        White-light image array with shape `(H, W)` or `(H, W, 3)`.
        Returns `None` if no image is available.

    meta : dict or None
        Dictionary containing the physical-coordinate metadata, including
        the origin in micrometres, physical dimensions in micrometres,
        pixel resolution in micrometres per pixel, and precomputed coordinate
        arrays for the x and y axes. Returns `None` if the metadata cannot
        be extracted.
    """
    if not (hasattr(reader, "img") and reader.img is not None):
        return None, None
    try:
        img_file = reader.img
        if hasattr(img_file, "seek"):
            img_file.seek(0)
        img_arr = np.array(Image.open(img_file))

        x0, y0   = reader.img_origins
        w, h     = reader.img_dimensions
        H, W     = img_arr.shape[:2]
        dx       = float(w) / float(W)
        dy       = float(h) / float(H)
        x_coords = (float(x0) + (np.arange(W) + 0.5) * dx).astype(np.float64)
        y_coords = (float(y0) + float(h) - (np.arange(H) + 0.5) * dy).astype(np.float64)

        meta = {
            "x0_um": float(x0), "y0_um": float(y0),
            "width_um": float(w), "height_um": float(h),
            "dx_um_per_px": dx, "dy_um_per_px": dy,
            "origin": "upper", "units": "micrometers",
            "shape_px": [int(H), int(W)],
            "x_coords_um": x_coords,
            "y_coords_um": y_coords,
        }
        return img_arr, meta
    except Exception as exc:
        print(f"[FAIRaman] WARNING: Could not extract white-light image: {exc}")
        return None, None

def _create_acquisition_map(img_arr: np.ndarray, wl_meta: dict,
                             x_axis: np.ndarray, y_axis: np.ndarray
                             ) -> np.ndarray | None:
    """
    Generates an RGB image by overlaying the Raman acquisition grid onto the
    white-light optical micrograph.

    Each acquisition point is displayed using a red marker. The resulting image
    is stored in the HDF5 file under `ENTRY/auxiliary/acquisition_map` and provides
    useful spatial context for interpreting the spectral maps.

    Parameters
    ----------
    img_arr : numpy.ndarray
        White-light image array.

    wl_meta : dict
        Spatial metadata dictionary returned by `_extract_white_light_image`.

    x_axis, y_axis : numpy.ndarray
        Physical coordinates of the Raman acquisition grid, in micrometres.

    Returns
    -------
    numpy.ndarray or None
        RGB image array with shape `(H, W, 3)` and dtype `uint8`, or `None`
        if an error occurs.
    """ 

    if img_arr is None or wl_meta is None:
        return None
    try:
        XX, YY    = np.meshgrid(x_axis, y_axis)
        x_pts     = XX.flatten()
        y_pts     = YY.flatten()

        fig, ax = plt.subplots(figsize=(10, 8))
        ax.imshow(
            img_arr,
            extent=(
                wl_meta["x0_um"],
                wl_meta["x0_um"] + wl_meta["width_um"],
                wl_meta["y0_um"] + wl_meta["height_um"],
                wl_meta["y0_um"],
            ),
            origin="upper",
        )
        ax.scatter(x_pts, y_pts, c="red", s=5, alpha=0.5, marker=".")
        ax.set_title("Raman Acquisition Grid")
        ax.set_xlabel("X (µm)")
        ax.set_ylabel("Y (µm)")

        buf = BytesIO()
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        return np.array(Image.open(buf).convert("RGB"))
    except Exception as exc:
        print(f"[FAIRaman] WARNING: Could not create acquisition map: {exc}")
        return None

def _read_renishaw_geometry(reader) -> dict:
    """
    Extracts the spatial geometry from a `WDFReader`, distinguishing a regular
    grid from a set of scattered acquisition points.

    WiRE populates `xpos` and `ypos` values (ORGN blocks) for every spectrum,
    including spectra from regular maps flattened in row-major order. Therefore,
    the presence of `xpos` and `ypos` alone cannot distinguish between the two
    geometries.

    The determining factor is `map_shape`: when it is available and its product
    matches the number of spectra, the acquisition is treated as a rectangular
    grid.

    Note that WiRE stores `map_shape` as `(nx, ny)`, whereas the spectral array
    has shape `(ny, nx, nw)`. The axis order is therefore reversed.

    Returns
    -------
    dict
        Dictionary containing:

        * `kind` — spatial geometry type: `"grid"`, `"points"`, or `"none"`.
        * `nx`, `ny` — grid dimensions, provided when `kind == "grid"`.
        * `x_axis`, `y_axis` — grid axes in micrometres, derived from the ORGN
        coordinates when available.
        * `x`, `y` — per-spectrum coordinates in micrometres, provided when
        `kind == "points"`.
    """
    try:
        xpos = getattr(reader, "xpos", None)
        ypos = getattr(reader, "ypos", None)
        x = None if xpos is None else np.asarray(xpos, dtype=float).ravel()
        y = None if ypos is None else np.asarray(ypos, dtype=float).ravel()
        n_spec = int(getattr(reader, "count", 0)) or (0 if x is None else x.size)

        ms = getattr(reader, "map_shape", None)
        if ms is not None and len(ms) == 2:
            nx_m, ny_m = int(ms[0]), int(ms[1])
            if nx_m * ny_m == n_spec and nx_m > 1 and ny_m > 1:
                if x is not None and y is not None and x.size == n_spec:
                    x_axis = x[:nx_m]      # prima riga (x veloce)
                    y_axis = y[::nx_m]     # primo elemento di ogni riga (y lento)
                else:
                    x_axis = y_axis = None
                return {"kind": "grid", "nx": nx_m, "ny": ny_m,
                        "x_axis": x_axis, "y_axis": y_axis}

        # Nessuna griglia coerente: coordinate per-punto reali e non degeneri → punti
        if x is not None and y is not None and x.size == y.size == n_spec \
                and not (np.allclose(x, x[0]) and np.allclose(y, y[0])):
            return {"kind": "points", "x": x, "y": y}

        return {"kind": "none"}
    except Exception as exc:
        print(f"[FAIRaman] WARNING _read_renishaw_geometry: {exc}")
        return {"kind": "none"}

def process_wdf(wdf_path: Path) -> dict:
    """
    Imports Renishaw WDF data into the canonical FAIRaman dictionary structure.

    Spatial geometry is assigned according to the following priority, validated
    using real WDF files:

        GRID
            If `map_shape` is consistent with the number of spectra, the data are
            represented as a `regular_grid` with a three-dimensional spectral cube
            and spatial axes in micrometres derived from the real ORGN coordinates.

        POINTS
            If per-spectrum ORGN coordinates are available but the acquisition does
            not form a regular grid, the data are represented as
            `point_coordinates`. Examples include microplastics, morphological
            regions of interest, and manually selected measurement spots.

        NONE
            If no real spatial coordinates are available, synthetic or index-based
            coordinates are used.

    The intended future function name is `import_renishaw_wdf`. The current
    `process_wdf` name is retained for backward compatibility with the conversion
    pipeline.
    """
    if not HAS_WDF:
        raise RuntimeError(
            "renishawWiRE is not installed. Install it with: pip install renishawWiRE"
        )

    reader      = WDFReader(str(wdf_path))
    spectra     = np.asarray(reader.spectra)
    raman_shift = np.asarray(reader.xdata)

    n_spectra = int(getattr(reader, "count", 0)) or (
        1 if spectra.ndim == 1 else
        spectra.shape[0] if spectra.ndim == 2 else
        spectra.shape[0] * spectra.shape[1]
    )

    geom = _read_renishaw_geometry(reader)

    out = _canonical_defaults()
    out.update({
        "cube":             None,
        "spectra":          None,
        "raman_shift":      raman_shift,
        "x_axis":           None,
        "y_axis":           None,
        "x":                None,
        "y":                None,
        "white_light":      None,
        "white_light_meta": None,
        "acquisition_map":  None,
        "filename":         wdf_path.name,
        "wdf_path":         wdf_path,
        "source_format":    "wdf",
    })

    # ── GRID: mappa rettangolare regolare (priorità) ─────────────────────────
    if geom["kind"] == "grid":
        ny, nx = geom["ny"], geom["nx"]
        if spectra.ndim == 3 and spectra.shape[:2] == (ny, nx):
            cube, reshaped = spectra, False
        else:
            cube, reshaped = spectra.reshape(ny, nx, spectra.shape[-1]), True
        if geom["x_axis"] is not None:
            x_axis, y_axis = geom["x_axis"], geom["y_axis"]
            units, src, valid = "micrometers", "Renishaw ORGN/map_shape", True
        else:
            x_axis = np.arange(nx, dtype=float)
            y_axis = np.arange(ny, dtype=float)
            units, src, valid = "index", "synthetic", False
        out.update({
            "cube":                 cube,
            "x_axis":               x_axis,
            "y_axis":               y_axis,
            "coordinate_mode":      COORDINATE_MODE_REGULAR,
            "coordinate_source":    src,
            "coordinate_units":     units,
            "coordinate_validated": valid,
            "reshape_applied":      reshaped,
            "reshape_source":       "map_shape" if reshaped else "none",
        })

    # ── POINTS: coordinate per-punto reali, geometria non a griglia ──────────
    elif geom["kind"] == "points":
        out.update({
            "spectra":              spectra.reshape(n_spectra, -1),
            "x":                    geom["x"],
            "y":                    geom["y"],
            "coordinate_mode":      COORDINATE_MODE_POINTS,
            "coordinate_source":    "Renishaw ORGN (per-point)",
            "coordinate_units":     "micrometers",
            "coordinate_validated": True,
        })

    # ── NONE: nessuna coordinata reale → synthetic / index ───────────────────
    else:
        if n_spectra == 1:
            xs, ys = np.array([0.0]), np.array([0.0])
        else:
            xs, ys = np.arange(n_spectra, dtype=float), np.zeros(n_spectra)
        out.update({
            "spectra":              spectra.reshape(n_spectra, -1),
            "x":                    xs,
            "y":                    ys,
            "coordinate_mode":      COORDINATE_MODE_POINTS,
            "coordinate_source":    "synthetic",
            "coordinate_units":     "index",
            "coordinate_validated": False,
        })

    # ── White-light & acquisition map (solo geometria regolare) ──────────────
    wl_img, wl_meta = _extract_white_light_image(reader)
    out["white_light"]      = wl_img
    out["white_light_meta"] = wl_meta
    if wl_img is not None and out["coordinate_mode"] == COORDINATE_MODE_REGULAR:
        out["acquisition_map"] = _create_acquisition_map(
            wl_img, wl_meta, out["x_axis"], out["y_axis"]
        )

    out["instrument"] = {
        "laser_wavelength": float(getattr(reader, "laser_length", 0.0)),
        "x_start": float(out["x_axis"][0]) if out["x_axis"] is not None
                   else (float(out["x"][0]) if out["x"] is not None else 0.0),
        "y_start": float(out["y_axis"][0]) if out["y_axis"] is not None
                   else (float(out["y"][0]) if out["y"] is not None else 0.0),
        "x_step": 0.0, "y_step": 0.0,
    }
    return out

def _reshape_spectra(
    spectra: np.ndarray,
    wmap: dict,
) -> np.ndarray:
    """
    Convert WDF spectra into the standard ``(y, x, Raman shift)`` cube.

    Parameters
    ----------
    spectra
        Raw spectra returned by ``WDFReader.spectra``.
    wmap
        Spatial map metadata returned by :func:`_read_wmap_direct`.

    Returns
    -------
    numpy.ndarray
        Three-dimensional spectral cube.

    Raises
    ------
    ValueError
        If the input spectra have an unsupported shape.
    """
    spectra = np.asarray(spectra)

    if spectra.size == 0:
        raise ValueError("The WDF file contains no spectral data.")

    if spectra.ndim == 1:
        return spectra.reshape(1, 1, -1)

    if spectra.ndim == 2:
        number_spectra, number_wavenumbers = spectra.shape

        number_x = int(wmap.get("num_x", 0))
        number_y = int(wmap.get("num_y", 0))

        expected_spectra = number_x * number_y

        if (
            number_x > 0
            and number_y > 0
            and expected_spectra == number_spectra
        ):
            return spectra.reshape(
                number_y,
                number_x,
                number_wavenumbers,
            )

        if number_spectra == 1:
            return spectra.reshape(
                1,
                1,
                number_wavenumbers,
            )

        # A line acquisition or an acquisition whose spatial map
        # information is unavailable.
        return spectra.reshape(
            number_spectra,
            1,
            number_wavenumbers,
        )

    if spectra.ndim == 3:
        return spectra

    raise ValueError(
        "Unsupported WDF spectral array shape: "
        f"{spectra.shape}. Expected one, two, or three dimensions."
    )
