import json
from pathlib import Path

import h5py
import numpy as np
import pandas as pd

from fairaman.schema import NEXUS_SCHEMA
from fairaman.metadata import NumpyEncoder
from fairaman.constant import COORDINATE_MODE_REGULAR, COORDINATE_MODE_POINTS
from fairaman.readers.wdf_reader import validate_canonical
from fairaman import FAIRAMAN_VERSION

def _write_dataset(parent: h5py.Group, name: str, value) -> None:

    """
    Creates an HDF5 dataset using the appropriate storage type.

    Numeric scalars are stored as native numeric datasets.
    NumPy arrays are stored using gzip compression (level 4) with
    automatic chunking.

    All other values are converted to strings.
    Pandas NA and NaT values are mapped to empty strings to prevent
    serialization errors when the data contains missing values.

    Parameters
    ----------
    parent : h5py.Group
        Parent HDF5 group in which the dataset will be created.

    name : str
        Name of the dataset.

    value
        Value to be written to the dataset.
    """

    # Treat pandas NA/NaT come empty string
    try:
        if pd.isna(value):
            parent.create_dataset(name, data="", dtype=h5py.string_dtype())
            return
    except (TypeError, ValueError):
        pass

    if isinstance(value, (int, float, np.number)):
        parent.create_dataset(name, data=value)
    elif isinstance(value, np.ndarray):
        parent.create_dataset(name, data=value, compression="gzip", chunks=True)
    else:
        parent.create_dataset(name, data=str(value))

def _write_nexus_structure(h5grp: h5py.Group, schema: dict, data_dict: dict,
                           path_prefix: str = "", ensure_complete: bool = True) -> None:
    """
    Recursively writes the `NEXUS_SCHEMA` hierarchy to an HDF5 file.

    Each schema entry is created as an HDF5 group with the appropriate
    `NX_class` attribute.

    When `ensure_complete` is `True`, every field defined in the schema is
    written to the file, even when no corresponding value is available in
    `data_dict`. Missing values are stored as empty strings.

    This ensures structural consistency across all FAIRaman output files and
    allows them to be processed in batches without accounting for differences
    in the schema structure of individual files.

    Parameters
    ----------
    h5grp : h5py.Group
        HDF5 group into which the hierarchy is written, typically the file root.

    schema : dict
        Dictionary containing the full schema or a schema subsection, following
        the `NEXUS_SCHEMA` convention.

    data_dict : dict
        Flat mapping from dot-separated HDF5 paths to their corresponding values.

    path_prefix : str
        Dot-separated path prefix accumulated during recursive traversal.

    ensure_complete : bool
        If `True`, writes an empty dataset for every schema field not present in
        `data_dict`. This is recommended for production use.
    """
    for key, config in schema.items():
        current_path = f"{path_prefix}.{key}" if path_prefix else key

        if isinstance(config, dict) and "NX_class" in config:
            grp = h5grp.create_group(key)
            grp.attrs["NX_class"] = config["NX_class"]
            if "definition" in config:
                grp.attrs["definition"] = config["definition"]

            for field in config.get("fields", []):
                field_path = f"{current_path}.{field}"
                val = data_dict.get(field_path)
                if ensure_complete:
                    if val is not None and val != "":
                        _write_dataset(grp, field, val)
                    else:
                        grp.create_dataset(field, data="", dtype=h5py.string_dtype())
                elif val is not None and val != "":
                    _write_dataset(grp, field, val)

            if "subgroups" in config:
                _write_nexus_structure(grp, config["subgroups"], data_dict,
                                       current_path, ensure_complete)

        elif isinstance(config, dict) and "fields" in config:
            grp = h5grp.create_group(key)
            if "NX_class" in config:
                grp.attrs["NX_class"] = config["NX_class"]
            for field in config["fields"]:
                field_path = f"{current_path}.{field}"
                val = data_dict.get(field_path)
                if ensure_complete:
                    if val is not None and val != "":
                        _write_dataset(grp, field, val)
                    else:
                        grp.create_dataset(field, data="", dtype=h5py.string_dtype())
                elif val is not None and val != "":
                    _write_dataset(grp, field, val)

