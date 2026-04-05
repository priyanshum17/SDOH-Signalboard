"""Generate 30 synthetic FHIR R4 patient transaction bundles.

Each bundle contains:
  - Patient resource (demographics)
  - Observation resources (PRAPARE / SDOH screening, using real LOINC codes)
  - Condition resources (chronic diseases, using SNOMED‑CT codes)
  - Encounter resources (ambulatory, ED, inpatient — dated over last 12 months)

Usage:
    python demo_data/generate_patients.py          # writes to demo_data/fhir_bundles/
    python demo_data/generate_patients.py --count 50
"""

from __future__ import annotations

import argparse
import json
import os
import random
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

# ---------------------------------------------------------------------------
# Constants – authoritative LOINC / SNOMED codes
# ---------------------------------------------------------------------------

# PRAPARE panel code
PRAPARE_PANEL_CODE = "93025-5"

# Individual PRAPARE question LOINC codes
LOINC = {
    "housing":    "71802-3",   # Housing status
    "food":       "88122-7",   # Within the past 12 months you worried food would run out
    "transport":  "93030-5",   # Has lack of transportation kept you from medical appointments
    "employment": "67875-5",   # Employment status
    "education":  "82589-3",   # Highest level of education
    "stress":     "93038-8",   # Stress level
    "safety":     "93033-9",   # How often does anyone physically hurt you
}

# Answer codes (LOINC answer list)
HOUSING_ANSWERS = {
    "stable":   {"code": "LA30185-5", "display": "I have housing"},
    "unstable": {"code": "LA30186-3", "display": "I do not have steady housing"},
    "worried":  {"code": "LA30187-1", "display": "I am worried about losing my housing"},
}

FOOD_ANSWERS = {
    "no":  {"code": "LA32-8",  "display": "No"},
    "yes": {"code": "LA33-6",  "display": "Yes"},
}

TRANSPORT_ANSWERS = {
    "no":  {"code": "LA32-8",  "display": "No"},
    "yes": {"code": "LA33-6",  "display": "Yes"},
}

EMPLOYMENT_ANSWERS = {
    "employed_ft":  {"code": "LA17956-6", "display": "Full-time work"},
    "employed_pt":  {"code": "LA17957-4", "display": "Part-time work"},
    "unemployed":   {"code": "LA17958-2", "display": "Otherwise unemployed but not seeking work"},
    "seeking":      {"code": "LA18005-1", "display": "Unemployed and seeking work"},
}

STRESS_ANSWERS = {
    "not_at_all": {"code": "LA6568-5", "display": "Not at all"},
    "a_little":   {"code": "LA13863-8", "display": "A little bit"},
    "somewhat":   {"code": "LA13909-9", "display": "Somewhat"},
    "quite_a_bit":{"code": "LA13914-9", "display": "Quite a bit"},
    "very_much":  {"code": "LA13902-4", "display": "Very much"},
}

# Chronic condition SNOMED codes
CONDITIONS = {
    "diabetes_type2":  {"code": "44054006",  "display": "Diabetes mellitus type 2",       "system": "http://snomed.info/sct"},
    "diabetes_type1":  {"code": "73211009",  "display": "Diabetes mellitus",              "system": "http://snomed.info/sct"},
    "hypertension":    {"code": "38341003",  "display": "Hypertension",                   "system": "http://snomed.info/sct"},
    "copd":            {"code": "13645005",  "display": "Chronic obstructive lung disease","system": "http://snomed.info/sct"},
    "depression":      {"code": "35489007",  "display": "Depressive disorder",            "system": "http://snomed.info/sct"},
    "asthma":          {"code": "195967001", "display": "Asthma",                         "system": "http://snomed.info/sct"},
    "ckd":             {"code": "709044004", "display": "Chronic kidney disease",         "system": "http://snomed.info/sct"},
    "heart_failure":   {"code": "84114007",  "display": "Heart failure",                  "system": "http://snomed.info/sct"},
}

# Encounter class codes (V3 ActCode)
ENCOUNTER_CLASSES = {
    "ambulatory": {"code": "AMB",  "display": "ambulatory",           "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode"},
    "emergency":  {"code": "EMER", "display": "emergency",            "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode"},
    "inpatient":  {"code": "IMP",  "display": "inpatient encounter",  "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode"},
}

# Names pool
FIRST_NAMES_M = ["James","Robert","Michael","William","David","John","Carlos","Ahmed","Wei","Raj",
                 "Marcus","Antonio","Dmitri","Sean","Tyrone","Hiroshi","Samuel","Andres","Kwame","Ibrahim"]
