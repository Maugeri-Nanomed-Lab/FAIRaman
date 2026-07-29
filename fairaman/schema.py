import numpy as np
import pandas as pd

NEXUS_SCHEMA = {
    "PROJECT": {
        "NX_class": "NXcollection",
        "fields": [
            "project_name", "project_id", "funding", "governance_reference", "author", "author_id",
            "data_license", "accessibility", "keywords"
        ]
    },
    "SAMPLE": {
        "NX_class": "NXsample",
        "fields": ["sample_id"],
        "subgroups": {
            "SAMPLE_INFO": {
                "fields": [
                    "sample_provenance", "sample_type", "detailed_sample_type", "sample_source",
                    "anatomical_site", "anatomical_site_code", "anatomical_ontology",
                    "storage_temperature", "processing_method",
                    "sample_creation_date", "sample_notes"
                ]
            },
            "SAMPLE_DONOR": {
                "fields": [
                    "donor_id", "donor_sex", "donor_age", "diagnosis_code",
                    "diagnosis_ontology", "diagnosis_notes"
                ]
            },
            "SAMPLE_EVENT": {
                "fields": [
                    "event_date", "event_description"
                ]
            }
        }
    },
    "ENTRY": {
        "NX_class": "NXentry",
        "definition": "NXraman",
        "fields": ["title", "experiment_type", "run_type", "start_time", "data_type"],
        "subgroups": {
            "measurement": {
                "NX_class": "NXcollection",
                "fields": [
                    "exposure_time", "exposure_time_units",
                    "substrate", "accumulation_count"
                ]
            },
            "instrument": {
                "NX_class": "NXinstrument",
                "fields": ["name"],
                "subgroups": {
                    "laser": {
                        "NX_class": "NXsource",
                        "fields": ["wavelength", "wavelength_units", "power", "power_units",  "filter"]
                    },
                    "optical_system": {
                        "NX_class": "NXoptics",
                        "fields": ["lens"]
                    }
                }
            }
        }
    }
}

def flatten_schema(schema: dict, prefix: str = "") -> list[str]:
    """
    Scansione di NEXUS_SCHEMA e restituisce una lista piatta
    dei percorsi HDF5 (es 'SAMPLE.SAMPLE_DONOR.diagnosis_code')

    Mi serve per popolare il menu a tendina nei campi della mappatura
    """
    paths = []
    for k, v in schema.items():
        if isinstance(v, dict):
            if "fields" in v:
                for field in v["fields"]:
                    paths.append(f"{prefix}.{k}.{field}" if prefix else f"{k}.{field}")
            if "subgroups" in v:
                paths.extend(
                    flatten_schema(v["subgroups"], f"{prefix}.{k}" if prefix else k)
                )
    return paths

HDF5_FIELDS = ["Do not map"] + flatten_schema(NEXUS_SCHEMA)
