
# ─────────────────────────────────────────────────────────────────────────────
# UTILITY CLASSES AND FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

import json
from pathlib import Path
import numpy as np
import pandas as pd

class NumpyEncoder(json.JSONEncoder):
    """
    JSON encoder that serializes NumPy scalar types and arrays 

    NumPy integers and floats are converted to native Python types; 
    arrays are converted to lists. Required for metadata containing NumPy values read from WDF or Excel
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
    Analyzes a metadata file in .txt format and converts it into a key–value dictionary

    The expected format is ``key: value`` per line
    Lines starting with ``#`` and empty lines are ignored

    Parameters
    ----------
    path : Path
        Path to the TXT file containing the metadata

    Returns
    -------
    dict
        Dictionary that associates field names with their values as strings

    Notes
    -----
    Even keys that start with ``#``—after removing any leading spaces—
    are

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