FIRST_NAMES_F = ["Maria","Jennifer","Linda","Patricia","Elizabeth","Sarah","Fatima","Mei","Priya","Aisha",
                 "Carmen","Yuki","Olga","Thandiwe","Rosa","Nalini","Grace","Amina","Soo-Jin","Esperanza"]
LAST_NAMES = ["Smith","Johnson","Williams","Brown","Jones","Garcia","Martinez","Rodriguez","Lee","Walker",
              "Hall","Allen","Young","King","Wright","Lopez","Hill","Scott","Green","Adams",
              "Baker","Gonzalez","Nelson","Carter","Mitchell","Perez","Roberts","Turner","Phillips","Campbell"]


# ---------------------------------------------------------------------------
# Profile templates  — controls the distribution of SDOH / clinical risk
# ---------------------------------------------------------------------------

RISK_PROFILES = [
    # (weight, sdoh_config, conditions, encounter_pattern)
    # --- HIGH RISK (8 patients) ---
    {"weight": 4, "housing": "unstable", "food": "yes", "transport": "yes", "employment": "seeking",
     "stress": "very_much", "conditions": ["diabetes_type2", "hypertension"],
     "enc_pattern": "high_ed", "age_range": (55, 85)},
    {"weight": 2, "housing": "worried", "food": "yes", "transport": "yes", "employment": "unemployed",
     "stress": "quite_a_bit", "conditions": ["diabetes_type2", "depression"],
     "enc_pattern": "high_ed", "age_range": (40, 75)},
    {"weight": 2, "housing": "unstable", "food": "yes", "transport": "no", "employment": "seeking",
     "stress": "quite_a_bit", "conditions": ["copd", "hypertension", "depression"],
     "enc_pattern": "high_ed", "age_range": (60, 85)},

    # --- MEDIUM RISK (12 patients) ---
    {"weight": 3, "housing": "worried", "food": "no", "transport": "yes", "employment": "employed_pt",
     "stress": "somewhat", "conditions": ["hypertension"],
     "enc_pattern": "moderate", "age_range": (35, 70)},
    {"weight": 3, "housing": "stable", "food": "yes", "transport": "no", "employment": "employed_ft",
     "stress": "somewhat", "conditions": ["diabetes_type2"],
     "enc_pattern": "moderate", "age_range": (30, 65)},
    {"weight": 3, "housing": "stable", "food": "no", "transport": "yes", "employment": "seeking",
     "stress": "a_little", "conditions": ["asthma"],
     "enc_pattern": "moderate", "age_range": (22, 55)},
    {"weight": 3, "housing": "worried", "food": "yes", "transport": "no", "employment": "employed_pt",
     "stress": "quite_a_bit", "conditions": ["depression", "hypertension"],
     "enc_pattern": "moderate", "age_range": (28, 60)},

    # --- LOW RISK (10 patients) ---
    {"weight": 4, "housing": "stable", "food": "no", "transport": "no", "employment": "employed_ft",
     "stress": "not_at_all", "conditions": [],
     "enc_pattern": "low", "age_range": (22, 45)},
    {"weight": 3, "housing": "stable", "food": "no", "transport": "no", "employment": "employed_ft",
     "stress": "a_little", "conditions": ["asthma"],
     "enc_pattern": "low", "age_range": (25, 55)},
    {"weight": 3, "housing": "stable", "food": "no", "transport": "no", "employment": "employed_pt",
     "stress": "not_at_all", "conditions": [],
     "enc_pattern": "low", "age_range": (65, 85)},
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uuid() -> str:
    return str(uuid.uuid4())


def _random_date(start: datetime, end: datetime) -> str:
    delta = end - start
    random_days = random.randint(0, max(delta.days, 1))
    dt = start + timedelta(days=random_days)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _random_birth_date(age_low: int, age_high: int) -> tuple[str, int]:
    age = random.randint(age_low, age_high)
    year = datetime.now().year - age
    month = random.randint(1, 12)
    day = random.randint(1, 28)
    return f"{year:04d}-{month:02d}-{day:02d}", age


def _build_patient(pid: str, gender: str, first: str, last: str, birth_date: str) -> Dict[str, Any]:
    return {
        "resourceType": "Patient",
        "id": pid,
        "meta": {"profile": ["http://hl7.org/fhir/us/core/StructureDefinition/us-core-patient"]},
        "identifier": [{"system": "urn:oid:2.16.840.1.113883.4.3.25", "value": _uuid()[:8].upper()}],
        "name": [{"use": "official", "family": last, "given": [first]}],
        "gender": gender,
        "birthDate": birth_date,
        "address": [{"use": "home", "city": random.choice(["Atlanta","Boston","Chicago","Denver","Houston","Miami","Phoenix","Seattle"]),
                     "state": random.choice(["GA","MA","IL","CO","TX","FL","AZ","WA"]), "country": "US"}],
        "telecom": [{"system": "phone", "value": f"555-{random.randint(100,999)}-{random.randint(1000,9999)}", "use": "home"}],
    }


def _build_sdoh_observation(patient_ref: str, loinc_code: str, loinc_display: str,
                            answer: Dict[str, str], obs_date: str) -> Dict[str, Any]:
    return {
        "resourceType": "Observation",
        "id": _uuid(),
        "status": "final",
        "category": [
            {
                "coding": [
                    {"system": "http://terminology.hl7.org/CodeSystem/observation-category",
                     "code": "social-history", "display": "Social History"},
                    {"system": "http://terminology.hl7.org/CodeSystem/observation-category",
                     "code": "survey", "display": "Survey"},
                ]
            },
            {
                "coding": [
                    {"system": "http://terminology.hl7.org/CodeSystem/SDOH-category",
                     "code": "sdoh", "display": "SDOH"}
                ]
            }
        ],
        "code": {
            "coding": [{"system": "http://loinc.org", "code": loinc_code, "display": loinc_display}],
            "text": loinc_display,
        },
        "subject": {"reference": f"Patient/{patient_ref}"},
        "effectiveDateTime": obs_date,
        "valueCodeableConcept": {
            "coding": [{"system": "http://loinc.org", "code": answer["code"], "display": answer["display"]}],
            "text": answer["display"],
        },
    }


def _build_condition(patient_ref: str, cond_info: Dict[str, str], onset_date: str) -> Dict[str, Any]:
    return {
        "resourceType": "Condition",
        "id": _uuid(),
        "meta": {"profile": ["http://hl7.org/fhir/us/core/StructureDefinition/us-core-condition"]},
        "clinicalStatus": {
            "coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                         "code": "active", "display": "Active"}]
        },
        "verificationStatus": {
            "coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-ver-status",
                         "code": "confirmed", "display": "Confirmed"}]
        },
        "category": [
            {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-category",
                          "code": "encounter-diagnosis", "display": "Encounter Diagnosis"}]}
        ],
        "code": {
            "coding": [{"system": cond_info["system"], "code": cond_info["code"], "display": cond_info["display"]}],
            "text": cond_info["display"],
        },
        "subject": {"reference": f"Patient/{patient_ref}"},
        "onsetDateTime": onset_date,
    }


