# FAIRaman

**FAIRaman** is a Python-based tool for generating AI-ready **HDF5** files for **biomedical Raman spectroscopy data**.

It converts raw spectral measurements into **self-describing HDF5 files** enriched with metadata in accordance with FAIR principles, MIABIS, and NeXus-inspired data organization.

- **project related metadata**
- **biological sample information** 
- **instrument metadata**
- **spectroscopic measurement parameters**

Each file includes a machine-readable `data_license` field to support the correct reuse and compliance with FAIR principles. The goal is to facilitate the creation of **interoperable datasets**, in accordance with the **FAIR principles** and the **MIABIS model** for biomedical data.

---
## FAIR Compliance

FAIRaman is designed in order to generate spectral containing files that are
genuinely reusable by researchers and automated systems that have never seen
the original data. Here is how each FAIR principle is implemented:

### Findable
Each HDF5 file stores `project_id`, `author_id`, `keywords`, and
`accessibility` in the `PROJECT` group, providing the minimum information
needed for indexing in data repositories. 

### Accessible
HDF5 is an open, non-proprietary format readable with standard libraries
(`h5py`, HDFView, MATLAB, R). The `data_license` and `accessibility` fields
in `PROJECT` allow explicit declaration of terms of use. FAIRaman also provide a JSON  fully human-readable copy of all metadata.

### Interoperable
The schema is built on established, community-maintained standards:

```
| Standard | Applied to |
|---|---|
| **NeXus / NXraman** | Spectral data structure and instrument metadata |
| **MIABIS v3** | Biological sample and biobank compliance fields |
| **UBERON** | Anatomical site annotation (`anatomical_ontology`) |
| **ICD-10** | Clinical diagnosis coding (`diagnosis_ontology`) |
```

Critically, every FAIRaman file always contains the **complete schema** —
all fields are written even when empty. This guarantees that datasets from
different instruments or operators can be merged and processed in batch
without schema-mismatch errors.

### Reusable
Physical units are always stored explicitly alongside their values
(`wavelength_units`, `exposure_time_units`). Root-level attributes (`source_format`,
`fairaman_version`) record the provenance of every file, supporting
long-term reproducibility and audit trails.


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

The program will start a graphical interface that allows you to:

- load Raman spectroscopy files (.wdf or ASCII)
- insert study metadata
- describe the biological sample
- export the dataset in **HDF5** format

Very user-friendly, the mapping of data loaded from TXT or Excel files is intuitive and simple.

Variables mapped and selected from the **Excel file** are associated **with each individual spectrum whose name matches the one present in the database**. This makes it possible to assign specific metadata to each spectrum.

On the other hand, variables defined in the **TXT file** are applied uniformly **to all spectra in the dataset**, representing metadata common to the entire experiment.

Example of the logical usage of the program:

```python
# loading spectral data
data = load_raman_data("spectrum.txt")

# adding sample metadata
sample = Sample(
    donor_id="D001",
    diagnosis="ICD10",
    tissue="UBERON"
)

# creating HDF5 file
create_hdf5(data, sample, "dataset.h5")
```

---

## Supported Input Formats

FAIRaman supports several input formats:

- `.wdf` (Renishaw WiRE)
- `.txt`
- `.csv`
- `.dat`

Typical ASCII format supported by the program:

```
wavenumber intensity
600   523
601   540
602   530
```

---

## Output

**FAIRaman** generates **HDF5** files containing:

- spectral data as multidimensional arrays
- sample metadata
- measurement information
- study metadata

This makes the files **self-describing and ready for FAIR data archiving**. The resulting files are thus directly compatible with machine learning and data-driven analysis pipelines.

The tool also includes the possibility of exporting:

- **.csv** containing the spectral matrix for each loaded spectrum
- **JSON** with a human-readable schematic map of the HDF5 information

---

## Data Model
Ensuring structural separation between project-level, biological, and measurement-specific information, FAIRaman organizes every HDF5 file using a three-level hierarchy inspired by **MIABIS v3** and **NeXus/NXraman**.

This structure enables:
- interoperability across institutions
- direct compatibility with machine learning workflows
- integration with clinical data systems

```
FAIRaman.h5
│
├── PROJECT  (NXcollection)          ← study-level context
│   ├── project_name
│   ├── project_id
│   ├── funding
│   ├── author / author_id
│   ├── data_license
│   ├── accessibility
│   └── keywords
│
├── SAMPLE  (NXsample)               ← biological specimen
│   ├── sample_id
│   ├── SAMPLE_INFO
│   │   ├── provenance
│   │   ├── sample_type / detailed_sample_type
│   │   ├── sample_source
│   │   ├── anatomical_site / anatomical_site_code / anatomical_ontology  (UBERON)
│   │   ├── storage_temperature
│   │   ├── processing_method
│   │   ├── sample_creation_date
│   │   └── notes
│   ├── SAMPLE_DONOR
│   │   ├── donor_id
│   │   ├── sex / age
│   │   ├── diagnosis_code / diagnosis_ontology  (ICD-10)
│   │   └── diagnosis_notes
│   └── SAMPLE_EVENT
│       ├── date
│       └── event_description
│
└── ENTRY  (NXentry → NXraman)       ← individual measurement
    ├── title / experiment_type / run_type
    ├── start_time / data_type
    ├── measurement  (NXcollection)
    │   ├── exposure_time / exposure_time_units
    │   ├── spectral_count / accumulation_count
    │   └── substrate
    └── instrument  (NXinstrument)
        ├── name
        ├── laser  (NXsource)
        │   ├── wavelength / wavelength_units
        │   └── filter
        └── optical_system  (NXoptics)
            └── lens
```


---

## Dependencies

Main libraries used:

- numpy
- pandas
- h5py
- matplotlib
- Pillow
- tkinter

Optional:

- renishawWiRE (for `.wdf` file reading)

---

## Contributing

Pull requests are welcome.

For major changes, please open an **issue** first to discuss what you would like to change.

Please make sure the code remains well documented and consistent with the project structure.

---

## License

See the *LICENSE* file.
