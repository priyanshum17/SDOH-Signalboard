"""Enrich Synthea FHIR bundles with PRAPARE SDOH observations.

Reads Synthea output from synthea/output/fhir/, adds SDOH screening
Observations with proper PRAPARE LOINC codes, tags all resources with
meta.tag for HAPI FHIR filtering, and writes enriched bundles to
demo_data/fhir_bundles/.

Usage:
    uv run python demo_data/enrich_synthea.py
"""

import json
import random
import uuid
from pathlib import Path

SYNTHEA_DIR = Path(__file__).resolve().parent.parent / "synthea" / "output" / "fhir"
OUTPUT_DIR = Path(__file__).resolve().parent / "fhir_bundles"
MAX_PATIENTS = 30

TAG_SYSTEM = "https://sdoh-demo"
TAG_CODE = "sdoh-project"
META_TAG = {"system": TAG_SYSTEM, "code": TAG_CODE, "display": "SDOH Risk Project"}

# PRAPARE SDOH LOINC question codes and risk answer codes
SDOH_QUESTIONS = [
    {
        "loinc": "71802-3",
        "display": "Housing status",
        "risk_answers": [
            {"code": "LA30186-3", "display": "I do not have steady housing"},
            {"code": "LA30187-1", "display": "I am worried about losing my housing"},
        ],
        "safe_answers": [
            {"code": "LA30188-9", "display": "I have housing"},
        ],
        "risk_probability": 0.45,
    },
    {
        "loinc": "88122-7",
        "display": "Food insecurity screening",
        "risk_answers": [
            {"code": "LA33-6", "display": "Yes"},
        ],
        "safe_answers": [
            {"code": "LA32-8", "display": "No"},
        ],
        "risk_probability": 0.45,
    },
    {
        "loinc": "93030-5",
        "display": "Transportation barrier",
        "risk_answers": [
            {"code": "LA33-6", "display": "Yes"},
        ],
        "safe_answers": [
            {"code": "LA32-8", "display": "No"},
        ],
        "risk_probability": 0.35,
    },
    {
        "loinc": "67875-5",
        "display": "Employment status",
        "risk_answers": [
            {"code": "LA17958-2", "display": "Unemployed"},
            {"code": "LA18005-1", "display": "Otherwise unemployed but not seeking work"},
        ],
        "safe_answers": [
            {"code": "LA17956-6", "display": "Full-time work"},
            {"code": "LA17957-4", "display": "Part-time or temporary work"},
        ],
        "risk_probability": 0.35,
    },
    {
        "loinc": "93038-8",
        "display": "Stress level",
        "risk_answers": [
            {"code": "LA13914-9", "display": "Quite a bit"},
            {"code": "LA13902-4", "display": "Very much"},
        ],
        "safe_answers": [
            {"code": "LA13863-8", "display": "Not at all"},
            {"code": "LA13909-9", "display": "A little bit"},
        ],
        "risk_probability": 0.30,
    },
]


def _make_sdoh_observation(patient_ref: str, question: dict, at_risk: bool) -> dict:
    """Create a single PRAPARE SDOH Observation resource."""
    if at_risk:
        answer = random.choice(question["risk_answers"])
    else:
        answer = random.choice(question["safe_answers"])

    return {
        "resourceType": "Observation",
        "id": str(uuid.uuid4()),
        "meta": {"tag": [META_TAG]},
        "status": "final",
        "category": [
            {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                        "code": "social-history",
                        "display": "Social History",
                    }
                ]
            }
        ],
        "code": {
            "coding": [
                {
                    "system": "http://loinc.org",
                    "code": question["loinc"],
                    "display": question["display"],
                }
            ],
            "text": question["display"],
        },
        "subject": {"reference": patient_ref},
        "valueCodeableConcept": {
            "coding": [
                {
                    "system": "http://loinc.org",
                    "code": answer["code"],
                    "display": answer["display"],
                }
            ],
            "text": answer["display"],
        },
    }


def _add_meta_tag(resource: dict) -> dict:
    """Ensure the resource has our project meta tag."""
    if "meta" not in resource:
        resource["meta"] = {}
    tags = resource["meta"].get("tag", [])
    if not any(t.get("code") == TAG_CODE for t in tags):
        tags.append(META_TAG)
    resource["meta"]["tag"] = tags
    return resource


def enrich_bundle(bundle: dict) -> dict:
    """Add SDOH observations and meta tags to a Synthea bundle."""
    # Find the Patient resource
    patient_ref = None
    for entry in bundle.get("entry", []):
        res = entry.get("resource", {})
        if res.get("resourceType") == "Patient":
            patient_ref = f"Patient/{res['id']}"
            _add_meta_tag(res)
            break

    if not patient_ref:
        return bundle

    # Tag all existing resources
    for entry in bundle.get("entry", []):
        res = entry.get("resource", {})
        _add_meta_tag(res)

    # Generate SDOH observations
    for question in SDOH_QUESTIONS:
        at_risk = random.random() < question["risk_probability"]
        obs = _make_sdoh_observation(patient_ref, question, at_risk)
        entry = {
            "fullUrl": f"urn:uuid:{obs['id']}",
            "resource": obs,
            "request": {"method": "POST", "url": "Observation"},
        }
        bundle["entry"].append(entry)

    return bundle


def main():
    if not SYNTHEA_DIR.exists():
        print(f"Synthea output not found at {SYNTHEA_DIR}")
        print("Run Synthea first: cd synthea && java -jar synthea-with-dependencies.jar -p 30")
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    synthea_files = sorted(SYNTHEA_DIR.glob("*.json"))[:MAX_PATIENTS]
    print(f"Found {len(synthea_files)} Synthea bundles in {SYNTHEA_DIR}")

    for i, fpath in enumerate(synthea_files, 1):
        with open(fpath) as f:
            bundle = json.load(f)

        enriched = enrich_bundle(bundle)

        out_path = OUTPUT_DIR / f"patient_{i:03d}.json"
        with open(out_path, "w") as f:
            json.dump(enriched, f, indent=2)

        # Count resources
        n_resources = len(enriched.get("entry", []))
        patient_name = "unknown"
        for entry in enriched.get("entry", []):
            res = entry.get("resource", {})
            if res.get("resourceType") == "Patient":
                names = res.get("name", [{}])
                if names:
                    given = names[0].get("given", [""])[0]
                    family = names[0].get("family", "")
                    patient_name = f"{given} {family}".strip()
                break

        print(f"  [{i:02d}/{len(synthea_files)}] {patient_name} -> {out_path.name} ({n_resources} resources)")

    print(f"\nDone. {len(synthea_files)} enriched bundles written to {OUTPUT_DIR}")
    print(f"All resources tagged with meta.tag = {TAG_CODE}")


if __name__ == "__main__":
    main()