def write_hdf5_nexus(out_path: Path, data: dict, metadata: dict) -> None:

    """
   Writes an HDF5/NeXus FAIRaman file from spectral data and metadata.

    The output file contains three root-level groups:

    * ``PROJECT/`` — Investigation-level metadata (FAIR provenance).
    * ``SAMPLE/``  — Sample-level metadata (MIABIS-compliant).
    * ``ENTRY/``   — Experimental metadata and spectral data (NXraman).

    Within ``ENTRY/``, the spectral intensity cube is stored in
    ``ENTRY/data/intensity`` as a three-dimensional array with shape
    (ny, nx, n_wavenumbers), along with additional datasets for the
    wavenumber axis and spatial axes.

    For WDF-derived data, white-light images and acquisition-map images
    are stored in ``ENTRY/auxiliary/``.

    Root-level attributes record the source format and FAIRaman version,
    providing information for tracking data provenance.

    Parameters
    ----------
    out_path : Path
        Destination path for the output HDF5 file.

    data : dict
        Dictionary containing spectral data returned by ``process_wdf``
        or ``process_txt_spectrum``.

    metadata : dict
        Must contain the ``flat_data`` key, which maps dot-separated
        HDF5 paths to metadata values.

        May also contain the optional ``excel_row`` and ``txt_meta``
        keys for debugging purposes.
    """

    flat_data = metadata["flat_data"].copy()
    
    # ── Auto-populate fields derived from the raw data ────────────────────────
    # Laser wavelength: extracted from WDF header; fall back to empty string
    # (l'utente deve darlo tramite il metadata TXT per input ASCII).
    lw_path = "ENTRY.instrument.laser.wavelength"
    if not flat_data.get(lw_path):
        lw = data["instrument"]["laser_wavelength"]
        if lw:
            flat_data[lw_path] = lw

    # Wavelength units default to nanometres (SI convention for visible/NIR)
    wu_path = "ENTRY.instrument.laser.wavelength_units"
    if not flat_data.get(wu_path):
        flat_data[wu_path] = "nm"

    # Spectral count: numero totale di spettri (geometry-aware)
    sc_path = "ENTRY.data.spectral_count"
    if not flat_data.get(sc_path):
        if data.get("coordinate_mode") == COORDINATE_MODE_REGULAR and data.get("cube") is not None:
            flat_data[sc_path] = int(data["cube"].shape[0] * data["cube"].shape[1])
        elif data.get("spectra") is not None:
            flat_data[sc_path] = int(np.asarray(data["spectra"]).shape[0])

    # Title defaults to the source filename for traceability
    title_path = "ENTRY.title"
    if not flat_data.get(title_path):
        flat_data[title_path] = data["filename"]

    # start_time: auto-populated from WDF file creation date if not already set
    # Il file WDF viene creato durante l'acquisizione, quindi la sua data di
    # modifica corrisponde alla data di acquisizione dello spettro
    st_path = "ENTRY.start_time"
    if not flat_data.get(st_path) and data.get("source_format") == "wdf":
        try:
            import datetime as _dt, os as _os
            mtime = _os.path.getmtime(data["wdf_path"])
            flat_data[st_path] = _dt.datetime.fromtimestamp(mtime).strftime("%Y-%m-%dT%H:%M:%S")
        except Exception:
            pass
    metadata["flat_data"] = flat_data
 
    with h5py.File(out_path, "w") as f:

        # 1. Write the complete metadata hierarchy (PROJECT, SAMPLE, ENTRY)
        _write_nexus_structure(f, NEXUS_SCHEMA, flat_data, ensure_complete=True)

        entry = f["ENTRY"]
        if "NX_class" not in entry.attrs:
            entry.attrs["NX_class"] = "NXentry"
            entry.attrs["definition"] = "NXraman"
        
        # 2. Validate canonical geometry, then write ENTRY/data (NXdata)
        validate_canonical(data)
        mode = data.get("coordinate_mode", COORDINATE_MODE_POINTS)

        data_grp = entry.create_group("data")
        data_grp.attrs["NX_class"] = "NXdata"
        data_grp.create_dataset("raman_shift", data=data["raman_shift"])

        # Provenance coordinate (comune a entrambe le geometrie)
        for k in ("coordinate_mode", "coordinate_source", "coordinate_units",
                  "coordinate_validated", "reshape_applied", "reshape_source",
                  "geometry_warning"):
            if data.get(k) is not None:
                data_grp.attrs[k] = data[k]

        if mode == COORDINATE_MODE_REGULAR:
            cube = data["cube"]
            ny, nx, n_wn = cube.shape
            data_grp.attrs["signal"] = "intensity"
            data_grp.attrs["axes"]   = ["y", "x", "raman_shift"]
            data_grp.create_dataset(
                "intensity", data=cube, compression="gzip", chunks=True
            )
            data_grp.create_dataset("x", data=data["x_axis"])
            data_grp.create_dataset("y", data=data["y_axis"])
            n_points = int(ny * nx)
            data_grp.attrs["nx"]            = int(nx)
            data_grp.attrs["ny"]            = int(ny)
            data_grp.attrs["n_wavenumbers"] = int(n_wn)
        else:  # point_coordinates
            spec = np.asarray(data["spectra"])
            n_points, n_wn = spec.shape
            data_grp.attrs["signal"] = "intensity"
            data_grp.attrs["axes"]   = ["point_id", "raman_shift"]
            data_grp.create_dataset(
                "intensity", data=spec, compression="gzip", chunks=True
            )
            data_grp.create_dataset("x", data=np.asarray(data["x"]))
            data_grp.create_dataset("y", data=np.asarray(data["y"]))
            data_grp.create_dataset("point_id", data=np.arange(n_points))
            data_grp.attrs["n_points"]      = int(n_points)
            data_grp.attrs["n_wavenumbers"] = int(n_wn)

        data_grp.attrs["spectral_count"] = int(n_points)

        # 3. Write auxiliary images (white-light and acquisition map; WDF only)
        if data["white_light"] is not None or data["acquisition_map"] is not None:
            aux = entry.create_group("auxiliary")
            aux.attrs["NX_class"] = "NXcollection"

            if data["white_light"] is not None:
                wl_grp = aux.create_group("white_light")
                wl_grp.attrs["NX_class"] = "NXdata"
                wl_grp.attrs["signal"]   = "image"

                img_ds = wl_grp.create_dataset(
                    "image", data=data["white_light"], compression="gzip"
                )
                img_ds.attrs["CLASS"]          = "IMAGE"
                img_ds.attrs["IMAGE_VERSION"]  = "1.2"
                img_ds.attrs["IMAGE_SUBCLASS"] = (
                    "IMAGE_TRUECOLOR"
                    if data["white_light"].ndim == 3
                    else "IMAGE_GRAYSCALE"
                )
                if data["white_light_meta"]:
                    wl_meta = data["white_light_meta"]
                    wl_grp.create_dataset("x", data=wl_meta["x_coords_um"])
                    wl_grp.create_dataset("y", data=wl_meta["y_coords_um"])
                    for k, v in wl_meta.items():
                        if k not in ("x_coords_um", "y_coords_um"):
                            img_ds.attrs[k] = v

            if data["acquisition_map"] is not None:
                map_grp = aux.create_group("acquisition_map")
                map_grp.attrs["NX_class"] = "NXdata"
                map_grp.attrs["signal"]   = "image"
                map_ds = map_grp.create_dataset(
                    "image", data=data["acquisition_map"], compression="gzip"
                )
                map_ds.attrs["CLASS"]          = "IMAGE"
                map_ds.attrs["IMAGE_VERSION"]  = "1.2"
                map_ds.attrs["IMAGE_SUBCLASS"] = "IMAGE_TRUECOLOR"

        # Root-level provenance attributes
        f.attrs["source_format"]    = data.get("source_format", "unknown")
        f.create_dataset("version FAIRaman", data=FAIRAMAN_VERSION)
     
