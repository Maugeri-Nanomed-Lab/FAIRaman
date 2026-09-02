
# ─────────────────────────────────────────────────────────────────────────────
# UTILITY CLASSES AND FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

import json
from pathlib import Path
import numpy as np
import pandas as pd

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