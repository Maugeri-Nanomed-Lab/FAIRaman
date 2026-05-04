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

### `SAMPLE` — campione biologico

| Field       | Description            | Example   | Source |
| ----------- | -------------------------------- | --------- | ------ |
| `sample_id` | unique ID of the sample analyzed | SB00x OCT | MIABIS |

#### `SAMPLE/SAMPLE_INFO`

| Field                  | Description                                              | Example                                      | Source |
| ---------------------- | -------------------------------------------------------- | -------------------------------------------- | ------ |
| `provenance`           | Clinical institution that provided the sample            | ICS Maugeri                                  |        |
| `sample_type`          | Type of biological sample                                | Tissue                                       | MIABIS |
| `detailed_sample_type` | Detailed type of biological sample analyzed according to MIABIS-SAMPLE-02 |                                              |        |

| `sample_source`        | Fonte da cui è stato raccolto il campione                | human / animal / environmental               | MIABIS |
| `anatomical_site`      | Sito anatomico del campione                              | blood                                        | MIABIS |
| `anatomical_site_code` | Codice del sito anatomico                                | 0000178                                      | MIABIS |
| `anatomical_ontology`  | Ontologia usata per il sito anatomico                    | UBERON                                       | MIABIS |
| `storage_temperature`  | Temperatura di conservazione a lungo termine (°C)        | -80 °C                                       | MIABIS |
| `processing_method`    | Protocollo di preparazione del campione                  | plasma preparation by double centrifugation  |        |
| `sample_creation_date` | Data di raccolta del campione                            | yyyy-mm-dd                                   |        |
| `notes`                | Note libere                                              |                                              |        |

#### `SAMPLE/SAMPLE_DONOR`

| Field                | Description                                            | Example | Source |
| -------------------- | ------------------------------------------------------ | ------- | ------ |
| `donor_id`           | ID of the donor                                        | AD123   | MIABIS |
| `sex`                | Sex of the donor                                       | F       | MIABIS |
| `age`                | Age of the donor                                       | 77      |        |
| `diagnosis_code`     | Codice diagnosi                                        | G30     | MIABIS |
| `diagnosis_ontology` | Ontologia usata per la diagnosi                        | ICD-10  | MIABIS |
| `diagnosis_notes`    | Note libere sulla diagnosi                             |         |        |

#### `SAMPLE/SAMPLE_EVENT`

| Field               | Description                                             | Example    | Source |
| ------------------- | ---------------------------------------------------------------------------- | ----------------- | ------ |
| `date`              | Date of the event                                                            | yyyy-mm-dd        | MIABIS |
| `event_description` | Description of the processing that the sample undergo before analysis        | sectioned 10 um   | MIABIS |

---

### `ENTRY` — singola acquisizione

| Field             | Description                             | Example                            | Source |
| ----------------- | --------------------------------------- | ---------------------------------- | ------ |
| `title`           | Nome del file (auto)                    | AD123-HDL-1-4                      | NeXus  |
| `experiment_type` | Tipo di analisi eseguita                | raman spectroscopy                 | NeXus  |
| `run_type`        | Modalità di acquisizione                | single / map / timeseries          |        |
| `start_time`      | Data dell'analisi                       | yyyy-mm-dd                         | NeXus  |
| `data_type`       | Tipo di dataset                         | experimental / simulated / derived |        |

#### `ENTRY/measurement`

| Field                 | Description                                    | Example | Source |
| --------------------- | ---------------------------------------------- | ------- | ------ |
| `exposure_time`       | Tempo di esposizione                           | 10      | NeXus  |
| `exposure_time_units` | Unità del tempo di esposizione                 | sec     | NeXus  |
| `substrate`           | Materiale su cui è depositato il campione      | CaF2    |        |
| `accumulation_count`  | Numero di accumulazioni                        | 15      | NeXus  |

#### `ENTRY/instrument`

| Field  | Description      | Example        | Source |
| ------ | ---------------- | -------------- | ------ |
| `name` | Nome strumento   | Renishaw inVia | NeXus  |

#### `ENTRY/instrument/laser`

| Field              | Description                                              | Example | Source |
| ------------------ | -------------------------------------------------------- | ------- | ------ |
| `wavelength`       | Lunghezza d'onda del laser                               | 632.8   | NeXus  |
| `wavelength_units` | Unità della lunghezza d'onda                             | nm      | NeXus  |
| `filter`           | Percentuale di luce laser che arriva sul campione        | 100%    | NeXus  |

#### `ENTRY/instrument/optical_system`

| Field  | Description              | Example | Source |
| ------ | ------------------------ | ------- | ------ |
| `lens` | Obiettivo del microscopio | 100x    | NeXus  |

#### `ENTRY/data`

Descrittori strutturali del cubo spettrale. Sono calcolati automaticamente
dalla shape del cubo; l'utente non deve fornirli.

| Field            | Description                                             | Example | Source |
| ---------------- | ------------------------------------------------------- | ------- | ------ |
| `spectral_count` | Numero totale di spettri acquisiti (ny × nx)            | 1024    | auto   |
| `nx`             | Numero di punti spaziali lungo l'asse x                 | 32      | auto   |
| `ny`             | Numero di punti spaziali lungo l'asse y                 | 32      | auto   |
| `n_wavenumbers`  | Numero di punti lungo l'asse spettrale                  | 1015    | auto   |
