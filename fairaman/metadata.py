"""
Metadata parsing utilities for FAIRaman.
"""
from pathlib import Path
import json
import numpy as np

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

def parse_txt_metadata(path: Path) -> dict[str, str]:
    """
    Parse a TXT metadata file containing one ``key: value`` pair per line.

    Empty lines and lines beginning with ``#`` are ignored.

    Parameters
    ----------
    path
        Path to the metadata TXT file.

    Returns
    -------
    dict[str, str]
        Mapping between metadata field names and string values.
    """
    metadata: dict[str, str] = {}

    with path.open(
        mode="r",
        encoding="utf-8",
        errors="replace",
    ) as file:
        for line_number, raw_line in enumerate(file, start=1):
            line = raw_line.strip()

            if not line or line.startswith("#"):
                continue

            if ":" not in line:
                print(
                    "[FAIRaman] WARNING: "
                    f"ignored metadata line {line_number}: missing ':'"
                )
                continue

            key, value = (
                part.strip()
                for part in line.split(":", 1)
            )

            if not key:
                print(
                    "[FAIRaman] WARNING: "
                    f"ignored metadata line {line_number}: empty key"
                )
                continue

            if key in metadata:
                print(
                    "[FAIRaman] WARNING: "
                    f"duplicate metadata key '{key}' on line "
                    f"{line_number}; last value used"
                )

            metadata[key] = value

    return metadata

