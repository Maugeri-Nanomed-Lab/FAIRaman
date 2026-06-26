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
# ── FAIRaman Version ──────────────────────────────────────────────────────────
# Update this number at every significant modify of the code
# It is automatically putted in HDF5 files under the voice Verison FAIRaman

FAIRAMAN_VERSION = "1.3"

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
            "project_name", "project_id", "funding", "governance_reference", "author", "author_id",
            "data_license", "accessibility", "keywords"
        ]
    },
    "SAMPLE": {
        "NX_class": "NXsample",
        "fields": ["sample_id"],
        "subgroups": {
            "SAMPLE_INFO": {
                "fields": [
                    "sample_provenance", "sample_type", "detailed_sample_type", "sample_source",
                    "anatomical_site", "anatomical_site_code", "anatomical_ontology",
                    "storage_temperature", "processing_method",
                    "sample_creation_date", "sample_notes"
                ]
            },
            "SAMPLE_DONOR": {
                "fields": [
                    "donor_id", "donor_sex", "donor_age", "diagnosis_code",
                    "diagnosis_ontology", "diagnosis_notes"
                ]
            },
            "SAMPLE_EVENT": {
                "fields": [
                    "event_date", "event_description"
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
                        "fields": ["wavelength", "wavelength_units", "power", "power_units",  "filter"]
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
# METADATA MAPPING FIRST GUESS
# ─────────────────────────────────────────────────────────────────────────────

def _normalise_mapping_key(s: str) -> str:
    """
    Normalizza nomi di campo per confronti robusti:
    - minuscolo
    - rimuove spazi, underscore, trattini, punti, parentesi
    - gestisce differenze banali tra Excel/TXT e HDF5 paths

    Esempi:
        'sample_id'       → 'sampleid'
        'Sample ID'       → 'sampleid'
        'SAMPLE.sample_id'→ 'samplesampleid'
    """
    import unicodedata

    s = "" if s is None else str(s)
    s = unicodedata.normalize("NFKD", s)
    s = s.encode("ascii", "ignore").decode("ascii")
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s


def _build_hdf5_mapping_lookup() -> tuple[dict, dict]:
    """
    Costruisce due lookup:
    1) full_lookup: match su path completo o path con underscore
       es. ENTRY.instrument.laser.wavelength
    2) basename_lookup: match sul nome finale del campo
       es. wavelength, sample_id, diagnosis_code

    Il basename viene usato solo se non ambiguo.
    """
    full_lookup: dict[str, str] = {}
    basename_lookup: dict[str, list[str]] = {}

    for path in HDF5_FIELDS:
        if path == "Do not map":
            continue

        # Match su path completo
        variants = {
            path,
            path.replace(".", "_"),
            path.replace(".", " "),
        }

        for variant in variants:
            full_lookup[_normalise_mapping_key(variant)] = path

        # Match sul solo field finale
        basename = path.split(".")[-1]
        basename_key = _normalise_mapping_key(basename)
        basename_lookup.setdefault(basename_key, []).append(path)

    return full_lookup, basename_lookup


_HDF5_FULL_LOOKUP, _HDF5_BASENAME_LOOKUP = _build_hdf5_mapping_lookup()


# Alias pragmatici per nomi frequenti in TXT/Excel.
# Le chiavi vengono normalizzate con _normalise_mapping_key().
_METADATA_ALIASES_RAW = {
    # ── Project / investigation ───────────────────────────────────────────────
    "project": "PROJECT.project_name",
    "projectname": "PROJECT.project_name",
    "project_name": "PROJECT.project_name",
    "study": "PROJECT.project_name",
    "studyname": "PROJECT.project_name",
    "study_name": "PROJECT.project_name",

    "projectid": "PROJECT.project_id",
    "project_id": "PROJECT.project_id",
    "studyid": "PROJECT.project_id",
    "study_id": "PROJECT.project_id",

    "funding": "PROJECT.funding",
    "grant": "PROJECT.funding",

    "governance": "PROJECT.governance_reference",
    "governancereference": "PROJECT.governance_reference",
    "governance_reference": "PROJECT.governance_reference",

    "author": "PROJECT.author",
    "dataauthor": "PROJECT.author",
    "data_author": "PROJECT.author",

    "orcid": "PROJECT.author_id",
    "authorid": "PROJECT.author_id",
    "author_id": "PROJECT.author_id",

    "license": "PROJECT.data_license",
    "licence": "PROJECT.data_license",
    "data_license": "PROJECT.data_license",
    "datalicense": "PROJECT.data_license",

    "access": "PROJECT.accessibility",
    "accessibility": "PROJECT.accessibility",

    "keywords": "PROJECT.keywords",
    "keyword": "PROJECT.keywords",

    # ── Sample ────────────────────────────────────────────────────────────────
    "sample": "SAMPLE.sample_id",
    "sampleid": "SAMPLE.sample_id",
    "sample_id": "SAMPLE.sample_id",
    "idcampione": "SAMPLE.sample_id",
    "campione": "SAMPLE.sample_id",

    "sampleprovenance": "SAMPLE.SAMPLE_INFO.sample_provenance",
    "sample_provenance": "SAMPLE.SAMPLE_INFO.sample_provenance",
    "provenance": "SAMPLE.SAMPLE_INFO.sample_provenance",

    "sampletype": "SAMPLE.SAMPLE_INFO.sample_type",
    "sample_type": "SAMPLE.SAMPLE_INFO.sample_type",
    "tipo_campione": "SAMPLE.SAMPLE_INFO.sample_type",
    "tipocampione": "SAMPLE.SAMPLE_INFO.sample_type",

    "detailedsampletype": "SAMPLE.SAMPLE_INFO.detailed_sample_type",
    "detailed_sample_type": "SAMPLE.SAMPLE_INFO.detailed_sample_type",

    "samplesource": "SAMPLE.SAMPLE_INFO.sample_source",
    "sample_source": "SAMPLE.SAMPLE_INFO.sample_source",

    "anatomicalsite": "SAMPLE.SAMPLE_INFO.anatomical_site",
    "anatomical_site": "SAMPLE.SAMPLE_INFO.anatomical_site",
    "site": "SAMPLE.SAMPLE_INFO.anatomical_site",
    "tissue": "SAMPLE.SAMPLE_INFO.anatomical_site",
    "tessuto": "SAMPLE.SAMPLE_INFO.anatomical_site",

    "anatomicalsitecode": "SAMPLE.SAMPLE_INFO.anatomical_site_code",
    "anatomical_site_code": "SAMPLE.SAMPLE_INFO.anatomical_site_code",
    "uberon": "SAMPLE.SAMPLE_INFO.anatomical_site_code",
    "uberonid": "SAMPLE.SAMPLE_INFO.anatomical_site_code",
    "uberon_id": "SAMPLE.SAMPLE_INFO.anatomical_site_code",

    "anatomicalontology": "SAMPLE.SAMPLE_INFO.anatomical_ontology",
    "anatomical_ontology": "SAMPLE.SAMPLE_INFO.anatomical_ontology",

    "storagetemperature": "SAMPLE.SAMPLE_INFO.storage_temperature",
    "storage_temperature": "SAMPLE.SAMPLE_INFO.storage_temperature",
    "temperature": "SAMPLE.SAMPLE_INFO.storage_temperature",

    "processingmethod": "SAMPLE.SAMPLE_INFO.processing_method",
    "processing_method": "SAMPLE.SAMPLE_INFO.processing_method",
    "protocol": "SAMPLE.SAMPLE_INFO.processing_method",

    "samplecreationdate": "SAMPLE.SAMPLE_INFO.sample_creation_date",
    "sample_creation_date": "SAMPLE.SAMPLE_INFO.sample_creation_date",

    "samplenotes": "SAMPLE.SAMPLE_INFO.sample_notes",
    "sample_notes": "SAMPLE.SAMPLE_INFO.sample_notes",
    "notes": "SAMPLE.SAMPLE_INFO.sample_notes",

    # ── Donor / diagnosis ─────────────────────────────────────────────────────
    "donor": "SAMPLE.SAMPLE_DONOR.donor_id",
    "donorid": "SAMPLE.SAMPLE_DONOR.donor_id",
    "donor_id": "SAMPLE.SAMPLE_DONOR.donor_id",
    "patient": "SAMPLE.SAMPLE_DONOR.donor_id",
    "patientid": "SAMPLE.SAMPLE_DONOR.donor_id",
    "patient_id": "SAMPLE.SAMPLE_DONOR.donor_id",
    "paziente": "SAMPLE.SAMPLE_DONOR.donor_id",

    "sex": "SAMPLE.SAMPLE_DONOR.donor_sex",
    "sesso": "SAMPLE.SAMPLE_DONOR.donor_sex",
    "donorsex": "SAMPLE.SAMPLE_DONOR.donor_sex",
    "donor_sex": "SAMPLE.SAMPLE_DONOR.donor_sex",

    "age": "SAMPLE.SAMPLE_DONOR.donor_age",
    "eta": "SAMPLE.SAMPLE_DONOR.donor_age",
    "donorage": "SAMPLE.SAMPLE_DONOR.donor_age",
    "donor_age": "SAMPLE.SAMPLE_DONOR.donor_age",

    "diagnosis": "SAMPLE.SAMPLE_DONOR.diagnosis_notes",
    "diagnosi": "SAMPLE.SAMPLE_DONOR.diagnosis_notes",
    "diagnosisnotes": "SAMPLE.SAMPLE_DONOR.diagnosis_notes",
    "diagnosis_notes": "SAMPLE.SAMPLE_DONOR.diagnosis_notes",

    "diagnosiscode": "SAMPLE.SAMPLE_DONOR.diagnosis_code",
    "diagnosis_code": "SAMPLE.SAMPLE_DONOR.diagnosis_code",
    "icd10": "SAMPLE.SAMPLE_DONOR.diagnosis_code",
    "icd": "SAMPLE.SAMPLE_DONOR.diagnosis_code",

    "diagnosisontology": "SAMPLE.SAMPLE_DONOR.diagnosis_ontology",
    "diagnosis_ontology": "SAMPLE.SAMPLE_DONOR.diagnosis_ontology",

    # ── Sample event ──────────────────────────────────────────────────────────
    "eventdate": "SAMPLE.SAMPLE_EVENT.event_date",
    "event_date": "SAMPLE.SAMPLE_EVENT.event_date",
    "collectiondate": "SAMPLE.SAMPLE_EVENT.event_date",
    "collection_date": "SAMPLE.SAMPLE_EVENT.event_date",

    "eventdescription": "SAMPLE.SAMPLE_EVENT.event_description",
    "event_description": "SAMPLE.SAMPLE_EVENT.event_description",

    # ── Entry / measurement ───────────────────────────────────────────────────
    "title": "ENTRY.title",
    "experimenttype": "ENTRY.experiment_type",
    "experiment_type": "ENTRY.experiment_type",
    "runtype": "ENTRY.run_type",
    "run_type": "ENTRY.run_type",
    "starttime": "ENTRY.start_time",
    "start_time": "ENTRY.start_time",
    "datatype": "ENTRY.data_type",
    "data_type": "ENTRY.data_type",

    "exposure": "ENTRY.measurement.exposure_time",
    "exposuretime": "ENTRY.measurement.exposure_time",
    "exposure_time": "ENTRY.measurement.exposure_time",
    "integrationtime": "ENTRY.measurement.exposure_time",
    "integration_time": "ENTRY.measurement.exposure_time",

    "exposureunits": "ENTRY.measurement.exposure_time_units",
    "exposure_time_units": "ENTRY.measurement.exposure_time_units",
    "exposuretimeunits": "ENTRY.measurement.exposure_time_units",

    "substrate": "ENTRY.measurement.substrate",

    "accumulations": "ENTRY.measurement.accumulation_count",
    "accumulation": "ENTRY.measurement.accumulation_count",
    "accumulationcount": "ENTRY.measurement.accumulation_count",
    "accumulation_count": "ENTRY.measurement.accumulation_count",

    # ── Instrument ────────────────────────────────────────────────────────────
    "instrument": "ENTRY.instrument.name",
    "instrumentname": "ENTRY.instrument.name",
    "instrument_name": "ENTRY.instrument.name",
    "instrument_name": "ENTRY.instrument.name",

    "laser": "ENTRY.instrument.laser.wavelength",
    "laserwavelength": "ENTRY.instrument.laser.wavelength",
    "laser_wavelength": "ENTRY.instrument.laser.wavelength",
    "laser_nm": "ENTRY.instrument.laser.wavelength",
    "lasernm": "ENTRY.instrument.laser.wavelength",
    "wavelength": "ENTRY.instrument.laser.wavelength",

    "laserunits": "ENTRY.instrument.laser.wavelength_units",
    "laser_units": "ENTRY.instrument.laser.wavelength_units",
    "wavelengthunits": "ENTRY.instrument.laser.wavelength_units",
    "wavelength_units": "ENTRY.instrument.laser.wavelength_units",

    "power": "ENTRY.instrument.laser.power",
    "laserpower": "ENTRY.instrument.laser.power",
    "laser_power": "ENTRY.instrument.laser.power",

    "powerunits": "ENTRY.instrument.laser.power_units",
    "power_units": "ENTRY.instrument.laser.power_units",
    "laserpowerunits": "ENTRY.instrument.laser.power_units",
    "laser_power_units": "ENTRY.instrument.laser.power_units",

    "filter": "ENTRY.instrument.laser.filter",
    "laserfilter": "ENTRY.instrument.laser.filter",
    "laser_filter": "ENTRY.instrument.laser.filter",

    "lens": "ENTRY.instrument.optical_system.lens",
    "objective": "ENTRY.instrument.optical_system.lens",
    "obiettivo": "ENTRY.instrument.optical_system.lens",
}

_METADATA_ALIASES = {
    _normalise_mapping_key(k): v
    for k, v in _METADATA_ALIASES_RAW.items()
}


def _guess_hdf5_mapping(src_key: str) -> str:
    """
    Restituisce un first guess per la mappatura di un campo TXT/Excel
    verso un path HDF5.

    Strategia:
    1) se src_key è già un path HDF5 valido → usa quello
    2) alias pratici → usa mapping esplicito
    3) match normalizzato su path completo
    4) match normalizzato sul basename, solo se univoco
    5) altrimenti → "Do not map"

    La scelta resta modificabile nella GUI.
    """
    if src_key is None:
        return "Do not map"

    raw = str(src_key).strip()

    # Campi tecnici da NON mappare automaticamente
    technical_keys = {
        "file", "filename", "file_name", "filepath", "file_path",
        "wdf", "wdf_file", "spectrum_file", "spectral_file",
        "csv", "txt", "path", "folder",
    }
    if _normalise_mapping_key(raw) in {
        _normalise_mapping_key(k) for k in technical_keys
    }:
        return "Do not map"

    # 1) Path HDF5 già corretto
    if raw in HDF5_FIELDS:
        return raw

    norm = _normalise_mapping_key(raw)

    # 2) Alias manuali
    if norm in _METADATA_ALIASES:
        candidate = _METADATA_ALIASES[norm]
        if candidate in HDF5_FIELDS:
            return candidate

    # 3) Match su path completo normalizzato
    if norm in _HDF5_FULL_LOOKUP:
        return _HDF5_FULL_LOOKUP[norm]

    # 4) Match su basename, solo se non ambiguo
    basename_candidates = _HDF5_BASENAME_LOOKUP.get(norm, [])
    basename_candidates = list(dict.fromkeys(basename_candidates))

    if len(basename_candidates) == 1:
        return basename_candidates[0]

    return "Do not map"


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
# RENISHAW WDF IMPORTER (requires renishawWiRE)
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

def _read_renishaw_geometry(reader) -> dict:
    """
    Estrae la geometria spaziale da un WDFReader, distinguendo griglia regolare
    da punti sparsi.

    WiRE popola xpos/ypos (blocchi ORGN) per OGNI spettro, anche sulle mappe
    regolari (srotolate row-major): la loro presenza NON distingue i due casi.
    Il discriminante è `map_shape`: se esiste e il suo prodotto combacia col
    numero di spettri, è una griglia rettangolare.

    NB: map_shape WiRE = (nx, ny), mentre spectra = (ny, nx, nw). Ordine invertito.

    Returns
    -------
    dict con:
      'kind'              : "grid" | "points" | "none"
      'nx','ny'           : per "grid"
      'x_axis','y_axis'   : per "grid" (µm, dagli ORGN se disponibili)
      'x','y'             : per "points" (µm, per-spettro)
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
    Importer Renishaw/WDF → dizionario canonico FAIRaman.

    Priorità geometrica (validata su file reali):
      GRID    map_shape coerente col n. spettri → regular_grid, cubo 3D,
              assi in µm dagli ORGN reali.
      POINTS  coordinate ORGN per-punto, geometria non a griglia → point_coordinates
              (es. microplastiche, ROI morfologiche, spot manuali).
      NONE    nessuna coordinata reale → synthetic / index.

    Nome concettuale futuro: import_renishaw_wdf. Mantenuto process_wdf per
    retrocompatibilità con la pipeline di conversione.
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

# ─────────────────────────────────────────────────────────────────────────────
# ASCII / CSV SPECTRAL IMPORTER
# ─────────────────────────────────────────────────────────────────────────────

def process_txt_spectrum(txt_path: Path) -> dict:
    """
    Importer ASCII/CSV → dizionario canonico FAIRaman.

    Formati supportati
    ------------------
    1) Spettro singolo:
       raman_shift | intensity

       Output:
       regular_grid 1×1
       cube shape = (1, 1, n_wavenumbers)
       x_axis = [0.0], y_axis = [0.0]
       coordinate_source = "synthetic"
       coordinate_units = "micrometers"
       coordinate_validated = False

    2) Matrice multi-spettro senza coordinate:
       raman_shift | spectrum_1 | spectrum_2 | ... | spectrum_n

       Output:
       regular_grid 1×n
       cube shape = (1, n_spectra, n_wavenumbers)
       x_axis = [0.0, 1.0, 2.0, ...]
       y_axis = [0.0]
       coordinate_source = "synthetic"
       coordinate_units = "micrometers"
       coordinate_validated = False

    3) Formato spaziale long:
       x | y | raman_shift | intensity

       Ogni riga rappresenta un singolo valore spettrale in una posizione (x, y).
       FAIRaman ricostruisce uno spettro per ogni coppia x/y.

    4) Formato spaziale wide con header:
       x | y | 800 | 801 | 802 | ...

       Le colonne dalla terza in poi sono intensità Raman; gli header numerici
       sono i Raman shift.

    Convenzione FAIRaman
    --------------------
    Tutte le coordinate x/y sono espresse in micrometri.

    Se il file non contiene coordinate fisiche, FAIRaman genera coordinate
    sintetiche in micrometri solo per mantenere una struttura HDF5 compatibile.
    In questi casi:
       coordinate_source = "synthetic"
       coordinate_validated = False
    """

    def _base_output() -> dict:
        """Crea il dizionario canonico base per un importer ASCII/CSV."""
        instrument_meta = {
            "laser_wavelength": 0.0,
            "x_start": 0.0,
            "y_start": 0.0,
            "x_step": 0.0,
            "y_step": 0.0,
        }

        out = _canonical_defaults()
        out.update({
            "cube":             None,
            "spectra":          None,
            "raman_shift":      None,
            "x_axis":           None,
            "y_axis":           None,
            "x":                None,
            "y":                None,
            "white_light":      None,
            "white_light_meta": None,
            "acquisition_map":  None,
            "instrument":       instrument_meta,
            "filename":         txt_path.name,
            "source_format":    "txt",
        })
        return out

    def _read_ascii_table(path: Path) -> pd.DataFrame:
        """
        Legge una tabella ASCII/CSV provando delimitatori comuni.
        Usa header=None per poter riconoscere anche header numerici dei Raman shift.
        """
        for sep in [r"\s+", ",", ";", "\t"]:
            try:
                df = pd.read_csv(
                    path,
                    comment="#",
                    sep=sep,
                    header=None,
                    engine="python",
                )
                df = df.dropna(how="all").dropna(axis=1, how="all")

                if df.shape[0] > 0 and df.shape[1] >= 2:
                    return df

            except Exception:
                continue

        raise ValueError(
            f"Could not parse '{path.name}': no supported delimiter found "
            f"(tried whitespace, comma, semicolon, tab)."
        )

    def _sort_by_raman_shift(
        raman_shift: np.ndarray,
        spectra: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Ordina l'asse Raman in ordine crescente.

        Parameters
        ----------
        raman_shift
            Array shape = (n_wavenumbers,)
        spectra
            Array shape = (n_spectra, n_wavenumbers)
        """
        raman_shift = np.asarray(raman_shift, dtype=np.float64)
        spectra = np.asarray(spectra, dtype=np.float64)

        if spectra.ndim != 2:
            raise ValueError(f"spectra must be 2D, detected shape {spectra.shape}")

        if spectra.shape[1] != len(raman_shift):
            raise ValueError(
                f"spectra second dimension must match raman_shift length "
                f"({spectra.shape[1]} != {len(raman_shift)})"
            )

        sort_idx = np.argsort(raman_shift)
        return raman_shift[sort_idx], spectra[:, sort_idx]

    def _as_regular_grid_from_axes(
        raman_shift: np.ndarray,
        cube: np.ndarray,
        x_axis: np.ndarray,
        y_axis: np.ndarray,
        coordinate_source: str,
        coordinate_validated: bool,
        reshape_applied: bool,
        reshape_source: str,
    ) -> dict:
        """
        Costruisce un output canonico regular_grid.
        """
        out = _base_output()

        out.update({
            "cube":                 np.asarray(cube, dtype=np.float64),
            "spectra":              None,
            "raman_shift":          np.asarray(raman_shift, dtype=np.float64),
            "x_axis":               np.asarray(x_axis, dtype=np.float64),
            "y_axis":               np.asarray(y_axis, dtype=np.float64),
            "x":                    None,
            "y":                    None,
            "coordinate_mode":      COORDINATE_MODE_REGULAR,
            "coordinate_source":    coordinate_source,
            "coordinate_units":     "micrometers",
            "coordinate_validated": bool(coordinate_validated),
            "reshape_applied":      bool(reshape_applied),
            "reshape_source":       reshape_source,
        })

        return out

    def _as_points(
        raman_shift: np.ndarray,
        spectra: np.ndarray,
        x: np.ndarray,
        y: np.ndarray,
        coordinate_source: str,
        coordinate_validated: bool,
    ) -> dict:
        """
        Costruisce un output canonico point_coordinates.
        Usato solo quando x/y reali non formano una griglia completa.
        """
        out = _base_output()

        out.update({
            "cube":                 None,
            "spectra":              np.asarray(spectra, dtype=np.float64),
            "raman_shift":          np.asarray(raman_shift, dtype=np.float64),
            "x_axis":               None,
            "y_axis":               None,
            "x":                    np.asarray(x, dtype=np.float64),
            "y":                    np.asarray(y, dtype=np.float64),
            "coordinate_mode":      COORDINATE_MODE_POINTS,
            "coordinate_source":    coordinate_source,
            "coordinate_units":     "micrometers",
            "coordinate_validated": bool(coordinate_validated),
            "reshape_applied":      False,
            "reshape_source":       "none",
        })

        return out

    def _grid_or_points_from_xy(
        raman_shift: np.ndarray,
        spectra: np.ndarray,
        x: np.ndarray,
        y: np.ndarray,
        coordinate_source: str,
    ) -> dict:
        """
        Decide se coordinate x/y rappresentano una griglia completa o punti sparsi.

        Se tutte le combinazioni x_unique × y_unique sono presenti una sola volta,
        il dato viene salvato come regular_grid.

        Altrimenti viene salvato come point_coordinates, conservando x/y per-spettro.
        """
        raman_shift = np.asarray(raman_shift, dtype=np.float64)
        spectra = np.asarray(spectra, dtype=np.float64)
        x = np.asarray(x, dtype=np.float64).ravel()
        y = np.asarray(y, dtype=np.float64).ravel()

        if spectra.ndim != 2:
            raise ValueError(f"spectra must be 2D, detected shape {spectra.shape}")

        n_points, n_wavenumbers = spectra.shape

        if len(raman_shift) != n_wavenumbers:
            raise ValueError(
                f"len(raman_shift) != spectra.shape[1] "
                f"({len(raman_shift)} != {n_wavenumbers})"
            )

        if x.size != n_points or y.size != n_points:
            raise ValueError(
                f"x/y coordinates do not match spectra count: "
                f"len(x)={x.size}, len(y)={y.size}, n_spectra={n_points}"
            )

        coord_df = pd.DataFrame({
            "x": x,
            "y": y,
            "idx": np.arange(n_points),
        })

        if coord_df.duplicated(["x", "y"]).any():
            duplicated = coord_df[coord_df.duplicated(["x", "y"], keep=False)]
            raise ValueError(
                f"Duplicate x/y coordinates found in '{txt_path.name}'. "
                f"Duplicated rows: {duplicated[['x', 'y']].head().to_dict('records')}"
            )

        x_unique = np.sort(np.unique(x))
        y_unique = np.sort(np.unique(y))

        is_complete_grid = (
            len(x_unique) > 1
            and len(y_unique) > 1
            and len(x_unique) * len(y_unique) == n_points
        )

        if is_complete_grid:
            complete_index = pd.MultiIndex.from_product(
                [y_unique, x_unique],
                names=["y", "x"],
            )

            ordered = (
                coord_df
                .set_index(["y", "x"])
                .reindex(complete_index)
            )

            if not ordered["idx"].isna().any():
                order = ordered["idx"].astype(int).to_numpy()

                cube = spectra[order, :].reshape(
                    len(y_unique),
                    len(x_unique),
                    len(raman_shift),
                )

                return _as_regular_grid_from_axes(
                    raman_shift=raman_shift,
                    cube=cube,
                    x_axis=x_unique,
                    y_axis=y_unique,
                    coordinate_source=coordinate_source,
                    coordinate_validated=True,
                    reshape_applied=True,
                    reshape_source="ASCII x/y grid",
                )

        return _as_points(
            raman_shift=raman_shift,
            spectra=spectra,
            x=x,
            y=y,
            coordinate_source=coordinate_source,
            coordinate_validated=True,
        )

    # ── Lettura tabella ───────────────────────────────────────────────────────
    df_raw = _read_ascii_table(txt_path)
    df_num = df_raw.apply(pd.to_numeric, errors="coerce")

    # ── CASE 4: wide spatial format con header ────────────────────────────────
    # Esempio:
    #   x,y,800,801,802
    #   0,0,10,11,12
    #   1,0,13,14,15
    #
    # Con header=None + to_numeric:
    #   prima riga = NaN, NaN, 800, 801, 802
    if df_num.shape[0] >= 2 and df_num.shape[1] >= 4:
        first_row = df_num.iloc[0, :]

        looks_like_wide_spatial_header = (
            pd.isna(first_row.iloc[0])
            and pd.isna(first_row.iloc[1])
            and first_row.iloc[2:].notna().all()
        )

        if looks_like_wide_spatial_header:
            raman_shift = first_row.iloc[2:].to_numpy(dtype=np.float64)
            body = df_num.iloc[1:, :].dropna(how="all")

            if body.isna().any().any():
                raise ValueError(
                    f"'{txt_path.name}' looks like wide spatial ASCII/CSV with "
                    f"header, but some numeric values are missing."
                )

            x = body.iloc[:, 0].to_numpy(dtype=np.float64)
            y = body.iloc[:, 1].to_numpy(dtype=np.float64)
            spectra = body.iloc[:, 2:].to_numpy(dtype=np.float64)

            raman_shift, spectra = _sort_by_raman_shift(raman_shift, spectra)

            return _grid_or_points_from_xy(
                raman_shift=raman_shift,
                spectra=spectra,
                x=x,
                y=y,
                coordinate_source="ASCII x/y columns + Raman-shift header",
            )

    # Da qui in avanti usiamo solo righe completamente numeriche.
    df_clean = df_num.dropna(how="all").dropna(axis=0, how="any")

    if df_clean.empty:
        raise ValueError(
            f"'{txt_path.name}' does not contain a usable numeric table."
        )

    arr = df_clean.to_numpy(dtype=np.float64)

    if arr.ndim != 2 or arr.shape[1] < 2:
        raise ValueError(
            f"'{txt_path.name}' must contain at least two numeric columns. "
            f"Detected shape: {arr.shape}."
        )

    # ── CASE 3: long spatial format x | y | raman_shift | intensity ───────────
    # Esempio:
    #   x,y,raman_shift,intensity
    #   0,0,800,10
    #   0,0,801,11
    #   1,0,800,13
    #   1,0,801,14
    if arr.shape[1] >= 4:
        x_col = arr[:, 0]
        y_col = arr[:, 1]
        wn_col = arr[:, 2]
        intensity_col = arr[:, 3]

        point_df = pd.DataFrame({"x": x_col, "y": y_col})
        n_points = point_df.drop_duplicates().shape[0]
        n_wavenumbers = np.unique(wn_col).size

        looks_like_long_spatial = (
            n_points > 1
            and n_wavenumbers > 1
            and n_points * n_wavenumbers == arr.shape[0]
        )

        if looks_like_long_spatial:
            long_df = pd.DataFrame({
                "x": x_col,
                "y": y_col,
                "raman_shift": wn_col,
                "intensity": intensity_col,
            })

            if long_df.duplicated(["x", "y", "raman_shift"]).any():
                duplicated = long_df[
                    long_df.duplicated(["x", "y", "raman_shift"], keep=False)
                ]
                raise ValueError(
                    f"Duplicate x/y/raman_shift rows found in '{txt_path.name}'. "
                    f"Duplicated rows: "
                    f"{duplicated[['x', 'y', 'raman_shift']].head().to_dict('records')}"
                )

            pivot = long_df.pivot(
                index=["y", "x"],
                columns="raman_shift",
                values="intensity",
            )

            pivot = pivot.reindex(sorted(pivot.columns), axis=1)

            if pivot.isna().any().any():
                raise ValueError(
                    f"'{txt_path.name}' looks like long spatial ASCII/CSV "
                    f"(x, y, raman_shift, intensity), but the x/y × Raman grid "
                    f"is incomplete."
                )

            raman_shift = pivot.columns.to_numpy(dtype=np.float64)
            spectra = pivot.to_numpy(dtype=np.float64)
            y = pivot.index.get_level_values("y").to_numpy(dtype=np.float64)
            x = pivot.index.get_level_values("x").to_numpy(dtype=np.float64)

            raman_shift, spectra = _sort_by_raman_shift(raman_shift, spectra)

            return _grid_or_points_from_xy(
                raman_shift=raman_shift,
                spectra=spectra,
                x=x,
                y=y,
                coordinate_source="ASCII x/y/raman_shift/intensity columns",
            )

    # ── CASE 1: single spectrum raman_shift | intensity ───────────────────────
    if arr.shape[1] == 2:
        raman_shift = arr[:, 0].astype(np.float64)
        intensity = arr[:, 1].astype(np.float64).reshape(1, -1)

        raman_shift, spectra = _sort_by_raman_shift(raman_shift, intensity)

        cube = spectra.reshape(1, 1, -1)

        return _as_regular_grid_from_axes(
            raman_shift=raman_shift,
            cube=cube,
            x_axis=np.array([0.0]),
            y_axis=np.array([0.0]),
            coordinate_source="synthetic",
            coordinate_validated=False,
            reshape_applied=True,
            reshape_source="ASCII single spectrum as 1x1 map",
        )

    # ── CASE 2: matrix raman_shift | spectrum_1 | spectrum_2 | ... ────────────
    # Esempio:
    #   800  10  11  15
    #   801  12  13  16
    #   802  14  15  18
    #
    # Nessuna coordinata reale: salviamo come mappa sintetica 1×n.
    raman_shift = arr[:, 0].astype(np.float64)
    spectra = arr[:, 1:].T.astype(np.float64)

    raman_shift, spectra = _sort_by_raman_shift(raman_shift, spectra)

    n_spectra = spectra.shape[0]
    cube = spectra.reshape(1, n_spectra, -1)

    return _as_regular_grid_from_axes(
        raman_shift=raman_shift,
        cube=cube,
        x_axis=np.arange(n_spectra, dtype=float),
        y_axis=np.array([0.0]),
        coordinate_source="synthetic",
        coordinate_validated=False,
        reshape_applied=True,
        reshape_source="ASCII matrix as 1xn map",
    )


