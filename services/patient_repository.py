"""Assembles a patient‑level DataFrame by pulling FHIR resources and scoring.

Supports two modes:
  1. **Demo mode** (``USE_DEMO_DATA=true``, default) — reads pre-generated FHIR
     bundles from ``demo_data/fhir_bundles/`` for instant, offline operation.
  2. **Live mode** (``USE_DEMO_DATA=false``) — queries a real FHIR server
     (e.g. HAPI FHIR) via the FHIR client.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd
from pydantic import ValidationError as PydanticValidationError

# fhir.resources — Pydantic-based FHIR R4 models for validation
from fhir.resources.patient import Patient as FHIRPatient
from fhir.resources.observation import Observation as FHIRObservation

from config import get_settings
from domain import scoring
from services.fhir_client import get_client

log = logging.getLogger(__name__)


def _validate_patient(raw: Dict[str, Any]) -> bool:
    """Validate a raw Patient dict against the FHIR R4 Patient schema."""
    try:
        FHIRPatient.model_validate(raw)
        return True
    except PydanticValidationError as exc:
        log.debug("Patient validation failed for %s: %s", raw.get("id"), exc)
        return False


def _validate_observation(raw: Dict[str, Any]) -> bool:
    """Validate a raw Observation dict against the FHIR R4 Observation schema."""
    try:
        FHIRObservation.model_validate(raw)
        return True
    except PydanticValidationError as exc:
        log.debug("Observation validation failed for %s: %s", raw.get("id"), exc)
        return False

# ---------------------------------------------------------------------------
# Authoritative LOINC / SNOMED code sets (aligned with PRAPARE)
# ---------------------------------------------------------------------------

# SDOH observation LOINC codes → which flag they set
SDOH_CODE_MAP: Dict[str, str] = {
    "71802-3":  "housing",      # Housing status
    "88122-7":  "food",         # Food insecurity screening
    "93030-5":  "transport",    # Transportation barrier
    "67875-5":  "employment",   # Employment status
    "93038-8":  "stress",       # Stress level
}

# Answer codes that indicate a *positive* risk
HOUSING_RISK_ANSWERS  = {"LA30186-3", "LA30187-1"}  # unstable / worried
FOOD_RISK_ANSWERS     = {"LA33-6"}                   # "Yes"
TRANSPORT_RISK_ANSWERS = {"LA33-6"}                  # "Yes"
EMPLOYMENT_RISK_ANSWERS = {"LA17958-2", "LA18005-1"} # unemployed / seeking
STRESS_RISK_ANSWERS    = {"LA13914-9", "LA13902-4"}  # quite a bit / very much

# Chronic condition SNOMED codes
DIABETES_CODES  = {"44054006", "73211009"}
HTN_CODES       = {"38341003"}

# ---------------------------------------------------------------------------
# SDOH flag extraction
# ---------------------------------------------------------------------------


def _flag_from_observations(observations: List[Dict[str, Any]]) -> Dict[str, bool]:
    """Parse FHIR Observation resources for SDOH risk flags."""
    flags = {
        "housing_insecure":  False,
        "food_insecure":     False,
        "transport_barrier": False,
        "unemployed":        False,
        "high_stress":       False,
    }
    for obs in observations:
        # Get the LOINC code for this observation
        obs_codes: set[str] = set()
        for cc in (obs.get("code", {}).get("coding") or []):
            if cc.get("code"):
                obs_codes.add(cc["code"])

        # Get the answer code(s)
        answer_codes: set[str] = set()
        value_cc = obs.get("valueCodeableConcept", {})
        for cc in (value_cc.get("coding") or []):
            if cc.get("code"):
                answer_codes.add(cc["code"])

        # Match question code → check answer
        for obs_code in obs_codes:
            domain = SDOH_CODE_MAP.get(obs_code)
            if domain == "housing" and answer_codes & HOUSING_RISK_ANSWERS:
                flags["housing_insecure"] = True
            elif domain == "food" and answer_codes & FOOD_RISK_ANSWERS:
                flags["food_insecure"] = True
            elif domain == "transport" and answer_codes & TRANSPORT_RISK_ANSWERS:
                flags["transport_barrier"] = True
            elif domain == "employment" and answer_codes & EMPLOYMENT_RISK_ANSWERS:
                flags["unemployed"] = True
            elif domain == "stress" and answer_codes & STRESS_RISK_ANSWERS:
                flags["high_stress"] = True

    return flags


def _condition_flags(conditions: List[Dict[str, Any]]) -> Dict[str, bool]:
    flags = {"diabetes": False, "hypertension": False}
    for cond in conditions:
        for cc in (cond.get("code", {}).get("coding") or []):
            code_val = cc.get("code")
            if code_val in DIABETES_CODES:
                flags["diabetes"] = True
            if code_val in HTN_CODES:
                flags["hypertension"] = True
    return flags


def _encounter_counts(encounters: List[Dict[str, Any]]) -> Tuple[int, int, int]:
    """Returns (total_encounters, recent_encounters_6mo, recent_ed_visits_6mo)."""
    now = datetime.now(timezone.utc)
    six_months_ago = now - timedelta(days=180)
    recent = 0
    recent_ed = 0
    total = len(encounters)

    for enc in encounters:
        period = enc.get("period") or {}
        start = period.get("start")
        if start:
            try:
                start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
                if start_dt >= six_months_ago:
                    recent += 1
                    # Check if this is an ED encounter
                    enc_class = (enc.get("class") or {}).get("code", "").upper()
                    if enc_class in ("EMER", "EMERGENCY"):
                        recent_ed += 1
                    else:
                        # Check type for ED
                        for t in (enc.get("type") or []):
                            for coding in (t.get("coding") or []):
                                if coding.get("code") == "50849002":
                                    recent_ed += 1
                                    break
            except (ValueError, TypeError):
                continue
    return total, recent, recent_ed


# ---------------------------------------------------------------------------
# Demo mode: load from local fixture files
# ---------------------------------------------------------------------------

def _load_demo_patients(bundle_dir: Path) -> pd.DataFrame:
    """Read bundles from a specific directory and assemble a DataFrame."""
    settings = get_settings()

    if not bundle_dir.exists():
        log.warning("Demo data directory not found: %s", bundle_dir)
        return pd.DataFrame()

    rows = []
    files = sorted(bundle_dir.glob("patient_*.json"))
    for fpath in files[: settings.patient_limit]:
        with open(fpath, "r") as f:
            bundle = json.load(f)

        # Separate resources by type
        patient_res = None
        observations: List[Dict] = []
        conditions: List[Dict] = []
        encounters: List[Dict] = []

        for entry in bundle.get("entry", []):
            res = entry.get("resource", {})
            rt = res.get("resourceType")
            if rt == "Patient":
                patient_res = res
            elif rt == "Observation":
                observations.append(res)
            elif rt == "Condition":
                conditions.append(res)
            elif rt == "Encounter":
                encounters.append(res)

        if patient_res is None:
            continue

        row = _build_patient_row(patient_res, observations, conditions, encounters)
        if row:
            rows.append(row)

    df = pd.DataFrame(rows)
    if not df.empty:
        df.sort_values(by="score", ascending=False, inplace=True)
        df.reset_index(drop=True, inplace=True)
    return df


# ---------------------------------------------------------------------------
# Live mode: pull from FHIR server
# ---------------------------------------------------------------------------

def _group_by_patient(resources: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Helper to group a flat list of FHIR resources by their subject.reference Patient ID."""
    grouped = {}
    for res in resources:
        ref = (res.get("subject") or {}).get("reference", "")
        if ref.startswith("Patient/"):
            pid = ref.split("/", 1)[1]
            grouped.setdefault(pid, []).append(res)
    return grouped

