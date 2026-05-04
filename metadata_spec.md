## FAIRaman metadata schema

Fields included in the FAIRaman scheme. All fields are written even if remain empty for compatibility with possible federated learning architecture

---

### `PROJECT` — Identification of the contex in witch data were collected, and condition of use of the data

| Field           | Description            | Example                                          | Source |
| --------------- | ---------------------- | ------------------------------------------------ | ------ |
| `project_name`  | Name of the project    | Spectra-BREAST                                   |        |
| `project_id`    | Project ID             | 101187508                                        |        |
| `funding`       | Funding                | European Innovation Council                      |        |
| `author`        | Data author            | Davide Piccapietra                               |        |
| `author_id`     | Orcid                  | 0000-0000-XXXX-XXXX                              |        |
| `data_license`  | Licence                | restricted                                       |        |
| `accessibility` | Accessibility          | upon reasonable request                          |        |
| `keywords`      | keywords               | Breast Cancer; Tissue Analysis; Surgical Margins |        |

The PROJECT section corresponds to the Investigation layer of the ISA (Investigation–Study–Assay) organisational standard adopted across biomedical research workflows (e.g., MetaboLights, FAIRDOM, BioSamples). It captures the context in which the data were generated: project identity, funding source, authorship with persistent identifiers (ORCID), licensing terms, and discoverability keywords, therefore supporting the Findable, Accessible and Reusable dimensions of the FAIR principles

---

### `SAMPLE` — Biological sample analyzed

| Field       | Description            | Example   | Source |
| ----------- | -------------------------------- | --------- | ------ |
| `sample_id` | unique ID of the sample analyzed | SB00x OCT | MIABIS |

#### `SAMPLE/SAMPLE_INFO`

| Field                  | Description                                                                                              | Example                                      | Source            |
| ---------------------- | -------------------------------------------------------------------------------------------------------- | -------------------------------------------- | ----------------- |
| `provenance`           | Clinical institution that collected and provided the sample                                              | ICS Maugeri                                  |                   |
| `sample_type`          | High-level biological sample category, aligned with the aggregated `Sample type` attribute of MIABIS Core 3.0 | Tissue                                  | MIABIS Core 3.0   |
| `detailed_sample_type` | Granular sample category, encoded according to the controlled vocabulary of `MIABIS-SAMPLE-02` (Sample type) | Plasma                                   | MIABIS-SAMPLE-02  |
| `sample_source`        | Biological source from which the sample was collected, encoded according to `MIABIS-SAMPLE-12`           | Human / Animal / Environment                 | MIABIS-SAMPLE-12  |
| `anatomical_site`      | Anatomical source of the sample material (`MIABIS-SAMPLE-05`)                                            | Blood                                        | MIABIS-SAMPLE-05  |
| `anatomical_ontology`  | Reference ontology used to encode the anatomical site (`MIABIS-SAMPLE-05-01`)                            | UBERON                                       | MIABIS-SAMPLE-05-01 |
| `anatomical_site_code` | Anatomical site identifier from the selected ontology version (`MIABIS-SAMPLE-05-03`)                    | 0000178                                      | MIABIS-SAMPLE-05-03 |
| `storage_temperature`  | Long-term storage temperature, encoded as one of the SPREC v4-based ranges defined in `MIABIS-SAMPLE-03` | -60 °C to -85 °C                             | MIABIS-SAMPLE-03  |
| `processing_method`    | Pre-analytical protocol applied to obtain the sample from the primary specimen                           | Plasma preparation by double centrifugation  |                   |
| `sample_creation_date` | Date of sample collection in ISO 8601 format (`MIABIS-SAMPLE-04`)                                        | yyyy-mm-dd                                   | MIABIS-SAMPLE-04  |
| `notes`                | Free-text field for additional information not covered by the structured metadata                        |                                              |                   |

#### `SAMPLE/SAMPLE_DONOR`

| Field                | Description                                                                                                                                | Example   | Source           |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ | --------- | ---------------- |
| `donor_id`           | Pseudonymised, persistent identifier of the sample donor (`MIABIS-DONOR-01 — Sample donor ID`)                                             | AD123     | MIABIS-DONOR-01  |
| `sex`                | Sex of the donor, encoded according to the controlled vocabulary of `MIABIS-DONOR-02` (Male, Female, Unknown, Undifferentiated, Not applicable) | F      | MIABIS-DONOR-02  |
| `age`                | Age of the donor at the time of sample collection, expressed in years                                                                      | 77        |                  |
| `diagnosis_code`     | Diagnosis code associated with the donor, encoded according to a recognised classification (e.g. ICD-10, ORPHA)                            | G30       | MIABIS           |
| `diagnosis_ontology` | Classification system used to encode the diagnosis                                                                                         | ICD-10    | MIABIS           |
| `diagnosis_notes`    | Free-text field for additional clinical context not captured by the structured diagnosis code                                              |           |                  |

#### `SAMPLE/SAMPLE_EVENT`

