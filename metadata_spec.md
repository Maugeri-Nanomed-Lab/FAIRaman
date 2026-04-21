## FAIRaman metadata schema

Campi dello schema FAIRaman, organizzati per gruppo. Tutti i campi sono
scritti nel file HDF5 anche quando vuoti, per garantire struttura
omogenea tra tutti i file prodotti.

---

### `PROJECT` — contesto dello studio

| Field           | Description            | Example                                          | Source |
| --------------- | ---------------------- | ------------------------------------------------ | ------ |
| `project_name`  | Nome del progetto      | Spectra-BREAST                                   |        |
| `project_id`    | ID del progetto        | 101187508                                        |        |
| `funding`       | Ente finanziatore      | European Innovation Council                      |        |
| `author`        | Autore/autori          | Davide Piccapietra                               |        |
| `author_id`     | ID autore/autori       | PCCDVD03                                         |        |
| `data_license`  | Licenza dati           | restricted                                       |        |
| `accessibility` | Accessibilità dati     | upon reasonable request                          |        |
| `keywords`      | Parole chiave          | Breast Cancer; Tissue Analysis; Surgical Margins |        |

---

### `SAMPLE` — campione biologico

| Field       | Description            | Example   | Source |
| ----------- | ---------------------- | --------- | ------ |
| `sample_id` | ID univoco del campione | AD123-HDL | MIABIS |

#### `SAMPLE/SAMPLE_INFO`

| Field                  | Description                                              | Example                                      | Source |
| ---------------------- | -------------------------------------------------------- | -------------------------------------------- | ------ |
| `provenance`           | Fonte clinica del campione                               | ICS Maugeri                                  |        |
| `sample_type`          | Tipo di campione biologico                               | plasma                                       | MIABIS |
| `detailed_sample_type` | Tipo di campione biologico per testing diagnostici       | plasma                                       | MIABIS |
| `sample_source`        | Fonte da cui è stato raccolto il campione                | human / animal / environmental               | MIABIS |
| `anatomical_site`      | Sito anatomico del campione                              | blood                                        | MIABIS |
| `anatomical_site_code` | Codice del sito anatomico                                | 0000178                                      | MIABIS |
| `anatomical_ontology`  | Ontologia usata per il sito anatomico                    | UBERON                                       | MIABIS |
| `storage_temperature`  | Temperatura di conservazione a lungo termine (°C)        | -80                                          | MIABIS |
| `processing_method`    | Protocollo di preparazione del campione                  | plasma preparation by double centrifugation  |        |
| `sample_creation_date` | Data di raccolta del campione                            | yyyy-mm-dd                                   |        |
| `notes`                | Note libere                                              |                                              |        |

#### `SAMPLE/SAMPLE_DONOR`

| Field                | Description                                            | Example | Source |
| -------------------- | ------------------------------------------------------ | ------- | ------ |
| `donor_id`           | ID del donatore                                        | AD123   | MIABIS |
| `sex`                | Sesso biologico del donatore                           | F       | MIABIS |
| `age`                | Età biologica del donatore                             | 77      |        |
| `diagnosis_code`     | Codice diagnosi                                        | G30     | MIABIS |
| `diagnosis_ontology` | Ontologia usata per la diagnosi                        | ICD-10  | MIABIS |
| `diagnosis_notes`    | Note libere sulla diagnosi                             |         |        |

#### `SAMPLE/SAMPLE_EVENT`

| Field               | Description                                             | Example    | Source |
| ------------------- | ------------------------------------------------------- | ---------- | ------ |
| `date`              | Data dell'evento                                        | yyyy-mm-dd |        |
| `event_description` | Descrizione della preparazione prima della misura       |            |        |

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