def _load_live_patients(source_mode: str) -> pd.DataFrame:
    """Query a real FHIR server and assemble the DataFrame using Batch Fetching."""
    settings = get_settings()
    client = get_client(source_mode)
    
    # 1. Fetch patients
    patients = client.search_patients(settings.patient_limit)

    pids = [p.get("id") for p in patients if p.get("id")]
    if not pids:
        return pd.DataFrame()

    # Create a comma-separated list of IDs for batch querying (e.g. "1,2,3")
    patient_id_csv = ",".join(pids)

    # 2. Batch fetch ALL related data for ALL patients in just 3 sequential requests
    try:
        all_obs = client.fetch_sdoh_observations(patient_id_csv)
        all_conds = client.fetch_conditions(patient_id_csv)
        all_encs = client.fetch_encounters(patient_id_csv)
    except Exception as exc:
        log.error("Failed to batch fetch data: %s", exc)
        all_obs, all_conds, all_encs = [], [], []

    # 3. Group the flat responses back into dictionaries keyed by Patient ID
    obs_by_pid = _group_by_patient(all_obs)
    conds_by_pid = _group_by_patient(all_conds)
    encs_by_pid = _group_by_patient(all_encs)

    # 4. Assemble the final rows
    rows = []
    for pat in patients:
        pid = pat.get("id")
        if not pid: continue
        row = _build_patient_row(
            pat, 
            obs_by_pid.get(pid, []), 
            conds_by_pid.get(pid, []), 
            encs_by_pid.get(pid, [])
        )
        if row:
            rows.append(row)

    df = pd.DataFrame(rows)
    if not df.empty:
        df.sort_values(by="score", ascending=False, inplace=True)
        df.reset_index(drop=True, inplace=True)
    return df