def export_csv(data: dict, out_path: Path) -> None:

    """
    Exports spectral data to a flat CSV file based on coordinate_mode.

    regular_grid       → x_um | y_um | wn_1 ... wn_n
                        (using meshgrid)

    point_coordinates  → point_id | x | y | wn_1 ... wn_n
                        (point-by-point)
    """

    mode = data.get("coordinate_mode", COORDINATE_MODE_POINTS)
    rs_cols = [f"{w:.4f}" for w in np.asarray(data["raman_shift"])]

    if mode == COORDINATE_MODE_REGULAR:
        ny, nx, n_pts = data["cube"].shape
        XX, YY = np.meshgrid(data["x_axis"], data["y_axis"])
        flat = np.column_stack([
            XX.flatten(), YY.flatten(),
            data["cube"].reshape(ny * nx, n_pts),
        ])
        columns = ["x_um", "y_um"] + rs_cols
    else:
        spec = np.asarray(data["spectra"])
        n_points = spec.shape[0]
        flat = np.column_stack([
            np.arange(n_points), np.asarray(data["x"]), np.asarray(data["y"]), spec,
        ])
        columns = ["point_id", "x", "y"] + rs_cols

    pd.DataFrame(flat, columns=columns).to_csv(out_path, index=False)

def export_json(metadata: dict, out_path: Path) -> None:
    """
    Exports a JSON sidecar file containing only the mapped metadata (flat_data).

    The raw sections (excel_row, txt_meta) are excluded because they are
    redundant: flat_data already contains all metadata values, correctly
    indexed by the HDF5 paths defined in the NXraman/MIABIS schema.

    Parameters
    ----------
    metadata : dict
        Metadata dictionary generated during the conversion pipeline.
        Must contain the 'flat_data' key.

    out_path : Path
        Destination path for the output JSON file.
    """
    flat = metadata.get("flat_data", {})
    flat_serializable = {
        k: (v.tolist() if isinstance(v, np.ndarray) else v)
        for k, v in flat.items()
    }
    output: dict = flat_serializable
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2, ensure_ascii=False, cls=NumpyEncoder)
