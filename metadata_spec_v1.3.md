# FAIRaman metadata specification v1.3

Standalone guide for preparing FAIRaman metadata input files and interpreting the metadata written in the generated HDF5/NeXus output.

FAIRaman converts Raman spectral data from Renishaw WDF or ASCII/CSV/TXT files into self-describing HDF5/NeXus files. The metadata model has three levels:

1. `PROJECT` — study, governance, authorship, access and reuse conditions.
2. `SAMPLE` — biological sample, donor and sample-processing event.
3. `ENTRY` — Raman acquisition, instrument configuration, spectral data and spatial geometry.

All metadata fields are written to the HDF5 output even when the corresponding input value is empty. This keeps all generated files structurally consistent and easier to compare, merge, validate or use in federated-learning workflows.

---

## 1. How to provide metadata as input

FAIRaman accepts metadata as a simple key-value file. The recommended format is a UTF-8 `.txt` file with one field per line:

```txt
project_name: SpectraBREAST
project_id: 101187508
funding: European Innovation Council
sample_id: SB001-OCT
sample_type: Tissue
detailed_sample_type: Breast tissue cryosection
anatomical_site: Breast
anatomical_site_code: UBERON:0000310
anatomical_ontology: UBERON
donor_id: SB001
donor_sex: Female
donor_age: 62
diagnosis_code: C50
diagnosis_ontology: ICD-10
experiment_type: Raman spectroscopy
run_type: map
substrate: CaF2
laser_wavelength: 785
wavelength_units: nm
power: 10
power_units: mW
lens: 50x
```

Rules:

- Use `key: value` syntax.
- Empty lines are ignored.
- Lines starting with `#` are ignored.
- Unknown fields are not automatically written unless mapped through the graphical interface.
- Field names are case-insensitive in the mapping assistant.
- Spaces, underscores and hyphens are normalised when FAIRaman guesses the mapping.
- The GUI mapping can always be manually corrected before export.

FAIRaman also recognises several practical aliases. For example, `patient_id`, `patient`, `paziente` and `donor_id` can all be mapped to `SAMPLE/SAMPLE_DONOR/donor_id`. However, for publication and reproducibility, the canonical field names listed below are preferred.

---

## 2. Metadata levels and HDF5 output paths

The tables below show:

- **Input key**: the recommended key to use in the metadata input file.
- **HDF5 output path**: where the value is written in the generated HDF5/NeXus file.
- **Meaning**: how the field should be used.
- **Example**: typical value.
- **Source / alignment**: reference standard or controlled vocabulary, when applicable.

---

## 3. `PROJECT` — study and data-use context

Use this section for information that describes the project or study under which the Raman data were generated. It corresponds to the Investigation layer of the ISA model.

| Input key | HDF5 output path | Meaning | Example | Source / alignment |
|---|---|---|---|---|
| `project_name` | `/PROJECT/project_name` | Name of the project, study or dataset collection. | `SpectraBREAST` | ISA Investigation |
| `project_id` | `/PROJECT/project_id` | Persistent or internal identifier of the project. | `101187508` | ISA Investigation |
| `funding` | `/PROJECT/funding` | Funding source or grant supporting data generation. | `European Innovation Council` | ISA Investigation |
| `governance_reference` | `/PROJECT/governance_reference` | Reference to the governance framework authorising the data collection and reuse. This can be an ethics approval, protocol ID, clinical trial ID, data management plan, institutional policy or access committee reference. | `EC approval 2025-XXX`; `NCT06048835`; `DMP v1.0` | EHDS/GDPR-facing study governance |
| `author` | `/PROJECT/author` | Person or group responsible for generating or curating the data. | `Davide Piccapietra` | ISA Investigation |
| `author_id` | `/PROJECT/author_id` | Persistent identifier for the data author. ORCID is recommended for individuals. | `0000-0000-XXXX-XXXX` | ORCID |
| `data_license` | `/PROJECT/data_license` | Licence or reuse condition applied to the data. | `CC-BY-4.0`; `restricted` | FAIR Reusability |
| `accessibility` | `/PROJECT/accessibility` | Declared access condition. | `open`; `upon reasonable request`; `restricted` | FAIR Accessibility |
| `keywords` | `/PROJECT/keywords` | Free keywords supporting discovery and indexing. Separate multiple terms with semicolons. | `Breast cancer; Raman spectroscopy; Surgical margins` | FAIR Findability |

