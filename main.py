"""
FAIRaman: A MIABIS-Compliant HDF5 Generator

FAIRaman converts raw Raman spectral data (WDF or ASCII format)
into self-describing HDF5/NeXus files that include both
instrument metadata and biological sample information,
compliant with the MIABIS standard and biomedical ontologies
(UBERON, ICD-10).

Design Rationale
----------------
Existing FAIR tools for Raman spectroscopy (e.g., ramanchada2)
primarily focus on the instrument:
they provide an excellent description of the acquisition hardware,
but do not represent the biological sample under investigation.

In clinical and translational research, however, the sample itself—
its tissue of origin, pathological status, donor characteristics,
and biobank information—is fundamental to data interpretation.
These metadata are essential for interoperability and for compliance
with current European biobanking guidelines.

FAIRaman therefore organizes metadata into three complementary levels:

  * Project   — project information, data governance, keywords
  * Sample    — donor information, diagnosis (ICD-10), anatomical site (UBERON),
                and biobank-related metadata compliant with MIABIS
  * Measurement — acquisition parameters, laser configuration,
                  and optical system metadata compliant with
                  NXraman/NXinstrument

This three-level hierarchy enables the integration of datasets
acquired using different instruments and experimental workflows,
facilitating multicenter machine learning studies for Raman-based
biomarker discovery.

Supported Spectral Input Formats
--------------------------------
* Renishaw WDF (.wdf)  — full spectral cube with white-light image
* ASCII two-column     — wavenumber (cm⁻¹) | intensity
                         (tab-, space-, CSV-, or DAT-separated)

Output Formats
--------------
* HDF5/NeXus (.h5)     — primary FAIR output compliant with NXraman
* JSON                 — human-readable metadata
* CSV                  — exported spectral matrices

Standards and Ontologies
------------------------
* NeXus / NXraman     (https://manual.nexusformat.org)
* MIABIS v3           (https://github.com/BBMRI-ERIC/miabis)
* UBERON Ontology     (https://www.ebi.ac.uk/ols/ontologies/uberon)
* ICD-10              (https://icd.who.int)
* FAIR Principles     (Wilkinson et al., Scientific Data, 2016)

Dependencies
------------
Required:
    numpy, pandas, h5py, Pillow, matplotlib

Optional:
    renishawWiRE
    (required only for WDF support;
    install with: pip install renishawWiRE)

Author
------
Davide Piccapietra

License
-------
MIT License — see the LICENSE file for details.

References
----------
Wilkinson, M.D. et al. (2016).
The FAIR Guiding Principles for scientific data management and stewardship.
Scientific Data, 3, 160018.

Schober, P. & Vetter, T.R. (2019).
MIABIS: Minimum Information About BIobank Data Sharing.
Biopreservation and Biobanking.
"""

# ── FAIRaman Version ──────────────────────────────────────────────────────────
# Update this number at every significant modify of the code
# It is automatically putted in HDF5 files under the voice Verison FAIRaman

FAIRAMAN_VERSION = "1.4"

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

from fairaman.schema import NEXUS_SCHEMA, flatten_schema, HDF5_FIELDS
from fairaman.utility import NumpyEncoder, parse_txt_metadata
from fairaman.readers import wdf_reader, ascii_reader
from fairaman.metadata_management import _normalise_stem, _assemble_flat_data, \
    _get_excel_row, _load_metadata_sources, _assemble_flat_data
from fairaman.writers  import hdf5_writer
from fairaman.gui import _pick_path, launch_gui, _create_filterable_combobox, _build_mapping_frame, _show_ontology_help
from fairaman.conversion import wdf_pipeline, ascii_pipeline
from fairaman.writers.hdf5_writer import write_hdf5_nexus

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

if __name__ == "__main__":
    launch_gui()
