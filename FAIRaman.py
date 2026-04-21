"""
FAIRaman: Generatore di HDF5 in linea con MIABIS

FAIRaman converte dati spettrali Raman grezzi (formato WDF o ASCII)
e li converte in file HDF5/NeXus autodescrittivi, che includono
sia metadati dello strumento sia informazioni sul campione biologico
conformi allo standard MIABIS e alle ontologie biomediche (UBERON, ICD-10) 

Logica progettuale
----------------
Gli strumenti FAIR esistenti per la spettroscopia Raman (es. ramanchada2)
si concentrano sullo stuemento:
descrivono perfettamente l'hardware usato, ma non rappresentano 
il campione biologico dello studio 
Nella ricerca clinica e traslazionare, invece, il campione;
la sua origine tissutale; stato patologico; caratteristiche del donatore; etc etc
sono parametri di netta competenza di analisi, centrali e necessarie
specie per entrare in conformità con le nuove linee guida europee delle biobanche 

FAIRaman struttura quindi i metadati su tre livelli complementari:

  * Indagine  — informazioni su progetto, data governance, keywords
  * Campione  — dati del donatore, diagnosi (ICD-10), sito anatomico (UBERON), 
                condizioni di biobanca (confrome a MIABIS)
  * Misura    — parametri di acquisizione, configurazione del laser, 
                optical system (conforme a NXraman/NXinstrument)

Questa gerarchia a tre livelli permette di unire dataset provenienti
da diversi stumenti e step di acquisizione di informazioni
fondamentale per studi multi-centro di machine learning su biomarcatori Raman

Formati di Input supportati per spettri
-----------------------
* Renishaw WDF (.wdf)  — full spectral cube + white-light image
* ASCII two-column     — wavenumber (cm⁻¹) | intensity; tab/space/CSV/DAT

Formati di output
--------------
* HDF5/NeXus (.h5)     — output FAIR principale, allineato a NXraman
* JSON                 — metadati leggibili dall'uomo
* CSV                  — per matrici spettrali

Standards e ontologie
------------------------
* NeXus / NXraman     (https://manual.nexusformat.org)
* MIABIS v3           (https://github.com/BBMRI-ERIC/miabis)
* UBERON ontology     (https://www.ebi.ac.uk/ols/ontologies/uberon)
* ICD-10              (https://icd.who.int)
* FAIR principles     (Wilkinson et al., Sci. Data 2016)

Dependencies
------------
Required : numpy, pandas, h5py, Pillow, matplotlib
Optional : renishawWiRE  (WDF mode only; pip install renishawWiRE)

Autore
-------
Davide Piccapietra

Licenza
-------
MIT License — see LICENSE file for details

References
----------
Wilkinson, M.D. et al. (2016) The FAIR Guiding Principles for scientific
data management and stewardship. Sci. Data 3, 160018

Schober, P. & Vetter, T.R. (2019) MIABIS: Minimum Information About
BIobank data Sharing. Biopreservation and Biobanking
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

# ─────────────────────────────────────────────────────────────────────────────
# NEXUS SCHEMA
# ─────────────────────────────────────────────────────────────────────────────
# lo Schema definisce la gerarchia dei gruppi e dataset HDF5
# e le classi base Nexus
# segue la definizione dell'applicazione NXraman ed è arricchito
# con un gruppo SAMPLE che registra la provenienza biomedica del campione 
# su tre livelli:
# SAMPLE_INFO (proprietà campione), 
# SAMPLE_DONOR (dati del donatore), 
# SAMPLE_EVENT (dettagli sull'acquisizione del campione)
#
# Tutti i campi sono sempre descritti nel file output, anche se vuoti, 
# di modo che ogni FAIRaman file abbia la stessa struttura 
# ─────────────────────────────────────────────────────────────────────────────

NEXUS_SCHEMA = {
    "PROJECT": {
        "NX_class": "NXcollection",
        "fields": [
            "project_name", "project_id", "funding", "author", "author_id",
            "data_license", "accessibility", "keywords"
        ]
    },
    "SAMPLE": {
        "NX_class": "NXsample",
        "fields": ["sample_id"],
        "subgroups": {
            "SAMPLE_INFO": {
                "fields": [
                    "provenance", "sample_type", "detailed_sample_type", "sample_source",
                    "anatomical_site", "anatomical_site_code", "anatomical_ontology",
                    "storage_temperature", "processing_method",
                    "sample_creation_date", "notes"
                ]
            },
            "SAMPLE_DONOR": {
                "fields": [
                    "donor_id", "sex", "age", "diagnosis_code",
                    "diagnosis_ontology", "diagnosis_notes"
                ]
            },
            "SAMPLE_EVENT": {
                "fields": [
                    "date", "event_description"
                ]
            }
        }
    },
    "ENTRY": {
        "NX_class": "NXentry",
        "definition": "NXraman",
        "fields": ["title", "experiment_type", "run_type", "start_time", "data_type"],
        "subgroups": {
            "measurement": {
                "NX_class": "NXcollection",
                "fields": [
                    "exposure_time", "exposure_time_units",
                    "substrate", "accumulation_count"
                ]
            },
            "instrument": {
                "NX_class": "NXinstrument",
                "fields": ["name"],
                "subgroups": {
                    "laser": {
                        "NX_class": "NXsource",
                        "fields": ["wavelength", "wavelength_units", "filter"]
                    },
                    "optical_system": {
                        "NX_class": "NXoptics",
                        "fields": ["lens"]
                    }
                }
            }
        }
    }
}


def flatten_schema(schema: dict, prefix: str = "") -> list[str]:
    """
    Scansione di NEXUS_SCHEMA e restituisce una lista piatta
    dei percorsi HDF5 (es 'SAMPLE.SAMPLE_DONOR.diagnosis_code')

    Mi serve per popolare il menu a tendina nei campi della mappatura
    """
    paths = []
    for k, v in schema.items():
        if isinstance(v, dict):
            if "fields" in v:
                for field in v["fields"]:
                    paths.append(f"{prefix}.{k}.{field}" if prefix else f"{k}.{field}")
            if "subgroups" in v:
                paths.extend(
                    flatten_schema(v["subgroups"], f"{prefix}.{k}" if prefix else k)
                )
    return paths

HDF5_FIELDS = ["Do not map"] + flatten_schema(NEXUS_SCHEMA)

# ─────────────────────────────────────────────────────────────────────────────
# UTILITY CLASSES AND FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

class NumpyEncoder(json.JSONEncoder):
    """
    encoder JSON che serializza tipi scalari e array di NumPy 

    Gli integers e i float di NumPy vengono convertiti a tipi nativi di Python; 
    Gli array a liste. Necessario per metadati con valori NumPy letti da WDF o Excel
    """

    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)


def parse_txt_metadata(path: Path) -> dict:
    """
    Analizza un file di metadati in txt e lo trasforma in un key–value dictionary

    Il formato previsto è ``key: value`` per riga
    le righe con ``#`` e quelle vuote vengono ignorate

    Parametri
    ----------
    path : Path
        Percorso del file TXT contenente i metadati

    Returns
    -------
    dict
        Dizionario che associa i nomi dei campi ai loro valori come stringhe

    Note
    -----
    Anche chiavi che iniziano con ``#`` dopo aver rimosso spazi iniziali
    vengono scartate; 
    questo previene che campi commentati (es ``# laser_wavelength: 785``) 
    vengano caricati per errore
    """
    meta: dict = {}
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if ":" in stripped:
                key, value = stripped.split(":", 1)
                key = key.strip()
                value = value.strip()
                if key and not key.startswith("#"):
                    meta[key] = value
    return meta


# ─────────────────────────────────────────────────────────────────────────────
# WDF PROCESSING (requires renishawWiRE)
# ─────────────────────────────────────────────────────────────────────────────

def _extract_white_light_image(reader) -> tuple:
    """
    Estrae white-light e i metadati delle coordinate fisiche da WDFRreader
    il sistema di coordinate dell'immagine vieni convertito dalla griglia di pixel
    a micrometri reali, usando origine e dimensione della scansione
    memorizzati nel file WDF, in questo modo si ottengono assi spaziali calibrati

    Parametri
    ----------
    reader : WDFReader
       Istanza aperta di renishawWire WDFReader

    Returns
    -------
    img_arr : numpy.ndarray or None
        Image array with shape (H, W) or (H, W, 3)
    meta : dict or None
        Dizionario contenente i metadati delle coordinate fisiche:
        origin (µm), physical dimensions (µm), pixel resolution (µm/px),
        e array di coordinate pre-calcolati per gli assi x e y
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
    Genera un'immagine RGB sovrapponendo la griglia di acquisizione Raman
    alla micrografia ottica di white-light

    ogni punto di acquisizione viene mostrato con un marcatore rosso
    l'immagine risultante viene salvata nel file HDF5 sotto 'ENTRY/auxiliary/acquisition_map'
    e fornisce un contesto spaziale utile per interpretare le mappe spettrali

    Parametri
    ----------
    img_arr : numpy.ndarray
        White-light image array
    wl_meta : dict
        Spatial metadata dict returned by ``_extract_white_light_image``
    x_axis, y_axis : numpy.ndarray
        Physical coordinates (µm) della griglia di acquisizione Raman

    Returns
    -------
    numpy.ndarray or None
        RGB image array (uint8) of shape (H, W, 3), or None in caso di errore
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


def _read_wmap_direct(wdf_path: Path) -> dict:
    """
    Legge il blocco WMAP direttamente dal file binario WDF,
    bypassando renishawWiRE map_info che usa chiavi inconsistenti.

    Struttura WMAP (offset dal dato, dopo i 16 byte di header blocco):
      0:  flags    uint32
      4:  reserved uint32
      8:  x_start  float32  (µm)
      12: y_start  float32  (µm)
      16: x_pad    float32
      20: x_step   float32  (µm)
      24: y_step   float32  (µm)
      28: z_step   float32
      32: num_x    uint32
      36: num_y    uint32
      40: num_z    uint32
    """
    import struct as _struct
    try:
        with open(wdf_path, "rb") as fh:
            raw = fh.read()
        pos = 0
        while pos + 16 <= len(raw):
            tag  = raw[pos:pos+4]
            size = _struct.unpack_from('<Q', raw, pos+8)[0]
            if tag == b'WMAP' and size >= 48:
                d = raw[pos+16:pos+16+48]
                x_start = _struct.unpack_from('<f', d, 8)[0]
                y_start = _struct.unpack_from('<f', d, 12)[0]
                x_step  = _struct.unpack_from('<f', d, 20)[0]
                y_step  = _struct.unpack_from('<f', d, 24)[0]
                num_x   = _struct.unpack_from('<I', d, 32)[0]
                num_y   = _struct.unpack_from('<I', d, 36)[0]
                print(f"[FAIRaman] WMAP direct: x_start={x_start:.3f} y_start={y_start:.3f} "
                      f"x_step={x_step:.3f} y_step={y_step:.3f} num_x={num_x} num_y={num_y}")
                return {
                    "x_start": float(x_start),
                    "y_start": float(y_start),
                    "x_step":  float(x_step),
                    "y_step":  float(y_step),
                    "num_x":   int(num_x),
                    "num_y":   int(num_y),
                }
            if size == 0 or size > len(raw):
                break
            pos += size
    except Exception as exc:
        print(f"[FAIRaman] WARNING _read_wmap_direct: {exc}")
    return {}


def process_wdf(wdf_path: Path) -> dict:
    """
    Lege un file WDF di Renishaw e restituisce un dizionario con dati spettrali

    L'array spettrale viene rimodellato in un cubo tridimensionale di intensità
    con assi (Y, X, numero d'onda), coerente con la convenziona NXraman sia per acquisizioni
    singole sia per mappe bidimensionali
    Gli assi spaziali sono espressi in micrometri reali, ricavati dal blocco map_info del file WDF
    
    Se presente, vengono estratti anche l'immagine a white-light e la sovrapposizione della griglia

    Parametri
    ----------
    wdf_path : Path
        Percorso del file WDF di input

    Returns
    -------
    dict
        Keys: cube, raman_shift, x_axis, y_axis, white_light,
        white_light_meta, acquisition_map, instrument, filename,
        source_format.

    Eccezioni
    ------
    RuntimeError
        se renishawWiRe non è installato
    """
    if not HAS_WDF:
        raise RuntimeError(
            "renishawWiRE is not installed. Install it with: pip install renishawWiRE"
        )

    reader      = WDFReader(str(wdf_path))
    spectra     = np.asarray(reader.spectra)
    raman_shift = np.asarray(reader.xdata)

    # Reshape a (ny, nx, n_wavenumbers) a priori del tipo di acquisizione
    if spectra.ndim == 1:
        cube = spectra.reshape(1, 1, -1)
    elif spectra.ndim == 2:
        cube = spectra.reshape(spectra.shape[0], 1, spectra.shape[1])
    else:
        cube = spectra

    ny, nx, _ = cube.shape

    # Legge coordinate direttamente dal blocco WMAP binario —
    # più affidabile di map_info che usa chiavi inconsistenti tra versioni WiRE
    wmap = _read_wmap_direct(wdf_path)
    x0 = wmap.get("x_start", 0.0)
    y0 = wmap.get("y_start", 0.0)
    dx = wmap.get("x_step",  1.0)
    dy = wmap.get("y_step",  1.0)

    # num_x/num_y da WMAP sono la fonte di verità per gli assi
    nx_wmap = wmap.get("num_x", nx)
    ny_wmap = wmap.get("num_y", ny)
    if wmap and (nx_wmap != nx or ny_wmap != ny):
        print(f"[FAIRaman] WARNING: cube shape ({ny}×{nx}) ≠ WMAP ({ny_wmap}×{nx_wmap}), "
              f"uso WMAP per gli assi")

    x_axis = x0 + np.arange(nx_wmap) * dx if nx_wmap > 1 else np.array([float(x0)])
    y_axis = y0 + np.arange(ny_wmap) * dy if ny_wmap > 1 else np.array([float(y0)])

    wl_img, wl_meta = _extract_white_light_image(reader)
    acq_map = (
        _create_acquisition_map(wl_img, wl_meta, x_axis, y_axis)
        if wl_img is not None else None
    )

    instrument_meta = {
        "laser_wavelength": float(getattr(reader, "laser_length", 0.0)),
        "x_start": x0, "y_start": y0, "x_step": dx, "y_step": dy,
    }

    return {
        "cube":             cube,
        "raman_shift":      raman_shift,
        "x_axis":           x_axis,
        "y_axis":           y_axis,
        "white_light":      wl_img,
        "white_light_meta": wl_meta,
        "acquisition_map":  acq_map,
        "instrument":       instrument_meta,
        "filename":         wdf_path.name,
        "wdf_path":         wdf_path,
        "source_format":    "wdf",
    }


# ─────────────────────────────────────────────────────────────────────────────
# ASCII TWO-COLUMN PROCESSAMENTO SPETTRALE 
# ─────────────────────────────────────────────────────────────────────────────

def process_txt_spectrum(txt_path: Path) -> dict:
    """
    Legge un file spettrale ASCII a due colonne e restituisce un dizionario di dati normalizzati

    Il file deve contenere un punto dati per riga: la prima colonna rappresenta 
    il Raman shift (cm-1) e la seconda colonna l'intensità corrispondente
    le righe di commento iniziano con '#' (compresi eventuali header di colonna) vengono ignorate
    i delimitatori supportati sono spazi/tab, virgola e punto e virgola
    la funziona prova a rilevarli automaticamente in quest'ordine 

    L'asse dei numeri d'onda viene ordinato in ordine crescente prima di ulteriori elaborazioni,
    poiché alcune routine di esporatzione degli sturmenti scrivono gli spettri
    dall'alto verso il basso
    il dizionario restituito ha la stessa struttura di quello prodotto da 'process_wdf'
    così che entrambi i tipi di input possano condividere la pipeline di scrittura HDF5

    Parametri
    ----------
    txt_path : Path
        Percorso del file spettrale ASCII (.txt, .csv, or .dat).

    Returns
    -------
    dict
        Keys: cube, raman_shift, x_axis, y_axis, white_light,
        white_light_meta, acquisition_map, instrument, filename,
        source_format.

    Eccezioni
    ------
    ValueError
        se il file non contiene almeno due colnne numeriche
    """
    # Tenta delimiter auto-detection: whitespace → comma → semicolon
    arr = None
    for delimiter in [None, ",", ";"]:
        try:
            arr = np.loadtxt(
                txt_path,
                comments="#",
                delimiter=delimiter,
                encoding="utf-8",
            )
            break
        except Exception:
            continue

    if arr is None:
        raise ValueError(
            f"Could not parse '{txt_path.name}': no supported delimiter found "
            f"(tried whitespace, comma, semicolon)."
        )

    if arr.ndim == 1 or arr.shape[1] < 2:
        raise ValueError(
            f"'{txt_path.name}' must contain at least two numeric columns "
            f"(wavenumber, intensity). Detected shape: {arr.shape}."
        )

    raman_shift = arr[:, 0].astype(np.float64)
    intensity   = arr[:, 1].astype(np.float64)

    # Ordina per wavenumber (ascending) per assicurare assi orientati giusti
    sort_idx    = np.argsort(raman_shift)
    raman_shift = raman_shift[sort_idx]
    intensity   = intensity[sort_idx]

    # Reshape intensità a (1, 1, n_wavenumbers) per pipeline compatibility
    cube = intensity.reshape(1, 1, -1)

    instrument_meta = {
        "laser_wavelength": 0.0,
        "x_start": 0.0, "y_start": 0.0,
        "x_step":  1.0, "y_step":  1.0,
    }

    return {
        "cube":             cube,
        "raman_shift":      raman_shift,
        "x_axis":           np.array([0.0]),
        "y_axis":           np.array([0.0]),
        "white_light":      None,
        "white_light_meta": None,
        "acquisition_map":  None,
        "instrument":       instrument_meta,
        "filename":         txt_path.name,
        "source_format":    "txt",
    }


# ─────────────────────────────────────────────────────────────────────────────
# HDF5/NeXus OUTPUT
# ─────────────────────────────────────────────────────────────────────────────

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
    Scrive ricorsivamente la gerarchia NEXUS_SCHEMA in un file HDF5

    ogni voce dello schema viene creata come gruppo HDF5 con l'attributo NX_class appropriato
    se 'ensure_complete' è True, tutti i campi definiti nello Schema vengono scritti nel file,
    anche se non hanno un valore in 'data_dict';
    i valori mancanti vengono memorizzati come stringhe vuote
    questo garantisce coerenza strutturale tra tutti i file di output FAIRaman, 
    permettendo la lettura batch senza doversi preoccupare dello Schema specifico

    Parametri
    ----------
    h5grp : h5py.Group
        Gruppo HDF5 in cui scrivere (tipicamente la radice del file)
    schema : dict
        Dizionario dello (sotto-)schema conforme alla convenzione NEXUS_SCHEMA
    data_dict : dict
        Mappatura piatta di percorsi HDF5 sparati da punti verso i valori
    path_prefix : str
        Prefisso separato da punti accumulato durante la ricorsione
    ensure_complete : bool
        se True, scrive dataset vuoti per tutti i campi dello schema non presenti
        in ``data_dict`` (consigliato per l'uso in produzione)
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

    # Spectral count: total number of acquired spectra (ny × nx)
    sc_path = "ENTRY.data.spectral_count"
    if not flat_data.get(sc_path):
        flat_data[sc_path] = int(data["cube"].shape[0] * data["cube"].shape[1])

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

    with h5py.File(out_path, "w") as f:

        # 1. Write the complete metadata hierarchy (PROJECT, SAMPLE, ENTRY)
        _write_nexus_structure(f, NEXUS_SCHEMA, flat_data, ensure_complete=True)

        # 2. Write spectral data into ENTRY/data (NXdata)
        entry = f["ENTRY"] if "ENTRY" in f else f.create_group("ENTRY")
        if "NX_class" not in entry.attrs:
            entry.attrs["NX_class"] = "NXentry"
            entry.attrs["definition"] = "NXraman"

        data_grp = entry.create_group("data")
        data_grp.attrs["NX_class"] = "NXdata"
        data_grp.attrs["signal"]   = "intensity"
        data_grp.attrs["axes"]     = ["y", "x", "raman_shift"]

        # Intensity cube: shape (ny, nx, n_wavenumbers), gzip-compressed
        data_grp.create_dataset(
            "intensity", data=data["cube"], compression="gzip", chunks=True
        )
        data_grp.create_dataset("raman_shift", data=data["raman_shift"])
        data_grp.create_dataset("x",           data=data["x_axis"])
        data_grp.create_dataset("y",           data=data["y_axis"])
        ny, nx, n_wn = data["cube"].shape
        data_grp.attrs["spectral_count"] = int(ny * nx)
        data_grp.attrs["nx"]             = int(nx)
        data_grp.attrs["ny"]             = int(ny)
        data_grp.attrs["n_wavenumbers"]  = int(n_wn)

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
        f.attrs["fairaman_version"] = "1.0"


# ─────────────────────────────────────────────────────────────────────────────
# EXPORT: CSV AND JSON SIDECAR
# ─────────────────────────────────────────────────────────────────────────────

def export_csv(data: dict, out_path: Path) -> None:
    """
    Esporta i dati spettrali in un file flat CSV

    Ogni riga corrisponde a un punto di acquisizione
    le prime due colonne contengono le coordinate spaziali (x_um, y_um)
    mentre le colonne successive riportano l'intensità a ciascun numero d'onda

    Parametri
    ----------
    data : dict
        Spectral data dictionary (come restituito da ``process_wdf`` o
        ``process_txt_spectrum``)
    out_path : Path
        Percorso di destinazione del file CSV
    """
    ny, nx, n_pts = data["cube"].shape
    XX, YY = np.meshgrid(data["x_axis"], data["y_axis"])
    flat = np.column_stack([
        XX.flatten(),
        YY.flatten(),
        data["cube"].reshape(ny * nx, n_pts),
    ])
    columns = ["x_um", "y_um"] + [f"{w:.4f}" for w in data["raman_shift"]]
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


# ─────────────────────────────────────────────────────────────────────────────
# GUI COMPONENTS
# ─────────────────────────────────────────────────────────────────────────────

def _create_filterable_combobox(parent: tk.Widget, width: int = 60):
    """
    Finestrella selezione 
    """
    BG      = "#1e1e2e"
    BG_SEL  = "#89b4fa"
    FG      = "#cdd6f4"
    FG_SEL  = "#1e1e2e"
    BORDER  = "#45475a"
    FONT    = ("Courier New", 9)

    frame = tk.Frame(parent, bg=BORDER, bd=1, relief="flat")
    var   = tk.StringVar(value="Do not map")

    entry = tk.Entry(frame, textvariable=var, bg="#2a2a3e", fg=FG,
                     insertbackground=FG, font=FONT, relief="flat",
                     bd=4, width=width)
    entry.pack(fill="x")

    # ── Floating dropdown ────────────────────────────────────────────────────
    popup    = None   
    listbox  = None
    _open    = [False]

    def _filtered():
        q = var.get().lower().strip()
        if not q or q == "do not map":
            return HDF5_FIELDS
        starts   = [f for f in HDF5_FIELDS if f.lower().startswith(q)]
        contains = [f for f in HDF5_FIELDS if q in f.lower() and f not in starts]
        return starts + contains

    def _open_popup(*_):
        nonlocal popup, listbox
        if _open[0]:
            _refresh_list()
            return
        _open[0] = True

        popup = tk.Toplevel(entry)
        popup.wm_overrideredirect(True)
        popup.wm_attributes("-topmost", True)

        # Position below the entry
        entry.update_idletasks()
        x = entry.winfo_rootx()
        y = entry.winfo_rooty() + entry.winfo_height()
        w = max(entry.winfo_width(), 380)
        popup.geometry(f"{w}x220+{x}+{y}")

        sb = tk.Scrollbar(popup, orient="vertical")
        listbox = tk.Listbox(popup, yscrollcommand=sb.set,
                             bg=BG, fg=FG, selectbackground=BG_SEL,
                             selectforeground=FG_SEL, font=FONT,
                             relief="flat", bd=0,
                             activestyle="none", exportselection=False)
        sb.config(command=listbox.yview)
        sb.pack(side="right", fill="y")
        listbox.pack(side="left", fill="both", expand=True)

        # Scroll wheel on listbox scrolls
        def _lb_scroll(event):
            listbox.yview_scroll(int(-1*(event.delta/120)), "units")
            return "break"
        listbox.bind("<MouseWheel>", _lb_scroll)
        popup.bind("<MouseWheel>", _lb_scroll)

        listbox.bind("<ButtonRelease-1>", _select)
        listbox.bind("<Return>",          _select)

        _refresh_list()

        # Close when clicking outside
        popup.bind("<FocusOut>", lambda e: _maybe_close())

    def _refresh_list():
        if not listbox:
            return
        items = _filtered()
        listbox.delete(0, "end")
        for item in items:
            listbox.insert("end", item)
        # Highlight current value
        cur = var.get()
        if cur in items:
            idx = items.index(cur)
            listbox.selection_set(idx)
            listbox.see(idx)

    def _select(event=None):
        if not listbox:
            return
        sel = listbox.curselection()
        if sel:
            var.set(listbox.get(sel[0]))
        _close()

    def _close():
        nonlocal popup, listbox
        _open[0] = False
        if popup:
            try: popup.destroy()
            except Exception: pass
        popup   = None
        listbox = None

    def _on_root_click(event):
        if not _open[0]:
            return
        w = event.widget
        try:
            if w is entry or w is frame:
                return
            if popup and str(w).startswith(str(popup)):
                return
        except Exception:
            pass
        _close()

    entry.after(1, lambda: entry.winfo_toplevel().bind_all(
        "<Button-1>", _on_root_click, add="+"
    ))

    def _maybe_close():
        entry.after(150, lambda: _close() if not _open[0] else None)

    def _on_key(event):
        if event.keysym == "Escape":
            _close(); return
        if event.keysym in ("Return", "Tab"):
            _select(); return
        if event.keysym in ("Down", "Up"):
            if not _open[0]:
                _open_popup()
            if listbox:
                sel = listbox.curselection()
                idx = sel[0] if sel else -1
                if event.keysym == "Down":
                    idx = min(idx + 1, listbox.size() - 1)
                else:
                    idx = max(idx - 1, 0)
                listbox.selection_clear(0, "end")
                listbox.selection_set(idx)
                listbox.see(idx)
            return "break"
        # Any other key: open and refresh
        entry.after(10, lambda: (_open_popup() if not _open[0] else _refresh_list()))

    entry.bind("<KeyPress>",    _on_key)
    entry.bind("<FocusOut>",    lambda e: entry.after(200, lambda: _close() if popup and not popup.focus_get() else None))
    entry.bind("<Button-1>",    _open_popup)
    entry.bind("<MouseWheel>",  lambda e: "break")   # absorb — don't scroll page
    frame.bind("<MouseWheel>",  lambda e: "break")

    frame.get = var.get
    frame.set = var.set
    frame.var = var
    return frame


def _build_mapping_frame(parent: tk.Widget, source_dict: dict,
                         title: str) -> tk.LabelFrame:
    """
    Fa funzionare la finestra scrollabile laga ves
    """
    BG       = "#1e1e2e"
    BG_PANEL = "#2a2a3e"
    FG       = "#cdd6f4"
    ACCENT   = "#89b4fa"
    BORDER   = "#45475a"
    FONT_SM  = ("Courier New", 9)
    FONT_B   = ("Courier New", 9, "bold")

    frame  = tk.LabelFrame(parent, text=f" {title} ", bg=BG_PANEL, fg=ACCENT,
                           font=("Courier New", 11, "bold"), bd=1, relief="solid",
                           highlightbackground=BORDER)
    canvas = tk.Canvas(frame, height=260, bg=BG_PANEL, highlightthickness=0)
    sb     = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
    inner  = tk.Frame(canvas, bg=BG_PANEL)

    inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=inner, anchor="nw")
    canvas.configure(yscrollcommand=sb.set)
    canvas.pack(side="left", fill="both", expand=True, padx=4, pady=4)
    sb.pack(side="right", fill="y", pady=4)

    def _sub_scroll(event):
        canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        return "break"
    canvas.bind("<MouseWheel>", _sub_scroll)
    inner.bind("<MouseWheel>",  _sub_scroll)

    # Header row
    tk.Label(inner, text="Campo sorgente", font=FONT_B,
             bg=BG_PANEL, fg=ACCENT).grid(row=0, column=0, sticky="w", padx=8, pady=4)
    tk.Label(inner, text="→  HDF5 target path", font=FONT_B,
             bg=BG_PANEL, fg=ACCENT).grid(row=0, column=1, sticky="w", padx=8, pady=4)

    combos: dict = {}
    for i, (key, val) in enumerate(source_dict.items(), 1):
        tk.Label(inner, text=f"{key}: {str(val)[:60]}",
                 bg=BG_PANEL, fg=FG, font=FONT_SM,
                 wraplength=460, anchor="w").grid(
            row=i, column=0, sticky="w", padx=8, pady=2)
        cb = _create_filterable_combobox(inner)
        cb.grid(row=i, column=1, sticky="ew", padx=8, pady=2)
        combos[key] = cb

    inner.columnconfigure(1, weight=1)
    frame.get_mapping = lambda: {k: cb.get() for k, cb in combos.items()}
    return frame


def _show_ontology_help() -> None:
    hw = tk.Toplevel()
    hw.title("FAIRaman — Ontology Reference")
    hw.geometry("620x380")

    tf = ttk.Frame(hw)
    tf.pack(fill="both", expand=True, padx=10, pady=10)
    tw = tk.Text(tf, wrap="word", font=("Consolas", 10))
    sb = ttk.Scrollbar(tf, command=tw.yview)
    tw.configure(yscrollcommand=sb.set)
    tw.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")

    content = (
        "═══ ONTOLOGY AND STANDARD REFERENCES ═══\n\n"
        "Anatomical site (anatomical_site_cs):\n"
        "  UBERON: https://www.ebi.ac.uk/ols/ontologies/uberon\n"
        "  Format: UBERON:<numeric_id>  (e.g. UBERON:0000178 for blood)\n\n"
        "Diagnosis coding (diagnosis_code / diagnosis_ontology):\n"
        "  ICD-10:  https://icd.who.int/browse10/2019/en\n"
        "  ICD-O-3: https://www.who.int/standards/classifications\n"
        "  Format: ICD-10:<code>  (e.g. ICD-10:K50.0 for Crohn's disease)\n\n"
        "Biobanking standard:\n"
        "  MIABIS v3: https://github.com/BBMRI-ERIC/miabis\n\n"
        "NeXus / NXraman:\n"
        "  https://manual.nexusformat.org/classes/applications/NXraman.html\n\n"
        "FAIR principles:\n"
        "  Wilkinson et al. (2016) Sci. Data 3, 160018\n"
        "  https://doi.org/10.1038/sdata.2016.18\n"
    )
    tw.insert("1.0", content)
    tw.config(state="disabled")
    ttk.Button(hw, text="Close", command=hw.destroy).pack(pady=10)


# ─────────────────────────────────────────────────────────────────────────────
# CONVERSION PIPELINE — SHARED METADATA LOADING
# ─────────────────────────────────────────────────────────────────────────────

# HDF5 path prefixes that belong to the Investigation/Assay level and are
# therefore sourced from the shared TXT metadata file (not from the per-file
# Excel sheet, which covers the Sample level only).
_INVESTIGATION_ASSAY_PREFIXES = (
    "PROJECT",
    "ENTRY.measurement",
    "ENTRY.instrument",
    "ENTRY.title",
    "ENTRY.experiment_type",
)

# Known spectral file extensions to strip when normalising filename stems.
_STRIP_EXTS = {".wdf", ".WDF", ".txt", ".TXT", ".csv", ".CSV", ".dat", ".DAT"}


def _normalise_stem(raw: str) -> str:
    """
    Normalizza un valore filename grezzo dalla colonna chiave Excel in minuscolo,
    senza estensione per lookup di dizionario
    
    Solo una singola trailing extension è rimossa (es "sample.wdf" → "sample")
    altre casistiche non sono qui gestite 
    perché non capitano nelle normali nomenclature file Raman
    
    Parametri
    ----------
    raw : str
        Valore della cella grezzo dalla colonna dei filename in Excel
    
    Returns
    -------
    str
        Lowercase stem with leading/trailing whitespace tolto
    """
    s = str(raw).strip()
    p = Path(s)
    if p.suffix in _STRIP_EXTS:
        s = p.stem
    return s.lower()


def _get_excel_row(stem: str, excel_map: dict):
    """
    Cerca la riga dei metadati in Excel corrispondente a un determinato nome file (senza estensione).

    La ricerca avviene in due modi:
        1) confronto esatto dopo aver convertito tutto in minuscolo
        2) confronto più permissivo che ignora o normalizza separatori nel nome

    A ogni chiamata vengono printate informazioni diagnostiche complete,
    così è più facile capire come è stato trovato (o non trovato) il match

    Ritorna il dizionario della riga corrispondente, oppure None se non viene
    trovata alcuna corrispondenza.
    """
    norm = stem.strip().lower()

    if norm in excel_map:
        print(f"[FAIRaman] Excel match: \'{stem}\' -> exact key \'{norm}\'")
        return excel_map[norm]

    norm_fuzzy = re.sub(r"[_\- ]", "", norm)
    for key, row in excel_map.items():
        key_fuzzy = re.sub(r"[_\- ]", "", key)
        if key_fuzzy == norm_fuzzy:
            print(f"[FAIRaman] Excel match (fuzzy): \'{stem}\' -> key \'{key}\'")
            return row

    print(
        f"[FAIRaman] NO Excel match for \'{norm}\'. "
        f"Available keys ({len(excel_map)}): {list(excel_map.keys())}"
    )
    return None



def _load_metadata_sources(state: dict, frames: dict) -> tuple:
    """
    Carica e preprocessa i metadati dal TXT e dall'Excel
    
    Il file TXT è sempre letto, siccome richiesto per le conversioni
    Il file Excel è opzionale, se presente la prima colnna viene usata
    per filename, 
    riflette il layout previsto del foglio Excel dove la colonna A 
    contiene i nomi dei file WDF (o degli spettri ASCII)
    
    Nomi dei file normalizzati tramite  ``_normalise_stem`` (lowercase, extension
    stripped) di modo che  ``"Sample_001.wdf"``, ``"sample_001"``, and
    ``"SAMPLE_001"`` siano tutti sotto la stessa chiave ``"sample_001"``.

    Parametri
    ----------
    state : dict
        Dionario dello stato dell'applicazione che contiene il subdictionario
    frames : dict
        GUI frame registry (non viene modificato, qui passato per coerenza con API).

    Returns
    -------
    tuple
        ``(txt_meta, excel_df, excel_metadata_map, filename_col, empty_row)``

        * ``txt_meta``          — dizionario dei metadati letti dal TXT
        * ``excel_df``          — DataFrame originale oppure None
        * ``excel_metadata_map``— mapping stem_normalizzato → dizionario riga Excel
        * ``filename_col``      — nome della prima colonna Excel (oppure None)
        * ``empty_row``      — prima riga del foglio Excel usata come fallback
    """
    txt_meta: dict = parse_txt_metadata(state["paths"]["txt"])
    print(f"[FAIRaman] TXT metadata loaded: {len(txt_meta)} fields")

    excel_df: pd.DataFrame | None = None
    excel_metadata_map: dict      = {}
    filename_col: str | None      = None
    empty_row: dict            = {}

    if state["paths"].get("excel"):
        try:
            excel_df = pd.read_excel(state["paths"]["excel"])

            if excel_df.empty:
                print("[FAIRaman] WARNING: Excel file is empty.")
                return txt_meta, excel_df, excel_metadata_map, filename_col, empty_row

            # Usa prima colonna non tira a indovinare
            filename_col = excel_df.columns[0]
            print(
                f"[FAIRaman] Excel: first column '{filename_col}' used as "
                f"filename key (normalised to lowercase stems)."
            )

            for _, row in excel_df.iterrows():
                norm_key = _normalise_stem(str(row[filename_col]))
                if norm_key:
                    excel_metadata_map[norm_key] = row.to_dict()

            print(
                f"[FAIRaman] Excel metadata loaded: {len(excel_metadata_map)} rows "
                f"(key column: '{filename_col}')"
            )

        except Exception as exc:
            print(f"[FAIRaman] WARNING: Could not load Excel file: {exc}")

    return txt_meta, excel_df, excel_metadata_map, filename_col, empty_row


def _assemble_flat_data(txt_meta: dict, excel_row: dict,
                        frames: dict) -> dict:
    """
    Costruisce un dizionario di metadati indicizzato dai percorsi HDF5 
    unendo le informazioni proveinienti dal TXT e dalla riga Excel
    
    i campi sorgente vengono indirizzati verso il percorso HDF5 corretto
    in abse alle mappature definite dall'utente nella GUI

    Se più campi sorgente finiscono nello stesso percorso HDF5, i valori
    non si sovrascrivono: vengono invece concatenati usando " | " come
    separatore
    
    Parametri
    ----------
    txt_meta : dict
        Contenuto del file di metadati TXT
    excel_row : dict
        Riga della tabella Excel con i metadati del campione per il file corrente
    frames : dict
        Registo dei frame della GUI, usato per accedere alla funzione 'get_mapping()'

    Returns
    -------
    dict
        Dizionario piatto che associa i percorsi HDF5 ai rispettivi valori di metadato
    """
    flat_data: dict = {}

    def _append(hdf_path: str, val) -> None:
        """Add val to flat_data[hdf_path], concatenating if already present."""
        s = str(val).strip()
        if not s:
            return
        if hdf_path in flat_data:
            existing = str(flat_data[hdf_path]).strip()
            if s not in existing:           # avoid exact duplicates
                flat_data[hdf_path] = f"{existing} | {s}"
                print(f"[FAIRaman] INFO: '{hdf_path}' has multiple sources → concatenated")
        else:
            flat_data[hdf_path] = s

    # Fields from TXT 
    if "txt" in frames:
        for src_key, hdf_path in frames["txt"].get_mapping().items():
            if not hdf_path or hdf_path == "Do not map":
                continue
            val = txt_meta.get(src_key)
            if val:
                _append(hdf_path, val)

    # Fields from Excel 
    if "excel" in frames and excel_row:
        for src_key, hdf_path in frames["excel"].get_mapping().items():
            if not hdf_path or hdf_path == "Do not map":
                continue
            val = excel_row.get(src_key)
            if val is not None and str(val).strip() != "":
                _append(hdf_path, val)

    return flat_data


# ─────────────────────────────────────────────────────────────────────────────
# CONVERSION PIPELINE — WDF MODE
# ─────────────────────────────────────────────────────────────────────────────

def _run_conversion_wdf(state: dict, frames: dict,
                        var_hdf5: tk.BooleanVar, var_json: tk.BooleanVar,
                        var_csv: tk.BooleanVar, progress_var: tk.StringVar,
                        progress_bar: ttk.Progressbar, root: tk.Tk) -> None:
    """
    Esegue la conversione batch dei file WDF nel formato FAIRaman HDF5/NeXus.

    Per ogni file WDF presente nella cartella di input la funzione:
        1) normalizza il nome del file (senza estensione) e cerca la riga
        corrispondente nel file Excel usando `_get_excel_row`
        (prima prova una corrispondenza esatta, poi una ricerca più permissiva);
        2) costruisce il dizionario dei metadati unendo le informazioni del TXT
         (livelli Investigation/Assay) e quelle di Excel (livello Sample)
        secondo le mappature definite nella GUI;
        3) legge il cubo spettrale dal file WDF insieme all’eventuale white-light image;
        4) genera i file di output selezionati (HDF5, JSON e/o CSV).

    I file per cui non viene trovata una riga corrispondente in Excel vengono
    saltati e segnalati nel riepilogo finale. Se non viene fornito alcun file
    Excel, tutti i file vengono comunque convertiti utilizzando solo i
    metadati del TXT.
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


# ─────────────────────────────────────────────────────────────────────────────
# CONVERSION PIPELINE — ASCII TXT MODE
# ─────────────────────────────────────────────────────────────────────────────

def _run_conversion_txt(state: dict, frames: dict,
                        var_hdf5: tk.BooleanVar, var_json: tk.BooleanVar,
                        var_csv: tk.BooleanVar, progress_var: tk.StringVar,
                        progress_bar: ttk.Progressbar, root: tk.Tk) -> None:

        """
    Esegue la conversione batch di file spettrali ASCII nel formato FAIRaman HDF5/NeXus.

    La logica è la stessa di `_run_conversion_wdf`, ma applicata a file spettrali
    in formato testo a due colonne (.txt, .csv, .dat). Il file TXT dei metadati
    viene escluso automaticamente dalla lista dei file di input anche se si trova
    nella stessa cartella.

    Per associare i metadati dal file Excel viene usata la stessa funzione
    `_get_excel_row` della pipeline WDF, così il comportamento di matching resta
    coerente tra i due flussi.

    I file per cui non viene trovata una riga corrispondente in Excel vengono
    saltati e segnalati nel riepilogo finale. Se non viene fornito alcun file
    Excel, tutti i file vengono comunque convertiti utilizzando solo i
    metadati del TXT.
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
    Compute the intensity-weighted centre of mass of a spectrum.

    Parameters
    ----------
    shift : np.ndarray
        Wavenumber axis (cm-1).
    intensity : np.ndarray
        Corresponding intensity values (must be >= 0; negatives clipped).

    Returns
    -------
    float
        Centre-of-mass wavenumber (cm-1).
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

# ─────────────────────────────────────────────────────────────────────────────
# GRAPHICAL USER INTERFACE
# ─────────────────────────────────────────────────────────────────────────────

def _pick_path(key: str, is_file: bool, state: dict, entries: dict,
               frames: dict, parent: tk.Widget) -> None:
    """
    Open a file or directory browser dialog and update the application state.

    When a metadata file (TXT or Excel) is selected, the corresponding
    mapping panel is rebuilt to reflect the new field set.
    """
    path = filedialog.askopenfilename() if is_file else filedialog.askdirectory()
    if not path:
        return

    state["paths"][key] = Path(path)
    entries[key].delete(0, tk.END)
    entries[key].insert(0, path)

    if key == "excel":
        if "excel" in frames:
            frames["excel"].destroy()
            del frames["excel"]
        try:
            df = pd.read_excel(path)
            if not df.empty:
                frames["excel"] = _build_mapping_frame(
                    parent, df.iloc[0].to_dict(),
                    "Excel → NeXus mapping  (Sample level)"
                )
                frames["excel"].pack(fill="both", expand=True, padx=10, pady=5)
        except Exception as exc:
            messagebox.showerror("Error", f"Could not read Excel file:\n{exc}")

    if key == "txt":
        if "txt" in frames:
            frames["txt"].destroy()
            del frames["txt"]
        try:
            meta = parse_txt_metadata(Path(path))
            if meta:
                frames["txt"] = _build_mapping_frame(
                    parent, meta,
                    "Metadata TXT → NeXus mapping  (Investigation / Assay level)"
                )
                frames["txt"].pack(fill="both", expand=True, padx=10, pady=5)
            else:
                messagebox.showwarning(
                    "Warning",
                    "No metadata fields found in the selected TXT file.\n"
                    "Expected format: one 'key: value' pair per line."
                )
        except Exception as exc:
            messagebox.showerror("Error", f"Could not read TXT file:\n{exc}")


def launch_gui() -> None:
    """
    Initialise and display the FAIRaman graphical user interface.

    Styled to match H5Extractor: dark Catppuccin-inspired theme,
    Courier New monospace font, coloured section headers.
    All functional logic (paths, mapping panels, conversion) is unchanged.
    """
    root = tk.Tk()
    root.title("FAIRaman  \u2014  FAIR/MIABIS-compliant Raman Spectroscopy Converter")
    root.geometry("1200x920")
    root.resizable(True, True)

    # ── Theme constants (identical to H5Extractor) ────────────────────────────
    BG        = "#1e1e2e"
    BG_PANEL  = "#2a2a3e"
    FG        = "#cdd6f4"
    ACCENT    = "#89b4fa"
    ACCENT2   = "#a6e3a1"
    WARN      = "#f38ba8"
    BORDER    = "#45475a"
    FONT_HEAD = ("Courier New", 11, "bold")
    FONT_BODY = ("Courier New", 10)
    FONT_SM   = ("Courier New", 9)

    root.configure(bg=BG)

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass
    style.configure("TFrame",      background=BG)
    style.configure("TLabel",      background=BG,       foreground=FG,     font=FONT_BODY)
    style.configure("TLabelframe", background=BG_PANEL, foreground=ACCENT, font=FONT_HEAD,
                    bordercolor=BORDER, relief="solid")
    style.configure("TLabelframe.Label", background=BG_PANEL, foreground=ACCENT, font=FONT_HEAD)
    style.configure("TEntry",      fieldbackground=BG_PANEL, foreground=FG,
                    insertcolor=FG, bordercolor=BORDER)
    style.configure("TButton",     background=ACCENT,  foreground=BG,
                    font=("Courier New", 10, "bold"), borderwidth=0)
    style.map("TButton",
              background=[("active", ACCENT2), ("pressed", ACCENT2)],
              foreground=[("active", BG)])
    style.configure("TRadiobutton", background=BG_PANEL, foreground=FG, font=FONT_BODY)
    style.map("TRadiobutton", background=[("active", BG_PANEL)])
    style.configure("TCheckbutton", background=BG_PANEL, foreground=FG, font=FONT_BODY)
    style.map("TCheckbutton", background=[("active", BG_PANEL)])
    style.configure("TProgressbar", troughcolor=BG_PANEL, background=ACCENT,
                    bordercolor=BORDER)
    style.configure("TCombobox", fieldbackground=BG_PANEL, foreground=FG,
                    selectbackground=ACCENT, selectforeground=BG)

    # ── Header ────────────────────────────────────────────────────────────────
    hdr = tk.Frame(root, bg=BG, pady=12)
    hdr.pack(fill="x", padx=20)
    tk.Label(hdr, text="FAIRaman", bg=BG, fg=ACCENT,
             font=("Courier New", 20, "bold")).pack(side="left")
    tk.Label(hdr, text="  FAIR/MIABIS-compliant Raman Spectroscopy Converter",
             bg=BG, fg=FG, font=FONT_BODY).pack(side="left", pady=4)

    # ── Scrollable main area ──────────────────────────────────────────────────
    main_canvas  = tk.Canvas(root, bg=BG, highlightthickness=0)
    v_scrollbar  = ttk.Scrollbar(root, orient="vertical", command=main_canvas.yview)
    scroll_frame = tk.Frame(main_canvas, bg=BG)
    scroll_frame.bind(
        "<Configure>",
        lambda e: main_canvas.configure(scrollregion=main_canvas.bbox("all"))
    )
    win_id = main_canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
    main_canvas.configure(yscrollcommand=v_scrollbar.set)
    main_canvas.pack(side="left", fill="both", expand=True, padx=(20, 0), pady=(0, 10))
    v_scrollbar.pack(side="right", fill="y", pady=(0, 10))

    # Resize inner frame to always match canvas width
    def _on_canvas_resize(event):
        main_canvas.itemconfig(win_id, width=event.width)
    main_canvas.bind("<Configure>", _on_canvas_resize)

    # Mousewheel: scroll main canvas only when NOT over a widget with its own scroll
    def _on_mousewheel(event):
        w = event.widget
        # Walk up the widget tree to find if we are inside a mapping sub-canvas
        # (the inner scrollable area of Excel/TXT mapping panels)
        try:
            node = w
            while node:
                if isinstance(node, tk.Canvas) and node is not main_canvas:
                    # It's a sub-canvas (mapping panel) — scroll it, not the page
                    node.yview_scroll(int(-1 * (event.delta / 120)), "units")
                    return
                node = node.master
        except Exception:
            pass
        # Default: scroll the main page canvas
        main_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    root.bind_all("<MouseWheel>", _on_mousewheel)

    state:  dict = {"paths": {}}
    frames: dict = {}
    entries: dict = {}

    # ── Widget helpers ────────────────────────────────────────────────────────
    def _lf(parent, title):
        return tk.LabelFrame(parent, text=f" {title} ", bg=BG_PANEL, fg=ACCENT,
                             font=FONT_HEAD, bd=1, relief="solid",
                             highlightbackground=BORDER)

    def _lbl(parent, text, small=False, muted=False):
        return tk.Label(parent, text=text, bg=BG_PANEL,
                        fg="#6c7086" if muted else FG,
                        font=FONT_SM if small else FONT_BODY)

    def _ent(parent, textvariable=None, width=55):
        return tk.Entry(parent, textvariable=textvariable, bg=BG, fg=FG,
                        insertbackground=FG, font=FONT_BODY, width=width,
                        relief="flat", highlightthickness=1,
                        highlightcolor=ACCENT, highlightbackground=BORDER)

    def _btn(parent, text, command, big=False):
        bg = ACCENT2 if big else ACCENT
        return tk.Button(parent, text=text, bg=bg, fg=BG,
                         font=("Courier New", 12 if big else 10, "bold"),
                         relief="flat", cursor="hand2", padx=8,
                         activebackground=ACCENT, activeforeground=BG,
                         command=command)

    def _rb(parent, text, value, var):
        return tk.Radiobutton(parent, text=text, variable=var, value=value,
                              bg=BG_PANEL, fg=FG, selectcolor=BG,
                              activebackground=BG_PANEL, font=FONT_BODY,
                              command=lambda: _refresh_path_panel())

    def _cb(parent, text, variable):
        return tk.Checkbutton(parent, text=text, variable=variable,
                              bg=BG_PANEL, fg=FG, selectcolor=BG,
                              activebackground=BG_PANEL, font=FONT_BODY)

    # ── Section 1: Input mode ─────────────────────────────────────────────────
    mode_lf = _lf(scroll_frame, "Input mode")
    mode_lf.pack(fill="x", padx=10, pady=8)
    rb_row = tk.Frame(mode_lf, bg=BG_PANEL)
    rb_row.pack(anchor="w", padx=10, pady=8)

    mode_var = tk.StringVar(value="wdf")
    rb_wdf = _rb(rb_row, "WDF mode  (Renishaw WiRE .wdf files)", "wdf", mode_var)
    rb_txt = _rb(rb_row, "ASCII mode  (two-column text: wavenumber | intensity)", "txt", mode_var)
    rb_wdf.pack(side="left", padx=(0, 24))
    rb_txt.pack(side="left")

    if not HAS_WDF:
        rb_wdf.config(state="disabled")
        mode_var.set("txt")
        tk.Label(rb_row, text="(renishawWiRE not installed)",
                 bg=BG_PANEL, fg=WARN, font=FONT_SM).pack(side="left", padx=8)

    # ── Section 2: Path panel ─────────────────────────────────────────────────
    path_lf = _lf(scroll_frame, "File and folder paths")
    path_lf.pack(fill="x", padx=10, pady=8)

    _anchors: dict = {}
    def _make_row(label: str, key: str, is_file: bool, row: int):
        lbl_w = _lbl(path_lf, label)
        lbl_w.grid(row=row, column=0, sticky="w", padx=10, pady=5)
        ent = _ent(path_lf, width=68)
        ent.grid(row=row, column=1, padx=8, pady=5, sticky="ew")
        entries[key] = ent

        def _browse(k=key, f=is_file, e=ent):
            # Open dialog exactly once, then update state + rebuild mapping if needed
            path = (filedialog.askopenfilename() if f else filedialog.askdirectory())
            if not path:
                return
            state["paths"][k] = Path(path)
            e.delete(0, tk.END)
            e.insert(0, path)
            # Rebuild mapping panel for excel/txt keys
            if k == "excel":
                if "excel" in frames:
                    frames["excel"].destroy()
                    del frames["excel"]
                try:
                    df = pd.read_excel(path)
                    if not df.empty:
                        frames["excel"] = _build_mapping_frame(
                            scroll_frame, df.iloc[0].to_dict(),
                            "Excel \u2192 NeXus mapping  (Sample level)"
                        )
                        frames["excel"].pack(fill="both", expand=True,
                                             padx=10, pady=5, before=_anchors["opt_lf"])
                except Exception as exc:
                    messagebox.showerror("Error", f"Could not read Excel file:\n{exc}")
            elif k == "txt":
                if "txt" in frames:
                    frames["txt"].destroy()
                    del frames["txt"]
                try:
                    meta = parse_txt_metadata(Path(path))
                    if meta:
                        frames["txt"] = _build_mapping_frame(
                            scroll_frame, meta,
                            "Metadata TXT \u2192 NeXus mapping  (Investigation / Assay level)"
                        )
                        frames["txt"].pack(fill="both", expand=True,
                                           padx=10, pady=5, before=_anchors["opt_lf"])
                    else:
                        messagebox.showwarning(
                            "Warning",
                            "No metadata fields found in the TXT file.\n"
                            "Expected format: one 'key: value' pair per line."
                        )
                except Exception as exc:
                    messagebox.showerror("Error", f"Could not read TXT file:\n{exc}")

        b = _btn(path_lf, "Browse\u2026", _browse)
        b.grid(row=row, column=2, padx=(0, 10))
        path_lf.columnconfigure(1, weight=1)
        return lbl_w, ent, b

    row_wdf     = _make_row("WDF folder:",               "wdf",         False, 0)
    row_spectra = _make_row("Spectra folder:",            "spectra_dir", False, 0)
    row_excel   = _make_row("Sample metadata (Excel):",  "excel",       True,  1)
    row_txt_    = _make_row("Shared metadata (TXT):",    "txt",         True,  2)
    row_out     = _make_row("Output folder:",            "out",         False, 3)

    def _refresh_path_panel():
        if mode_var.get() == "wdf":
            for w in row_wdf:     w.grid()
            for w in row_spectra: w.grid_remove()
        else:
            for w in row_spectra: w.grid()
            for w in row_wdf:     w.grid_remove()

    _refresh_path_panel()

    # Section 3: mapping panels are inserted dynamically before opt_lf when
    # the user picks an Excel or TXT file (see _browse inside _make_row).

    # ── Section 4: Output options ─────────────────────────────────────────────
    opt_lf = _lf(scroll_frame, "Output formats")
    _anchors["opt_lf"] = opt_lf
    opt_lf.pack(fill="x", padx=10, pady=8)
    opt_row = tk.Frame(opt_lf, bg=BG_PANEL)
    opt_row.pack(anchor="w", padx=10, pady=8)

    var_hdf5    = tk.BooleanVar(value=True)
    var_json    = tk.BooleanVar(value=True)
    var_csv     = tk.BooleanVar(value=True)


    _cb(opt_row, "HDF5 / NeXus (NXraman)",       var_hdf5).pack(side="left", padx=(0, 16))
    _cb(opt_row, "JSON metadata sidecar",         var_json).pack(side="left", padx=(0, 16))
    _cb(opt_row, "CSV spectral matrix",           var_csv).pack(side="left",  padx=(0, 16))


    help_lf = _lf(scroll_frame, "References")
    help_lf.pack(fill="x", padx=10, pady=8)
    help_row = tk.Frame(help_lf, bg=BG_PANEL)
    help_row.pack(anchor="w", padx=10, pady=8)
    _lbl(help_row, "Ontology references (UBERON, ICD-10, MIABIS, NXraman):").pack(
        side="left", padx=(0, 12))
    _btn(help_row, "\U0001f4da Open reference guide", _show_ontology_help).pack(side="left")

    # ── Progress ──────────────────────────────────────────────────────────────
    prog_frame = tk.Frame(scroll_frame, bg=BG)
    prog_frame.pack(fill="x", padx=10, pady=4)
    progress_var = tk.StringVar(value="Ready.")
    tk.Label(prog_frame, textvariable=progress_var, bg=BG, fg=FG,
             font=FONT_SM, anchor="w").pack(fill="x")
    progress_bar = ttk.Progressbar(prog_frame, mode="determinate")
    progress_bar.pack(fill="x", pady=4)

    # ── Console log ───────────────────────────────────────────────────────────
    log_lf = _lf(scroll_frame, "Console log")
    log_lf.pack(fill="both", expand=True, padx=10, pady=8)
    log_text = tk.Text(log_lf, bg=BG, fg=FG, font=("Courier New", 9),
                       height=8, relief="flat", wrap="word",
                       insertbackground=FG, state="disabled")
    log_scroll = ttk.Scrollbar(log_lf, command=log_text.yview)
    log_text.configure(yscrollcommand=log_scroll.set)
    log_text.pack(side="left", fill="both", expand=True, padx=4, pady=4)
    log_scroll.pack(side="right", fill="y", pady=4)
    log_text.tag_configure("ok",   foreground=ACCENT2)
    log_text.tag_configure("warn", foreground="#fab387")
    log_text.tag_configure("err",  foreground=WARN)
    log_text.tag_configure("info", foreground=FG)

    _orig_stdout = sys.stdout

    class _LogRedirect:
        def write(self, s):
            _orig_stdout.write(s)
            if s.strip():
                tag = ("warn" if "WARNING" in s
                       else "err"  if ("ERROR" in s or "SKIP" in s)
                       else "ok"   if ("written" in s.lower() or "complete" in s.lower())
                       else "info")
                log_text.configure(state="normal")
                log_text.insert("end", s if s.endswith("\n") else s + "\n", tag)
                log_text.see("end")
                log_text.configure(state="disabled")
                root.update_idletasks()
        def flush(self): _orig_stdout.flush()

    sys.stdout = _LogRedirect()

    # ── Run conversion ────────────────────────────────────────────────────────
    def _on_run():
        log_text.configure(state="normal")
        log_text.delete("1.0", "end")
        log_text.configure(state="disabled")
        if mode_var.get() == "wdf":
            _run_conversion_wdf(
                state, frames, var_hdf5, var_json, var_csv,
                progress_var, progress_bar, root
            )
        else:
            _run_conversion_txt(
                state, frames, var_hdf5, var_json, var_csv,
                progress_var, progress_bar, root
            )


    btn_frame = tk.Frame(scroll_frame, bg=BG)
    btn_frame.pack(pady=12)
    tk.Button(
        btn_frame, text="\u25b6  Run conversion",
        bg=ACCENT2, fg=BG, font=("Courier New", 12, "bold"),
        relief="flat", cursor="hand2", padx=24, pady=8,
        command=_on_run,
        activebackground=ACCENT, activeforeground=BG,
    ).pack()

    root.mainloop()
    sys.stdout = _orig_stdout

if __name__ == "__main__":
    launch_gui()