Practical note: `governance_reference` is not a legal-base field. It points to the document, identifier or governance mechanism that explains why the sample and data can be used.

---

## 4. `SAMPLE` — biological sample

Use this section for the biological material analysed by Raman spectroscopy. It corresponds to the Study layer of the ISA model and is aligned with MIABIS terminology where possible.

### 4.1 Main sample identifier

| Input key | HDF5 output path | Meaning | Example | Source / alignment |
|---|---|---|---|---|
| `sample_id` | `/SAMPLE/sample_id` | Unique identifier of the analysed sample. It should not contain directly identifying personal information. | `SB001-OCT` | MIABIS Sample ID |

---

### 4.2 `SAMPLE_INFO` — sample material and handling

| Input key | HDF5 output path | Meaning | Example | Source / alignment |
|---|---|---|---|---|
| `sample_provenance` | `/SAMPLE/SAMPLE_INFO/sample_provenance` | Institution, biobank, laboratory or cohort from which the sample originates. | `ICS Maugeri` | MIABIS / provenance |
| `sample_type` | `/SAMPLE/SAMPLE_INFO/sample_type` | High-level biological sample category. | `Tissue`; `Liquid biopsy`; `Cells`; `Extracellular vesicles` | MIABIS Sample |
| `detailed_sample_type` | `/SAMPLE/SAMPLE_INFO/detailed_sample_type` | More granular sample description. | `Breast tissue cryosection`; `Plasma`; `Small extracellular vesicles` | MIABIS-SAMPLE-02 |
| `sample_source` | `/SAMPLE/SAMPLE_INFO/sample_source` | Biological source from which the sample was collected. | `Human`; `Animal`; `Environment`; `Cell culture` | MIABIS-SAMPLE-12 |
| `anatomical_site` | `/SAMPLE/SAMPLE_INFO/anatomical_site` | Human-readable anatomical origin of the sample. | `Breast`; `Blood`; `Colon` | MIABIS-SAMPLE-05 |
| `anatomical_site_code` | `/SAMPLE/SAMPLE_INFO/anatomical_site_code` | Ontology identifier for the anatomical site. Include the prefix when possible. | `UBERON:0000310`; `UBERON:0000178` | UBERON / MIABIS-SAMPLE-05-03 |
| `anatomical_ontology` | `/SAMPLE/SAMPLE_INFO/anatomical_ontology` | Ontology used for the anatomical-site code. | `UBERON` | MIABIS-SAMPLE-05-01 |
| `storage_temperature` | `/SAMPLE/SAMPLE_INFO/storage_temperature` | Long-term storage temperature or storage class. | `-80 °C`; `-60 °C to -85 °C`; `room temperature` | SPREC / MIABIS-SAMPLE-03 |
| `processing_method` | `/SAMPLE/SAMPLE_INFO/processing_method` | Pre-analytical method used to prepare the sample. | `Cryosectioning, 10 µm`; `Double centrifugation plasma preparation`; `SEC isolation of EVs` | Protocol metadata |
| `sample_creation_date` | `/SAMPLE/SAMPLE_INFO/sample_creation_date` | Date of sample collection or creation, preferably in ISO 8601 format. | `2026-06-26` | MIABIS-SAMPLE-04 |
| `sample_notes` | `/SAMPLE/SAMPLE_INFO/sample_notes` | Free-text note for sample information not captured by structured fields. | `Adjacent normal tissue`; `Low-volume plasma sample` | Local metadata |

Practical note: `sample_type` should remain broad. Put the precise material in `detailed_sample_type`. For example, use `sample_type: Tissue` and `detailed_sample_type: Breast tissue OCT cryosection`.

---

### 4.3 `SAMPLE_DONOR` — donor and diagnosis

Use this section only for pseudonymised donor-level information. Do not insert names, hospital numbers, tax codes, addresses or other direct identifiers.