# ─────────────────────────────────────────────────────────────────────────────
# FUTURE RAMANSPY ADAPTER (optional dependency)
# ─────────────────────────────────────────────────────────────────────────────
# RamanSPy NON sostituisce renishawWiRE per i WDF: la sua load.renishaw() è essa
# stessa basata su renishawWiRE e, normalizzando a SpectralImage/Container,
# SCARTA xpos/ypos, map_shape, white-light e laser. Per il WDF si usa quindi
# l'importer diretto sopra. RamanSPy resta utile SOLO per formati che FAIRaman
# non parsa nativamente (Horiba .spe, WiTec .wip, MATLAB .mat), dove fornisce
# loader già pronti.
#
# Quando servirà, implementare:
#   def import_via_ramanspy(path: Path) -> dict:
#       import ramanspy as rp
#       obj = rp.load.<loader>(str(path))
#       # mappare obj.spectral_data / obj.spectral_axis sul dizionario canonico,
#       # impostando coordinate_mode in base alla dimensionalità del container e
#       # coordinate_source = "RamanSPy" / coordinate_validated = False se le
#       # coordinate fisiche non sono recuperabili dal container.
#       ...
# ─────────────────────────────────────────────────────────────────────────────





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
            data_grp.attrs["signal"] = "spectra"
            data_grp.attrs["axes"]   = ["point_id", "raman_shift"]
            data_grp.create_dataset(
                "spectra", data=spec, compression="gzip", chunks=True
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

# ─────────────────────────────────────────────────────────────────────────────
# EXPORT: CSV AND JSON SIDECAR
# ─────────────────────────────────────────────────────────────────────────────

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
                         title: str, use_first_guess: bool = True) -> tk.LabelFrame:
    
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

        if use_first_guess:
            guess = _guess_hdf5_mapping(key)
            if guess in HDF5_FIELDS:
                cb.set(guess)

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
