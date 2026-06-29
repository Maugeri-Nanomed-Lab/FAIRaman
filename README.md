# FAIRaman

**FAIRaman** is a Python-based tool for generating AI-ready **HDF5** files for **biomedical Raman spectroscopy data**.

It converts raw spectral measurements into **self-describing HDF5 files** enriched with metadata in accordance with FAIR principles, MIABIS, and NeXus-inspired data organization:

- **project-level metadata** (study identity, governance, licensing)
- **biological sample information** (MIABIS v3-compliant donor, tissue, and biobanking fields)
- **instrument metadata** (NXraman/NXinstrument)
- **spectroscopic measurement parameters** (acquisition, laser, optics)

Each file includes a machine-readable `data_license` field and a full schema that is always written — even for empty fields — so that batch processing across datasets never encounters schema-mismatch errors.

----

## FAIR Compliance

FAIRaman generates spectral files that are genuinely reusable by researchers and automated systems that have never seen the original data.

### Findable
Each HDF5 file stores `project_id`, `author_id`, `keywords`, `governance_reference`, and `accessibility` in the `PROJECT` group, providing the minimum information needed for indexing in data repositories.

### Accessible
HDF5 is an open, non-proprietary format readable with standard libraries (`h5py`, HDFView, MATLAB, R). The `data_license` and `accessibility` fields in `PROJECT` allow explicit declaration of terms of use. FAIRaman also produces a JSON sidecar as a fully human-readable copy of all metadata.

### Interoperable
The schema is built on established, community-maintained standards:

| Standard | Applied to |
|---|---|
| **NeXus / NXraman** | Spectral data structure and instrument metadata |
| **MIABIS v3** | Biological sample and biobank compliance fields |
| **UBERON** | Anatomical site annotation (`anatomical_ontology`) |
| **ICD-10** | Clinical diagnosis coding (`diagnosis_ontology`) |

Every FAIRaman file always contains the **complete schema** — all fields are written even when empty, guaranteeing that datasets from different instruments or operators can be merged and processed in batch without structural mismatches.

### Reusable
Physical units are always stored explicitly alongside their values (`wavelength_units`, `power_units`, `exposure_time_units`). Root-level attributes (`source_format`, `fairaman_version`) record the provenance of every file, supporting long-term reproducibility and audit trails.

---

## Installation

Install the main dependencies using **pip**:

```bash
pip install numpy pandas h5py matplotlib pillow
```

To support **Renishaw (.wdf)** files:

```bash
pip install renishawWiRE
```

If this library is not installed, FAIRaman will still work but **without WDF support**.

---

## Usage

Run the main script:

```bash
python FAIRaman.py
```

The program starts a graphical interface that allows you to:

- load Raman spectroscopy files (`.wdf` or ASCII)
- insert study and governance metadata
- describe the biological sample
- export the dataset in **HDF5**, **JSON**, and/or **CSV** format

**Excel metadata file** — variables mapped from an Excel file are associated with each individual spectrum whose file name matches the one present in the database. This makes it possible to assign specific metadata to each spectrum.

**TXT metadata file** — variables defined in a TXT file are applied uniformly to all spectra in the dataset, representing metadata common to the entire experiment.