| Input key | HDF5 output path | Meaning | Example | Source / alignment |
|---|---|---|---|---|
| `donor_id` | `/SAMPLE/SAMPLE_DONOR/donor_id` | Pseudonymised persistent donor identifier. | `SB001`; `AD123` | MIABIS-DONOR-01 |
| `donor_sex` | `/SAMPLE/SAMPLE_DONOR/donor_sex` | Sex of the donor. Prefer controlled values when possible. | `Female`; `Male`; `Unknown`; `Not applicable` | MIABIS-DONOR-02 |
| `donor_age` | `/SAMPLE/SAMPLE_DONOR/donor_age` | Age at sample collection, in years. Use age range if exact age is not appropriate. | `62`; `60-65` | Clinical metadata |
| `diagnosis_code` | `/SAMPLE/SAMPLE_DONOR/diagnosis_code` | Diagnosis code associated with the donor or sample. | `C50`; `G30`; `ORPHA:XXX` | ICD-10 / ORPHA |
| `diagnosis_ontology` | `/SAMPLE/SAMPLE_DONOR/diagnosis_ontology` | Classification system used for the diagnosis code. | `ICD-10`; `ORPHA`; `ICD-9-CM` | Clinical terminology |
| `diagnosis_notes` | `/SAMPLE/SAMPLE_DONOR/diagnosis_notes` | Free-text clinical context not captured by the structured code. | `Invasive ductal carcinoma`; `Healthy control` | Local metadata |

Practical note: use `diagnosis_code` for the machine-readable diagnosis and `diagnosis_notes` for the human-readable label.

---

### 4.4 `SAMPLE_EVENT` — sample-processing event

Use this section for the event that links the biological sample to the analysed material. This may be collection, sectioning, EV isolation, thawing, staining-free preparation or another pre-analytical step.

| Input key | HDF5 output path | Meaning | Example | Source / alignment |
|---|---|---|---|---|
| `event_date` | `/SAMPLE/SAMPLE_EVENT/event_date` | Date of the relevant sample event, preferably in ISO 8601 format. | `2026-06-26` | MIABIS Event |
| `event_description` | `/SAMPLE/SAMPLE_EVENT/event_description` | Description of what happened to the sample before Raman analysis. | `Sectioned at 10 µm and mounted on CaF2`; `Plasma thawed and EVs isolated by ultracentrifugation` | MIABIS Event / protocol metadata |

---

## 5. `ENTRY` — Raman acquisition and instrument metadata

Use this section for the individual Raman measurement. It corresponds to the Assay layer of the ISA model and is aligned with NeXus/NXraman concepts.

### 5.1 Entry-level acquisition fields

| Input key | HDF5 output path | Meaning | Example | Source / alignment |
|---|---|---|---|---|
| `title` | `/ENTRY/title` | Human-readable title of the acquisition. If not provided, FAIRaman may use the source filename. | `SB001-OCT-map-01` | NeXus / NXentry |
| `experiment_type` | `/ENTRY/experiment_type` | Type of experiment. | `Raman spectroscopy` | NXraman |
| `run_type` | `/ENTRY/run_type` | Acquisition mode. | `single`; `map`; `timeseries`; `point_coordinates` | Local / NXraman-facing |
| `start_time` | `/ENTRY/start_time` | Date and time of acquisition. ISO 8601 is recommended. | `2026-06-26T14:30:00` | NeXus |
| `data_type` | `/ENTRY/data_type` | Nature of the data. | `experimental`; `simulated`; `derived` | Data provenance |

---

### 5.2 `ENTRY/measurement` — measurement settings

| Input key | HDF5 output path | Meaning | Example | Source / alignment |
|---|---|---|---|---|
| `exposure_time` | `/ENTRY/measurement/exposure_time` | Integration time of a single acquisition. | `1.2`; `10` | NeXus |
| `exposure_time_units` | `/ENTRY/measurement/exposure_time_units` | Unit for exposure time. | `s`; `sec`; `ms` | NeXus units |
| `substrate` | `/ENTRY/measurement/substrate` | Material on which the sample was measured. | `CaF2`; `quartz`; `glass`; `aluminium slide` | Experimental metadata |
| `accumulation_count` | `/ENTRY/measurement/accumulation_count` | Number of accumulations co-added for each spectrum. | `15`; `32` | NeXus / Raman metadata |

---

### 5.3 `ENTRY/instrument` — instrument identity

