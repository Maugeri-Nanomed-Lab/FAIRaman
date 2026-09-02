import json
import os
from datetime import datetime
from pathlib import Path

import h5py
import numpy as np
import pandas as pd

from fairaman.schema import NEXUS_SCHEMA
from fairaman.metadata import NumpyEncoder
from fairaman.constant import COORDINATE_MODE_REGULAR, COORDINATE_MODE_POINTS, FAIRAMAN_VERSION
from fairaman.readers.wdf_reader import validate_canonical


def _write_dataset(parent: h5py.Group, name: str, value) -> None:
    """
    Crea un dataset HDF5 con il tipo di memorizzazione appropriato

    gli scalari numerici vengono salvati come dataset numerici nativi
    gli array NumPy vengono salvati come comprensione gzip (livello 4) e chuking automatico
    tutti gli altri valori vengono convertiti in stringhe 
    i valori Pandas NA e NaT vengono mappati su stringhe vuote per evitare errori di serializzazione
    quando i dati contengono valori mancanti

    Parametri
    ----------
    parent : h5py.Group
        Parent HDF5 group in cui creare il dataset 
    name : str
        Dataset name
    value
        Valore da scrivere
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
    Scrive un file HDF5/NeXus FAIRaman a partire da dati spettrali e matadati

    il file di output contiene tre gruppi a livello radice:

    * ``PROJECT/`` — metadati a livello di indagien (FAIR provenance)
    * ``SAMPLE/``  — metadati a livello di campione (MIABIS-compliant)
    * ``ENTRY/``   — metadati sperimentali e dati spettrali (NXraman)

    all'interno di ``ENTRY/``, il cubo di intensità spettrale viene memorizzato in
    ``ENTRY/data/intensity`` come array tridimensinale di shape
    (ny, nx, n_wavenumbers), con dataset aggiuntivi per l'asse dei numeri d'onda
    e gli assi spaziali. 
    per dati derivati da WDF, immagini a white-light e
    acquisition-map images sono salvate in ``ENTRY/auxiliary/``.

    gli attributi a livello radice registrano il formato di origine e la versione di FAIRaman 
    utili per tracciare la provenienza dei dati

    Parametri
    ----------
    out_path : Path
        Percorso di destinazione per il file HDF5 di output
    data : dict
        Dizionario di dati spettrali restituito da ``process_wdf`` o
        ``process_txt_spectrum``.
    metadata : dict
        Deve contenere la chiave ``flat_data`` che mappa percorsi HDF5 separati da punti
        ai valori dei metadati
        può contenere anceh le chiavi ``excel_row`` e ``txt_meta`` a scopo di debug
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
        data_grp.create_dataset("spectral_count", data=int(n_points))

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
        f.attrs["fairaman_version"] = FAIRAMAN_VERSION
        f.create_dataset("version FAIRaman", data=FAIRAMAN_VERSION)
     
def export_csv(data: dict, out_path: Path) -> None:
    """
    Esporta i dati spettrali in CSV flat, in funzione di coordinate_mode.

    regular_grid       → x_um | y_um | wn_1 ... wn_n        (via meshgrid)
    point_coordinates  → point_id | x | y | wn_1 ... wn_n   (punto-per-punto)
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
    Esporta un file JSON sidecar con i soli metadati mappati (flat_data).

    Le sezioni raw (excel_row, txt_meta) vengono escluse perché ridondanti:
    flat_data contiene già tutti i valori, correttamente indicizzati
    sui percorsi HDF5 dello schema NXraman/MIABIS.

    Parametri
    ----------
    metadata : dict
        Dizionario dei metadati generato durante la pipeline di conversione.
        Deve contenere la chiave 'flat_data'.
    out_path : Path
        Destinazione del file JSON.
    """
    flat = metadata.get("flat_data", {})
    flat_serializable = {
        k: (v.tolist() if isinstance(v, np.ndarray) else v)
        for k, v in flat.items()
    }
    output: dict = flat_serializable
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2, ensure_ascii=False, cls=NumpyEncoder)
