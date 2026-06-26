# FAIRaman Metadata Mapping

FAIRaman automatically recognizes commonly used metadata field names and maps them to the corresponding HDF5 metadata path.

This allows users to import metadata from Excel, CSV or TXT files without manually renaming every column.

---

## Matching rules

Before attempting a match, FAIRaman normalizes field names by:

- converting names to lowercase;
- removing spaces;
- removing underscores (`_`);
- removing hyphens (`-`);
- removing dots (`.`);
- removing parentheses;
- removing accents and special characters.

For example, all of the following are interpreted as equivalent:

```text
sample_id
Sample ID
sample-id
SAMPLE.sample_id
```

---

## Automatic field mapping

| Accepted input names | FAIRaman HDF5 path |
|---|---|
| `project`, `project_name`, `study`, `study_name` | `PROJECT.project_name` |
| `project_id`, `study_id` | `PROJECT.project_id` |
| `funding`, `grant` | `PROJECT.funding` |
| `governance`, `governance_reference` | `PROJECT.governance_reference` |
| `author`, `data_author` | `PROJECT.author` |
| `orcid`, `author_id` | `PROJECT.author_id` |
| `license`, `licence`, `data_license` | `PROJECT.data_license` |
| `access`, `accessibility` | `PROJECT.accessibility` |
| `keyword`, `keywords` | `PROJECT.keywords` |
| `sample`, `sample_id`, `campione` | `SAMPLE.sample_id` |
| `sample_provenance`, `provenance` | `SAMPLE.SAMPLE_INFO.sample_provenance` |
| `sample_type`, `tipo_campione`, `tipocampione` | `SAMPLE.SAMPLE_INFO.sample_type` |
| `detailed_sample_type` | `SAMPLE.SAMPLE_INFO.detailed_sample_type` |
| `sample_source` | `SAMPLE.SAMPLE_INFO.sample_source` |
| `anatomical_site`, `site`, `tissue`, `tessuto` | `SAMPLE.SAMPLE_INFO.anatomical_site` |
| `anatomical_site_code`, `UBERON`, `uberon_id` | `SAMPLE.SAMPLE_INFO.anatomical_site_code` |
| `anatomical_ontology` | `SAMPLE.SAMPLE_INFO.anatomical_ontology` |
| `storage_temperature`, `temperature` | `SAMPLE.SAMPLE_INFO.storage_temperature` |
| `processing_method`, `protocol` | `SAMPLE.SAMPLE_INFO.processing_method` |
| `sample_creation_date` | `SAMPLE.SAMPLE_INFO.sample_creation_date` |
| `notes`, `sample_notes` | `SAMPLE.SAMPLE_INFO.sample_notes` |
| `donor`, `donor_id`, `patient`, `patient_id`, `paziente` | `SAMPLE.SAMPLE_DONOR.donor_id` |
| `sex`, `sesso`, `donor_sex` | `SAMPLE.SAMPLE_DONOR.donor_sex` |
| `age`, `eta`, `donor_age` | `SAMPLE.SAMPLE_DONOR.donor_age` |
| `diagnosis`, `diagnosi`, `diagnosis_notes` | `SAMPLE.SAMPLE_DONOR.diagnosis_notes` |
| `diagnosis_code`, `ICD10`, `ICD` | `SAMPLE.SAMPLE_DONOR.diagnosis_code` |
| `diagnosis_ontology` | `SAMPLE.SAMPLE_DONOR.diagnosis_ontology` |
| `collection_date`, `event_date` | `SAMPLE.SAMPLE_EVENT.event_date` |
| `event_description` | `SAMPLE.SAMPLE_EVENT.event_description` |
| `title` | `ENTRY.title` |
| `experiment_type` | `ENTRY.experiment_type` |
| `run_type` | `ENTRY.run_type` |
| `start_time` | `ENTRY.start_time` |
| `data_type` | `ENTRY.data_type` |
| `exposure`, `exposure_time`, `integration_time` | `ENTRY.measurement.exposure_time` |
| `exposure_time_units` | `ENTRY.measurement.exposure_time_units` |
| `substrate` | `ENTRY.measurement.substrate` |
| `accumulation`, `accumulations`, `accumulation_count` | `ENTRY.measurement.accumulation_count` |
| `instrument`, `instrument_name` | `ENTRY.instrument.name` |
| `laser`, `laser_wavelength`, `laser_nm`, `wavelength` | `ENTRY.instrument.laser.wavelength` |
| `laser_units`, `wavelength_units` | `ENTRY.instrument.laser.wavelength_units` |
| `laser_power`, `power` | `ENTRY.instrument.laser.power` |
| `laser_power_units`, `power_units` | `ENTRY.instrument.laser.power_units` |
| `laser_filter`, `filter` | `ENTRY.instrument.laser.filter` |
| `objective`, `lens`, `obiettivo` | `ENTRY.instrument.optical_system.lens` |

---

## Direct HDF5 paths

If a metadata column already contains a valid FAIRaman HDF5 path, it is used directly without conversion.

Example:

```text
ENTRY.instrument.laser.wavelength
```

---

## Automatic basename matching

If a metadata column matches the final element of a unique HDF5 path, FAIRaman automatically assigns it.

For example:

```text
wavelength
```

is automatically mapped to:

```text
ENTRY.instrument.laser.wavelength
```

provided that no ambiguity exists.

---

## Fields ignored automatically

The following fields are considered technical file-management information and are **not** mapped automatically:

```text
file
filename
file_name
filepath
file_path
folder
path
wdf
wdf_file
csv
txt
spectrum_file
spectral_file
```

These fields will appear as:

```text
Do not map
```

---

## Manual override

The automatic mapping is only a first guess.

Users can freely modify every mapping inside the FAIRaman metadata import GUI before creating the HDF5 dataset.

---

## Design philosophy

The mapping system is intentionally permissive to maximize interoperability with existing laboratory spreadsheets while preserving a single standardized FAIRaman HDF5 schema.

This approach minimizes manual preprocessing and facilitates the FAIRification of legacy Raman datasets.