| Input key | HDF5 output path | Meaning | Example | Source / alignment |
|---|---|---|---|---|
| `instrument_name` | `/ENTRY/instrument/name` | Instrument model or internal instrument identifier. | `Renishaw inVia`; `Horiba LabRAM` | NXinstrument |

Alias note: the shorter input key `instrument` can also be mapped to `/ENTRY/instrument/name`, but `instrument_name` is clearer in metadata templates.

---

### 5.4 `ENTRY/instrument/laser` — laser source

| Input key | HDF5 output path | Meaning | Example | Source / alignment |
|---|---|---|---|---|
| `laser_wavelength` | `/ENTRY/instrument/laser/wavelength` | Excitation wavelength of the Raman laser. | `532`; `633`; `785` | NXsource |
| `wavelength_units` | `/ENTRY/instrument/laser/wavelength_units` | Unit for laser wavelength. | `nm` | NeXus units |
| `laser_power` | `/ENTRY/instrument/laser/power` | Laser power at the source or sample, depending on local convention. Specify this convention in `sample_notes` or protocol documentation if needed. | `10`; `50` | NXsource / Raman metadata |
| `power_units` | `/ENTRY/instrument/laser/power_units` | Unit for laser power. | `mW`; `%` | NeXus units / local metadata |
| `laser_filter` | `/ENTRY/instrument/laser/filter` | Neutral-density filter or fraction of nominal laser power transmitted to the sample. | `10%`; `100%`; `ND 1.0` | Raman metadata |

Practical note: avoid mixing absolute power and percentage in the same field across a dataset. If the instrument reports laser power as percentage, use `laser_filter` or set `power_units: %` consistently.

---

### 5.5 `ENTRY/instrument/optical_system` — optical configuration

| Input key | HDF5 output path | Meaning | Example | Source / alignment |
|---|---|---|---|---|
| `lens` | `/ENTRY/instrument/optical_system/lens` | Objective or lens used to collect Raman signal. | `50x`; `100x`; `20x long working distance` | NXoptics |

Alias note: `objective` and `obiettivo` can be mapped to this field.

---

## 6. Spectral data and geometry written automatically

The fields in this section are generated by FAIRaman from the input spectral file. They do not normally need to be included in the metadata input file.

FAIRaman v1.3 distinguishes two spatial models:

1. **`regular_grid`** — a rectangular Raman map with shape `(ny, nx, n_wavenumbers)`.
2. **`point_coordinates`** — a list of spectra with one real or synthetic `(x, y)` coordinate per spectrum.

### 6.1 Common spectral fields

| HDF5 output path | Meaning | Example / shape | Generated from |
|---|---|---|---|
| `/ENTRY/data/raman_shift` | Raman shift axis. | `(n_wavenumbers,)` | WDF x-axis or first column/header of ASCII file |
| `/ENTRY/data/signal` | Raman intensity data. For maps this is a cube; for point data this is a spectra matrix. | `(ny, nx, n_wavenumbers)` or `(n_points, n_wavenumbers)` | WDF spectra or ASCII intensity columns |
| `/ENTRY/data/n_wavenumbers` | Number of Raman-shift points. | `1015` | Derived automatically |
| `/ENTRY/data/spectral_count` | Number of spectra in the dataset. | `1024` | Derived automatically |
| `/ENTRY/data/source_format` | Original spectral file format. | `wdf`; `txt` | Importer |

### 6.2 Geometry fields for `regular_grid`

| HDF5 output path | Meaning | Example / shape | Generated from |
|---|---|---|---|
| `/ENTRY/data/coordinate_mode` | Declares the geometry model. | `regular_grid` | Importer |
| `/ENTRY/data/x_axis` | X coordinates of the grid columns. | `(nx,)` | WDF ORGN/map_shape or ASCII x column |
| `/ENTRY/data/y_axis` | Y coordinates of the grid rows. | `(ny,)` | WDF ORGN/map_shape or ASCII y column |
| `/ENTRY/data/nx` | Number of grid points along x. | `32` | Derived automatically |
| `/ENTRY/data/ny` | Number of grid points along y. | `32` | Derived automatically |
| `/ENTRY/data/coordinate_units` | Unit of spatial coordinates. | `micrometers`; `index` | Importer |
| `/ENTRY/data/coordinate_source` | Origin of the coordinate information. | `Renishaw ORGN/map_shape`; `ASCII x/y grid`; `synthetic` | Importer |
| `/ENTRY/data/coordinate_validated` | Whether the coordinates are physically meaningful and consistent with the spectra. | `true`; `false` | Validation logic |
| `/ENTRY/data/reshape_applied` | Whether spectra were reshaped into a cube. | `true`; `false` | Importer |
| `/ENTRY/data/reshape_source` | Rule used for reshaping. | `map_shape`; `ASCII x/y grid`; `none` | Importer |

