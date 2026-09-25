
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