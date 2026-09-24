"""
FAIRaman: A MIABIS-Compliant HDF5 Generator for Raman spectroscopy data.

Public API
-----------
Importing `fairaman` gives you direct access to the most commonly used
readers, pure conversion functions, and writers, without needing to know
the internal module layout.

For programmatic use (scripts, notebooks, other GUIs), prefer the pure
`convert_wdf_batch` / `convert_ascii_batch` functions over the GUI-bound
`run_conversion_wdf` / `run_conversion_txt` wrappers.
"""

# ── Package version ────────────────────────────────────────────────────────
# Single source of truth for the version. Bump this on every release.
__version__ = "1.4"

# Keep this name too, since the codebase references FAIRAMAN_VERSION
# in several places (e.g. written into HDF5 metadata).
FAIRAMAN_VERSION = __version__

# ── Public API ────────────────────────────────────────────────────────────
# Import only what you want users to access directly as `fairaman.X`
# or `from fairaman import X`. Keep internal helpers (utility, gui internals,
# metadata_management, etc.) out of this list — they stay accessible via
# their full path but aren't "advertised".

# Readers — parse raw spectral files into the canonical dictionary
from fairaman.readers.wdf_reader import process_wdf
from fairaman.readers.ascii_reader import process_txt_spectrum

# Conversion — pure batch pipelines (no GUI dependency)
from fairaman.conversion.wdf_pipeline import convert_wdf_batch, ConversionResult
from fairaman.conversion.ascii_pipeline import convert_ascii_batch

# Conversion — GUI wrappers (require Tkinter state/widgets)
from fairaman.conversion.wdf_pipeline import run_conversion_wdf
from fairaman.conversion.ascii_pipeline import run_conversion_txt

# Writers
from fairaman.writers.hdf5_writer import write_hdf5_nexus, export_json, export_csv

# Schema
from fairaman.schema import NEXUS_SCHEMA

# ── What `from fairaman import *` will expose ──────────────────────────────
__all__ = [
    "__version__",
    "FAIRAMAN_VERSION",
    # readers
    "process_wdf",
    "process_txt_spectrum",
    # pure conversion
    "convert_wdf_batch",
    "convert_ascii_batch",
    "ConversionResult",
    # GUI conversion
    "run_conversion_wdf",
    "run_conversion_txt",
    # writers
    "write_hdf5_nexus",
    "export_json",
    "export_csv",
    # schema
    "NEXUS_SCHEMA",
]