| Field               | Description                                             | Example    | Source |
| ------------------- | ---------------------------------------------------------------------------- | ----------------- | ------ |
| `date`              | Date of the event                                                            | yyyy-mm-dd        | MIABIS |
| `event_description` | Description of the processing that the sample undergo before analysis        | sectioned 10 um   | MIABIS |


The SAMPLE section corresponds to the Study layer of the ISA model and aligns with the MIABIS (Minimum Information About BIobank data Sharing) terminology maintained by BBMRI-ERIC, the de-facto standard for describing biological samples and their donors in biobanking and biomedical research workflows. It captures the biological material under investigation across three complementary perspectives: the sample itself (SAMPLE_INFO, aligned with the MIABIS Sample component v1.1 and SPREC v4), the donor from whom it originated (SAMPLE_DONOR, aligned with the MIABIS Sample Donor component v1.1), and the events the sample undergoes prior to analysis (SAMPLE_EVENT, aligned with the MIABIS Event component). Encoding provenance, anatomical source, storage conditions, donor demographics and diagnosis through controlled vocabularies and recognised ontologies (UBERON, ICD-10, ORPHA) supports the Interoperable and Reusable dimensions of the FAIR principles, while persistent sample and donor identifiers ensure Findability and unambiguous linkage to the corresponding spectroscopic measurements at the Assay level.

---

### `ENTRY` — Aquistion parameters

| Field             | Description                             | Example                            | Source |
| ----------------- | --------------------------------------- | ---------------------------------- | ------ |
| `title`           | Name of the original file (autogenerated)                                                            | AD123-HDL-1-4                      | NeXus  |
| `experiment_type` | Type of experiment performed, encoded according to the NXraman application definition                | raman spectroscopy                 | NeXus  |
| `run_type`        | Acquisition mode of the measurement                                                                  | single / map / timeseries          |        |
| `start_time`      | Date and time at which the acquisition started                                                       | yyyy-mm-dd                         | NeXus  |
| `data_type`       | Nature of the data encoded                                                                           | experimental / simulated / derived |        |

#### `ENTRY/measurement`

| Field                 | Description                                                                          | Example | Source |
| --------------------- | ------------------------------------------------------------------------------------ | ------- | ------ |
| `exposure_time`       | Integration time of a single acquisition                                             | 10      | NeXus  |
| `exposure_time_units` | Unit in which `exposure_time` is expressed                                           | sec     | NeXus  |
| `substrate`           | Material of the support on which the sample is deposited during the measurement      | CaF2    |        |
| `accumulation_count`  | Number of consecutive acquisitions co-added to produce the final spectrum            | 15      | NeXus  |

#### `ENTRY/instrument`

| Field  | Description                                 | Example        | Source |
| ------ | ------------------------------------------- | -------------- | ------ |
| `name` | Model of the instrument (eventually code)   | Renishaw inVia | NeXus  |

#### `ENTRY/instrument/laser`

| Field              | Description                                                                                       | Example | Source |
| ------------------ | ------------------------------------------------------------------------------------------------- | ------- | ------ |
| `wavelength`       | Excitation wavelength of the laser source                                                         | 632.8   | NeXus  |
| `wavelength_units` | Unit in which `wavelength` is expressed                                                           | nm      | NeXus  |
| `filter`           | Fraction of the nominal laser power transmitted to the sample by neutral density filtering        | 100%    | NeXus  |

#### `ENTRY/instrument/optical_system`

| Field  | Description                            | Example | Source |
| ------ | -------------------------------------- | ------- | ------ |
| `lens` | Lens (objective) used to collect light | 100x    | NeXus  |

#### `ENTRY/data`

Structural descriptors of the spectral hypercube. These fields are derived automatically from the dataset shape and do not require manual entry.

| Field            | Description                                             | Example | Source |
| ---------------- | ------------------------------------------------------- | ------- | ------ |
| `spectral_count` | Structural descriptors of the spectral hypercube. These fields are derived automatically from the dataset shape and do not require manual entry. (ny × nx)            | 1024    | auto   |
| `nx`             | Number of spatial sampling points along the "x" axis                 | 32      | auto   |
| `ny`             | Number of spatial sampling points along the "y" axis                 | 32      | auto   |
| `n_wavenumbers`  | Number of points along the spectral (wavenumber) axis                  | 1015    | auto   |

The ENTRY section corresponds to the Assay layer of the ISA model and aligns with the NXraman application definition of the NeXus standard, the reference schema for storing Raman spectroscopy data in a domain-specific, machine-actionable form. It captures the full experimental fingerprint of a single acquisition — instrument identity, laser excitation, optical configuration, integration and accumulation parameters, substrate, and the structural shape of the resulting spectral hypercube — so that any recorded spectrum can be unambiguously interpreted, reproduced, and compared across instruments and laboratories. Adopting NeXus naming conventions and units, complemented by automatically derived structural descriptors, supports the Interoperable and Reusable dimensions of the FAIR principles, while explicit linkage to the upstream PROJECT (Investigation) and SAMPLE (Study) sections preserves the full provenance chain from research context through biological material to instrumental measurement.