### 6.3 Geometry fields for `point_coordinates`

| HDF5 output path | Meaning | Example / shape | Generated from |
|---|---|---|---|
| `/ENTRY/data/coordinate_mode` | Declares the geometry model. | `point_coordinates` | Importer |
| `/ENTRY/data/x` | X coordinate for each spectrum. | `(n_points,)` | WDF ORGN, ASCII x column or synthetic index |
| `/ENTRY/data/y` | Y coordinate for each spectrum. | `(n_points,)` | WDF ORGN, ASCII y column or synthetic zero vector |
| `/ENTRY/data/coordinate_units` | Unit of spatial coordinates. | `micrometers`; `index` | Importer |
| `/ENTRY/data/coordinate_source` | Origin of the coordinate information. | `Renishaw ORGN (per-point)`; `ASCII x/y columns`; `synthetic` | Importer |
| `/ENTRY/data/coordinate_validated` | Whether the coordinates are physically meaningful and consistent with spectra. | `true`; `false` | Validation logic |
| `/ENTRY/data/reshape_applied` | Always false for true point-coordinate datasets. | `false` | Importer |
| `/ENTRY/data/reshape_source` | Reshape source. | `none` | Importer |

Practical interpretation:

- `coordinate_validated: true` means FAIRaman found real coordinates coherent with the number and shape of spectra.
- `coordinate_validated: false` means coordinates were generated only to keep the HDF5 structure complete.
- `coordinate_units: index` means the coordinates should not be interpreted as micrometre positions.
- `reshape_applied: true` is not a problem: it documents that a flat spectral list was reconstructed into a spatial cube using a declared rule.

---

## 7. Supported spectral input formats

### 7.1 Renishaw WDF

For `.wdf` files, FAIRaman reads:

- spectra;
- Raman shift axis;
- map shape, when available;
- per-spectrum coordinates, when available;
- white-light image, when available;
- laser wavelength, when available from the file metadata.

If `map_shape` is present and consistent with the number of spectra, the output is written as `regular_grid`.

If no regular grid is detected but valid per-spectrum coordinates exist, the output is written as `point_coordinates`.

If no physical coordinates are available, synthetic index coordinates are generated and marked as non-validated.

### 7.2 ASCII / CSV / TXT spectral files

FAIRaman supports four practical ASCII layouts.

#### Single spectrum

```txt
800  120
801  125
802  130
```

Interpreted as:

- Raman shift column;
- intensity column;
- synthetic `1 × 1` regular grid.

#### Multi-spectrum wide matrix without coordinates

```txt
800  120  118  122
801  125  121  128
802  130  127  131
```

Interpreted as:

- first column = Raman shift;
- remaining columns = spectra;
- synthetic `1 × n` regular grid.

#### Long spatial format

```txt
x,y,raman_shift,intensity
0,0,800,120
0,0,801,125
1,0,800,118
1,0,801,121
```

Interpreted as:

- one row per Raman-shift value at a given x/y position;
- reconstructed spectra for each x/y pair;
- `regular_grid` if all x/y combinations form a complete grid;
- otherwise `point_coordinates`.

#### Wide spatial format with Raman-shift header

```txt
x,y,800,801,802
0,0,120,125,130
1,0,118,121,127
0,1,122,128,131
1,1,119,124,129
```

Interpreted as:

- first two columns = x and y;
- remaining column headers = Raman shift values;
- values = intensities;
- `regular_grid` if all x/y combinations form a complete grid;
- otherwise `point_coordinates`.

---

## 8. Recommended controlled values

FAIRaman currently does not enforce strict controlled vocabularies for all fields, but consistent values are strongly recommended.