# ---------------------------------------------------------------------------
# Shared row builder
# ---------------------------------------------------------------------------

def _build_patient_row(
    patient: Dict[str, Any],
    observations: List[Dict[str, Any]],
    conditions: List[Dict[str, Any]],
    encounters: List[Dict[str, Any]],
) -> Dict[str, Any] | None:
    pid = patient.get("id")
    if not pid:
        return None

    # Validate Patient resource against FHIR R4 schema (fhir.resources)
    if not _validate_patient(patient):
        log.warning("Skipping invalid Patient resource: %s", pid)
        return None

    sdoh_flags = _flag_from_observations(observations)
    cond_flags = _condition_flags(conditions)
    total_enc, recent_enc, recent_ed = _encounter_counts(encounters)

    age: int | None = None
    age_str, gender = "(unknown)", "(unknown)"
    birth_date = patient.get("birthDate")
    if birth_date:
        try:
            bdt = datetime.strptime(birth_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - bdt).days // 365
            age_str = str(age)
        except ValueError:
            pass

    score, details = scoring.score_patient_v2(
        sdoh_flags=sdoh_flags, 
        condition_flags=cond_flags, 
        recent_ed_visits=recent_ed, 
        age=age
    )

    gender = patient.get("gender", "(unknown)")

    city = ""
    state = ""
    if patient.get("address"):
        addr = patient["address"][0]
        city = addr.get("city", "")
        state = addr.get("state", "")

    return {
        "id": pid,
        "name": _patient_name(patient),
        "age": age_str,
        "gender": gender,
        "city": city,
        "state": state,
        "recent_encounters": recent_enc,
        "recent_ed_visits": recent_ed,
        "total_encounters": total_enc,
        **sdoh_flags,
        **cond_flags,
        "score": score,
        "details": details,
        "factors": [d.name for d in details],
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_patient_frame(source_mode: str = "Live FHIR Server (HAPI)") -> pd.DataFrame:
    """Load patient cohort from demo data or live FHIR server."""
    settings = get_settings()
    
    if source_mode == "Local Generation (Synthea)":
        log.info("Loading Synthea bundles from local disk")
        return _load_demo_patients(Path("demo_data/fhir_bundles"))
    elif source_mode == "Legacy Demo Data (Backup)":
        log.info("Loading Legacy demo bundles from local disk")
        return _load_demo_patients(Path("demo_data/fhir_bundles_backup"))
    else:
        # Default to Live FHIR Server or Private Azure FHIR Server
        log.info("Loading patients from live server for mode: %s", source_mode)
        return _load_live_patients(source_mode)


def _patient_name(pat: Dict[str, Any]) -> str:
    names = pat.get("name") or []
    if not names:
        return "(unknown)"
    first = names[0].get("given", [""])[0]
    last = names[0].get("family", "")
    return f"{first} {last}".strip()