def _build_encounter(patient_ref: str, enc_class: Dict[str, str], start: str, end: str, status: str = "finished") -> Dict[str, Any]:
    return {
        "resourceType": "Encounter",
        "id": _uuid(),
        "status": status,
        "class": {"system": enc_class["system"], "code": enc_class["code"], "display": enc_class["display"]},
        "type": [
            {"coding": [{"system": "http://snomed.info/sct",
                          "code": "308335008" if enc_class["code"] == "AMB" else
                                  "50849002" if enc_class["code"] == "EMER" else "32485007",
                          "display": "Patient encounter procedure" if enc_class["code"] == "AMB" else
                                     "Emergency department admission" if enc_class["code"] == "EMER" else
                                     "Hospital admission"}],
             "text": enc_class["display"]}
        ],
        "subject": {"reference": f"Patient/{patient_ref}"},
        "period": {"start": start, "end": end},
    }


def _generate_encounters(patient_ref: str, pattern: str, now: datetime) -> List[Dict[str, Any]]:
    encounters = []
    twelve_months_ago = now - timedelta(days=365)

    if pattern == "high_ed":
        # 3-5 ED visits + 2-4 ambulatory in last 12 months
        n_ed = random.randint(3, 5)
        n_amb = random.randint(2, 4)
    elif pattern == "moderate":
        # 0-2 ED visits + 2-5 ambulatory
        n_ed = random.randint(0, 2)
        n_amb = random.randint(2, 5)
    else:  # low
        # 0-1 ED + 1-2 ambulatory
        n_ed = random.randint(0, 1)
        n_amb = random.randint(1, 2)

    for _ in range(n_ed):
        start_dt = twelve_months_ago + timedelta(days=random.randint(0, 365))
        end_dt = start_dt + timedelta(hours=random.randint(2, 12))
        encounters.append(_build_encounter(patient_ref, ENCOUNTER_CLASSES["emergency"],
                                           start_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                           end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")))

    for _ in range(n_amb):
        start_dt = twelve_months_ago + timedelta(days=random.randint(0, 365))
        end_dt = start_dt + timedelta(hours=1)
        encounters.append(_build_encounter(patient_ref, ENCOUNTER_CLASSES["ambulatory"],
                                           start_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                           end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")))

    # Occasional inpatient for high-risk
    if pattern == "high_ed" and random.random() < 0.4:
        start_dt = twelve_months_ago + timedelta(days=random.randint(0, 300))
        end_dt = start_dt + timedelta(days=random.randint(2, 7))
        encounters.append(_build_encounter(patient_ref, ENCOUNTER_CLASSES["inpatient"],
                                           start_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                           end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")))

    return encounters


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------

def generate_patient_bundle(profile: Dict, gender: str, first: str, last: str) -> Dict[str, Any]:
    pid = _uuid()
    now = datetime.utcnow()
    birth_date, age = _random_birth_date(*profile["age_range"])
    screening_date = _random_date(now - timedelta(days=90), now)

    entries: List[Dict[str, Any]] = []

    # --- Patient ---
    patient = _build_patient(pid, gender, first, last, birth_date)
    entries.append({
        "fullUrl": f"urn:uuid:{pid}",
        "resource": patient,
        "request": {"method": "PUT", "url": f"Patient/{pid}"},
    })

    # --- SDOH Observations ---
    sdoh_obs = [
        (LOINC["housing"], "Housing status",
         HOUSING_ANSWERS[profile["housing"]]),
        (LOINC["food"], "Within the past 12 months you worried food would run out",
         FOOD_ANSWERS[profile["food"]]),
        (LOINC["transport"], "Has lack of transportation kept you from medical appointments",
         TRANSPORT_ANSWERS[profile["transport"]]),
        (LOINC["employment"], "Employment status",
         EMPLOYMENT_ANSWERS[profile["employment"]]),
        (LOINC["stress"], "Stress level",
         STRESS_ANSWERS[profile["stress"]]),
    ]

    for loinc_code, display, answer in sdoh_obs:
        obs = _build_sdoh_observation(pid, loinc_code, display, answer, screening_date)
        entries.append({
            "fullUrl": f"urn:uuid:{obs['id']}",
            "resource": obs,
            "request": {"method": "PUT", "url": f"Observation/{obs['id']}"},
        })

    # --- Conditions ---
    for cond_key in profile["conditions"]:
        cond_info = CONDITIONS[cond_key]
        # Onset 1-10 years ago
        onset = _random_date(now - timedelta(days=365 * 10), now - timedelta(days=365))
        cond = _build_condition(pid, cond_info, onset)
        entries.append({
            "fullUrl": f"urn:uuid:{cond['id']}",
            "resource": cond,
            "request": {"method": "PUT", "url": f"Condition/{cond['id']}"},
        })

    # --- Encounters ---
    encounters = _generate_encounters(pid, profile["enc_pattern"], now)
    for enc in encounters:
        entries.append({
            "fullUrl": f"urn:uuid:{enc['id']}",
            "resource": enc,
            "request": {"method": "PUT", "url": f"Encounter/{enc['id']}"},
        })

    return {
        "resourceType": "Bundle",
        "type": "transaction",
        "entry": entries,
    }


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic FHIR patient bundles")
    parser.add_argument("--count", type=int, default=30, help="Number of patients to generate")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    args = parser.parse_args()

    random.seed(args.seed)

    output_dir = Path(__file__).resolve().parent / "fhir_bundles"
    output_dir.mkdir(exist_ok=True)

    # Build weighted profile list
    profiles: List[Dict] = []
    for p in RISK_PROFILES:
        profiles.extend([p] * p["weight"])

    all_entries: List[Dict[str, Any]] = []

    for i in range(args.count):
        profile = profiles[i % len(profiles)]
        gender = random.choice(["male", "female"])
        first = random.choice(FIRST_NAMES_M if gender == "male" else FIRST_NAMES_F)
        last = random.choice(LAST_NAMES)

        bundle = generate_patient_bundle(profile, gender, first, last)

        # Write individual bundle
        fname = output_dir / f"patient_{i+1:03d}.json"
        with open(fname, "w") as f:
            json.dump(bundle, f, indent=2)

        all_entries.extend(bundle["entry"])
        print(f"  [{i+1:3d}/{args.count}] {first} {last} — {len(bundle['entry'])} resources")

    # Write combined bundle
    combined = {"resourceType": "Bundle", "type": "transaction", "entry": all_entries}
    combined_path = Path(__file__).resolve().parent / "all_patients_bundle.json"
    with open(combined_path, "w") as f:
        json.dump(combined, f, indent=2)

    print(f"\n✓ Generated {args.count} patient bundles in {output_dir}/")
    print(f"✓ Combined bundle: {combined_path} ({len(all_entries)} entries)")


if __name__ == "__main__":
    main()