The GUI includes an **intelligent first-guess mapper** that automatically suggests the correct HDF5 field for each column or key found in your Excel/TXT metadata files (see [Metadata Mapping](#metadata-mapping)).

Example of the underlying API:

```python
from pathlib import Path
from FAIRaman import process_wdf, write_hdf5_nexus

# Load a Renishaw WDF map
data = process_wdf(Path("map.wdf"))

# Define metadata
metadata = {
    "flat_data": {
        "PROJECT.project_name": "SpectraBREAST",
        "SAMPLE.sample_id":     "S001",
        "SAMPLE.SAMPLE_DONOR.diagnosis_code": "C50.9",
        "SAMPLE.SAMPLE_INFO.anatomical_ontology": "UBERON:0000310",
    }
}

# Export to HDF5
write_hdf5_nexus(Path("output.h5"), data, metadata)
```

---

## Supported Input Formats

### Renishaw WDF

FAIRaman reads `.wdf` files via `renishawWiRE` and automatically determines the spatial geometry:

- **Regular grid maps** — `map_shape` is used to reconstruct the spatial cube `(ny, nx, n_wavenumbers)` with calibrated µm axes from the WDF ORGN blocks.
- **Scatter/point acquisitions** — per-spectrum ORGN coordinates are stored directly as point coordinates.
- **Single spectra or unknown geometry** — synthetic index-based coordinates are generated and flagged as `coordinate_source: synthetic`.

White-light optical images and Raman acquisition map overlays are extracted and stored in `ENTRY/auxiliary/` when available.

### ASCII / CSV

FAIRaman recognises four ASCII/CSV layouts automatically:

| Layout | Description |
|---|---|
| **Single spectrum** | Two columns: `raman_shift \| intensity` |
| **Multi-spectrum (wide)** | Two or more intensity columns: `raman_shift \| spec_1 \| spec_2 \| ...` |
| **Spatial long format** | Four columns per row: `x \| y \| raman_shift \| intensity` |
| **Spatial wide format** | Header row with Raman shift values: `x \| y \| 800 \| 801 \| 802 \| ...` |

Supported delimiters: whitespace, comma, semicolon, tab. Comments starting with `#` are ignored. Raman shift axes are automatically sorted in ascending order.

For spatial formats, FAIRaman automatically detects whether the x/y coordinates form a **complete rectangular grid** (saved as `regular_grid`) or **irregular scatter points** (saved as `point_coordinates`).

---

## Canonical Data Model

FAIRaman v1.3 introduces a **canonical data model** — a single internal contract between all importers (WDF, ASCII; RamanSPy adapter planned) and the HDF5/NeXus writer.

<p align="center">
  <img src="fairaman_canonical_data_model.svg" alt="FAIRaman v1.3 — Canonical Data Model" width="800"/>
</p>

Two coordinate geometries are supported, distinguished by `coordinate_mode`:

| Mode | Array | Spatial axes |
|---|---|---|
| `regular_grid` | `cube (ny, nx, nw)` | `x_axis (nx,)` and `y_axis (ny,)` — combinable with meshgrid |
| `point_coordinates` | `spectra (n_points, nw)` | `x (n_pts,)` and `y (n_pts,)` — one real coordinate per spectrum |

Every imported dataset carries full **coordinate provenance**:

| Field | Values |
|---|---|
| `coordinate_source` | `"Renishaw ORGN/map_shape"`, `"ASCII x/y columns"`, `"synthetic"`, … |
| `coordinate_units` | `"micrometers"` or `"index"` |
| `coordinate_validated` | `True` if coordinates were verified against spectral dimensions |
| `reshape_applied` | `True` if the array was reshaped from 2D to 3D |

Geometric consistency is validated via `validate_canonical()` before any write to disk.

---

## Output

FAIRaman generates:

- **HDF5 / NeXus** (`.h5`) — the primary FAIR output, aligned to NXraman
- **JSON** sidecar — human-readable copy of all metadata fields
- **CSV** spectral matrix — geometry-aware flat export:
  - `regular_grid` → `x_um | y_um | wn_1 | ... | wn_n`
  - `point_coordinates` → `point_id | x | y | wn_1 | ... | wn_n`

---

## Data Model

FAIRaman organises every HDF5 file using a three-level hierarchy inspired by **MIABIS v3** and **NeXus/NXraman**, ensuring structural separation between project-level, biological, and measurement-specific information.

```text
FAIRaman.h5
│
├── PROJECT  (NXcollection)          ← study-level context
│   ├── project_name
│   ├── project_id
│   ├── funding
│   ├── governance_reference          ← NEW in v1.3 (ethics approval, DUA, etc.)
│   ├── author / author_id
│   ├── data_license
│   ├── accessibility
│   └── keywords
│
├── SAMPLE  (NXsample)               ← biological specimen
│   ├── sample_id
│   ├── SAMPLE_INFO
│   │   ├── sample_provenance
│   │   ├── sample_type / detailed_sample_type
│   │   ├── sample_source
│   │   ├── anatomical_site / anatomical_site_code / anatomical_ontology  (UBERON)
│   │   ├── storage_temperature
│   │   ├── processing_method
│   │   ├── sample_creation_date
│   │   └── sample_notes
│   ├── SAMPLE_DONOR
│   │   ├── donor_id
│   │   ├── donor_sex / donor_age
│   │   ├── diagnosis_code / diagnosis_ontology  (ICD-10)
│   │   └── diagnosis_notes
│   └── SAMPLE_EVENT
│       ├── event_date
│       └── event_description
│
└── ENTRY  (NXentry → NXraman)       ← individual measurement
    ├── title / experiment_type / run_type
    ├── start_time / data_type
    ├── measurement  (NXcollection)
    │   ├── exposure_time / exposure_time_units
    │   ├── accumulation_count
    │   └── substrate
    ├── instrument  (NXinstrument)
    │   ├── name
    │   ├── laser  (NXsource)
    │   │   ├── wavelength / wavelength_units
    │   │   ├── power / power_units               ← NEW in v1.3
    │   │   └── filter
    │   └── optical_system  (NXoptics)
    │       └── lens
    ├── data  (NXdata)               ← spectral data + coordinate provenance
    │   ├── intensity / spectra      ← 3D cube (ny, nx, nw) or 2D matrix (n_pts, nw)
    │   ├── raman_shift              ← wavenumber axis
    │   ├── x / y                    ← spatial axes (µm) or per-point coordinates
    │   ├── point_id                 ← point_coordinates mode only
    │   └── @coordinate_mode / @coordinate_source / @coordinate_validated / …
    └── auxiliary  (NXcollection)    ← WDF mode only
        ├── white_light  (NXdata)    ← optical micrograph with calibrated µm axes
        └── acquisition_map  (NXdata) ← Raman grid overlaid on white-light image
```

---

## Metadata Mapping

FAIRaman includes an intelligent **first-guess mapper** that automatically suggests the correct HDF5 field for every column or key found in your Excel or TXT metadata files.

The mapper recognises a wide range of common names, including aliases in Italian:

| Source column | Mapped to |
|---|---|
| `patient_id`, `paziente` | `SAMPLE.SAMPLE_DONOR.donor_id` |
| `icd10`, `diagnosis_code` | `SAMPLE.SAMPLE_DONOR.diagnosis_code` |
| `uberon`, `tissue`, `tessuto` | `SAMPLE.SAMPLE_INFO.anatomical_site` |
| `governance`, `governance_reference` | `PROJECT.governance_reference` |
| `laser`, `wavelength`, `laser_nm` | `ENTRY.instrument.laser.wavelength` |
| `power`, `laser_power` | `ENTRY.instrument.laser.power` |
| `exposure`, `integration_time` | `ENTRY.measurement.exposure_time` |

All suggestions can be reviewed and adjusted in the GUI before conversion.

---

## Dependencies

Main libraries:

- numpy
- pandas
- h5py
- matplotlib
- Pillow
- tkinter

Optional:

- renishawWiRE (for `.wdf` file reading — `pip install renishawWiRE`)

---

## Notes

- The acquisition map overlay is intended for qualitative spatial context and may not represent exact spatial alignment due to undocumented transformations in the WDF format.
- WDF start time is auto-populated from the file modification date if not provided in metadata.
- A **RamanSPy adapter** for Horiba, WiTec, and MATLAB formats is planned as a future extension. Note that RamanSPy's built-in Renishaw loader is not used for WDF files, as it discards spatial coordinates, white-light images, and laser metadata.

---

## Contributing

Pull requests are welcome. For major changes, please open an **issue** first to discuss what you would like to change.

Please make sure the code remains well documented, consistent with the canonical data model, and that `validate_canonical()` passes for all new importers.

---

## License

MIT License — see the `LICENSE` file for details.
