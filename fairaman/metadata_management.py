# ─────────────────────────────────────────────────────────────────────────────
# CONVERSION PIPELINE — SHARED METADATA LOADING
# ─────────────────────────────────────────────────────────────────────────────
# HDF5 path prefixes that belong to the Investigation/Assay level and are
# therefore sourced from the shared TXT metadata file (not from the per-file
# Excel sheet, which covers the Sample level only).
# ─────────────────────────────────────────────────────────────────────────────
# METADATA MAPPING FIRST GUESS
# ─────────────────────────────────────────────────────────────────────────────
# Alias pragmatici per nomi frequenti in TXT/Excel.
# Le chiavi vengono normalizzate con _normalise_mapping_key().

from pathlib import Path
import re
import pandas as pd
import unicodedata
from fairaman.metadata import parse_txt_metadata
from fairaman.schema import NEXUS_SCHEMA, flatten_schema

HDF5_FIELDS = ["Do not map"] + flatten_schema(NEXUS_SCHEMA)

# Known spectral file extensions to strip when normalising filename stems.
_STRIP_EXTS = {".wdf", ".WDF", ".txt", ".TXT", ".csv", ".CSV", ".dat", ".DAT"}

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

def _normalise_mapping_key(s: str) -> str:

    """
    Normalizes field names for robust comparisons by:
    - converting to lowercase;
    - removing spaces, underscores, hyphens, periods, and parentheses;
    - handling minor formatting differences between Excel/TXT field names and
    HDF5 paths.

    Examples:
        'sample_id'        → 'sampleid'
        'Sample ID'        → 'sampleid'
        'SAMPLE.sample_id' → 'samplesampleid'
    """

    s = "" if s is None else str(s)
    s = unicodedata.normalize("NFKD", s)
    s = s.encode("ascii", "ignore").decode("ascii")
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s

_METADATA_ALIASES = {
    _normalise_mapping_key(k): v
    for k, v in _METADATA_ALIASES_RAW.items()
}

def _build_hdf5_mapping_lookup() -> tuple[dict, dict]:

    """
    Builds two lookup dictionaries:

    1) `full_lookup`: matches using the complete field path or its normalized
    underscore representation, e.g.
    `ENTRY.instrument.laser.wavelength`.

    2) `basename_lookup`: matches using only the final field name, e.g.
    `wavelength`, `sample_id`, or `diagnosis_code`.

    The basename lookup is used only when the field name is unambiguous.
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

def _normalise_stem(raw: str) -> str:

    """
    Normalizes a raw filename from the Excel key column by converting it to
    lowercase and removing its file extension, making it suitable for
    dictionary lookup.

    Only a single trailing file extension is removed (e.g., `"sample.wdf"` →
    `"sample"`). More complex filename patterns are not handled, as they do
    not occur in the standard Raman file naming convention.

    Parameters
    ----------
    raw : str
        Raw filename value from the key column in the Excel file.

    Returns
    -------
    str
        Lowercase filename stem with leading and trailing whitespace removed.
    """

    s = str(raw).strip()
    p = Path(s)
    if p.suffix in _STRIP_EXTS:
        s = p.stem
    return s.lower()

def _get_excel_row(stem: str, excel_map: dict):

    """
    Searches for the Excel metadata row corresponding to a given filename
    (without its extension).

    The search is performed in two ways:
        1) an exact comparison after converting all values to lowercase;
        2) a more permissive comparison that ignores or normalizes separators
        in the filename.

    Each call prints detailed diagnostic information, making it easier to
    understand how the match was found or why no match was found.

    Returns the corresponding row as a dictionary, or `None` if no match
    is found.
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
    Loads and preprocesses metadata from the TXT and Excel files.

    The TXT file is always read because it is required for the conversion process.
    The Excel file is optional. When provided, its first column is used as the
    filename column. This reflects the expected Excel worksheet layout, where
    column A contains the names of the WDF files or ASCII spectra.

    Filenames are normalized using `_normalise_stem` by converting them to
    lowercase and removing the extension. Therefore, `"Sample_001.wdf"`,
    `"sample_001"`, and `"SAMPLE_001"` are all stored under the same
    `"sample_001"` key.

    Parameters
    ----------
    state : dict
        Application state dictionary containing the relevant sub-dictionary.

    frames : dict
        GUI frame registry. It is not modified and is passed here only for
        consistency with the API.

    Returns
    -------
    tuple
        `(txt_meta, excel_df, excel_metadata_map, filename_col, empty_row)`

        * `txt_meta` — dictionary containing metadata read from the TXT file.
        * `excel_df` — original Excel DataFrame, or `None`.
        * `excel_metadata_map` — mapping from normalized filename stem to the
        corresponding Excel row dictionary.
        * `filename_col` — name of the first Excel column, or `None`.
        * `empty_row` — first row of the Excel worksheet, used as a fallback.
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
    Constructs a flat metadata dictionary indexed by HDF5 paths by merging
    information from the TXT metadata and the corresponding Excel row.

    Source fields are mapped to the appropriate HDF5 paths according to the
    mappings defined by the user in the GUI.

    If multiple source fields map to the same HDF5 path, their values are
    not overwritten. Instead, they are concatenated using `" | "` as the
    separator.

    Parameters
    ----------
    txt_meta : dict
        Metadata read from the TXT file.

    excel_row : dict
        Excel row containing the sample metadata for the current file.

    frames : dict
        GUI frame registry, used to access the `get_mapping()` function.

    Returns
    -------
    dict
        Flat dictionary mapping HDF5 paths to their corresponding metadata values.
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


