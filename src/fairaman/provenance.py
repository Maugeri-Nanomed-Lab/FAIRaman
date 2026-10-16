"""
Source-file provenance for FAIRaman.

ENTRY/HASH is the SHA-256 checksum of the complete binary content of the
original input file. It does not depend on file name, location, modification
date or FAIRaman version, and can be recomputed with standard tools.
"""

import hashlib
from pathlib import Path

HASH_ALGORITHM = "sha256"
_CHUNK = 1024 * 1024  # 1 MiB


def sha256_file(path) -> str:
    """Return the SHA-256 hex digest of the complete binary content of `path`."""
    h = hashlib.sha256()
    with open(Path(path), "rb") as fh:
        for chunk in iter(lambda: fh.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def source_provenance(path) -> dict:
    """Provenance fields every importer adds to the canonical dictionary."""
    path = Path(path)
    return {
        "source_path":       path,
        "source_sha256":     sha256_file(path),
        "source_size_bytes": path.stat().st_size,
    }