| Field | Recommended values / format |
|---|---|
| `sample_source` | `Human`, `Animal`, `Environment`, `Cell culture`, `Synthetic` |
| `donor_sex` | `Female`, `Male`, `Unknown`, `Undifferentiated`, `Not applicable` |
| `diagnosis_ontology` | `ICD-10`, `ICD-9-CM`, `ORPHA`, `SNOMED CT` |
| `anatomical_ontology` | `UBERON`, `NCIT`, `FMA` |
| `sample_creation_date` | ISO 8601 date: `YYYY-MM-DD` |
| `event_date` | ISO 8601 date: `YYYY-MM-DD` |
| `start_time` | ISO 8601 datetime: `YYYY-MM-DDTHH:MM:SS` |
| `data_type` | `experimental`, `simulated`, `derived` |
| `run_type` | `single`, `map`, `timeseries`, `point_coordinates` |
| `wavelength_units` | `nm` |
| `exposure_time_units` | `s`, `sec`, `ms` |
| `power_units` | `mW`, `%` |

---

## 9. Minimal metadata template

A minimal metadata file for a tissue Raman map may look like this:

```txt
project_name: SpectraBREAST
project_id: 101187508
funding: European Innovation Council
governance_reference: Ethics approval XXX; protocol SpectraBREAST v1.0
author: Davide Piccapietra
author_id: 0000-0000-XXXX-XXXX
data_license: restricted
accessibility: upon reasonable request
keywords: Breast cancer; Raman spectroscopy; Surgical margins

sample_id: SB001-OCT
sample_provenance: ICS Maugeri
sample_type: Tissue
detailed_sample_type: Breast tissue cryosection
sample_source: Human
anatomical_site: Breast
anatomical_site_code: UBERON:0000310
anatomical_ontology: UBERON
storage_temperature: -80 °C
processing_method: OCT embedding and cryosectioning
sample_creation_date: 2026-06-26
sample_notes: Unstained section mounted on CaF2

donor_id: SB001
donor_sex: Female
donor_age: 62
diagnosis_code: C50
diagnosis_ontology: ICD-10
diagnosis_notes: Breast carcinoma

event_date: 2026-06-26
event_description: Sectioned at 10 µm and mounted on CaF2 before Raman acquisition

title: SB001-OCT-map-01
experiment_type: Raman spectroscopy
run_type: map
start_time: 2026-06-26T14:30:00
data_type: experimental
exposure_time: 1.2
exposure_time_units: s
substrate: CaF2
accumulation_count: 32
instrument_name: Renishaw inVia
laser_wavelength: 532
wavelength_units: nm
laser_power: 50
power_units: %
laser_filter: 50%
lens: 50x
```

---

## 10. Minimal output reading guide

When opening a FAIRaman HDF5 file, the most important paths are:

```txt
/PROJECT
/SAMPLE
/SAMPLE/SAMPLE_INFO
/SAMPLE/SAMPLE_DONOR
/SAMPLE/SAMPLE_EVENT
/ENTRY
/ENTRY/measurement
/ENTRY/instrument
/ENTRY/instrument/laser
/ENTRY/instrument/optical_system
/ENTRY/data
```

To interpret the spectral data, first check:

```txt
/ENTRY/data/coordinate_mode
/ENTRY/data/signal
/ENTRY/data/raman_shift
/ENTRY/data/coordinate_validated
/ENTRY/data/coordinate_source
/ENTRY/data/coordinate_units
```

Then:

- if `coordinate_mode = regular_grid`, read `x_axis`, `y_axis` and the signal cube;
- if `coordinate_mode = point_coordinates`, read `x`, `y` and the spectra matrix;
- if `coordinate_validated = false`, treat coordinates as structural placeholders, not physical positions.

---

## 11. Privacy and governance warning

Do not include direct personal identifiers in FAIRaman metadata files. In particular, avoid:

- patient names;
- hospital record numbers;
- fiscal codes or national identifiers;
- full dates of birth;
- addresses;
- phone numbers;
- free-text notes that could re-identify a donor.

Use pseudonymised `sample_id` and `donor_id` values and keep the re-identification key outside FAIRaman, under the responsibility of the authorised clinical or biobank data controller.
