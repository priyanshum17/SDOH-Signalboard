from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List, Tuple

import pandas as pd

from config import get_settings
from domain import scoring
from services.fhir_client import get_client

# LOINC / code lists for SDOH signals (simplified placeholders)
HOUSING_CODES = {"71802-3", "LA30185-5", "88030-8"}
FOOD_CODES = {"88122-7", "88124-3"}
TRANSPORT_CODES = {"93025-5", "71802-3"}
EMPLOYMENT_CODES = {"67875-5"}

CHRONIC_DIABETES_CODES = {"44054006", "73211009"}
CHRONIC_HTN_CODES = {"38341003"}


def _flag_from_observations(observations: List[Dict]) -> Dict[str, bool]:
    flags = {
        "housing_insecure": False,
        "food_insecure": False,
        "transport_barrier": False,
        "unemployed": False,
    }
    for obs in observations:
        codes = set()
        code = obs.get("code", {})
        for cc in code.get("coding", []) or []:
            if cc.get("code"):
                codes.add(cc["code"])
        if codes & HOUSING_CODES:
            flags["housing_insecure"] = True
        if codes & FOOD_CODES:
            flags["food_insecure"] = True
        if codes & TRANSPORT_CODES:
            flags["transport_barrier"] = True
        if codes & EMPLOYMENT_CODES:
            flags["unemployed"] = True
    return flags


def _condition_flags(conditions: List[Dict]) -> Dict[str, bool]:
    flags = {"diabetes": False, "hypertension": False}
    for cond in conditions:
        code = cond.get("code", {})
        codings = code.get("coding", []) or []
        for cc in codings:
            code_val = cc.get("code")
            if code_val in CHRONIC_DIABETES_CODES:
                flags["diabetes"] = True
            if code_val in CHRONIC_HTN_CODES:
                flags["hypertension"] = True
    return flags


def _encounter_counts(encounters: List[Dict]) -> Tuple[int, int]:
    now = datetime.utcnow()
    six_months_ago = now - timedelta(days=180)
    recent = 0
    total = len(encounters)
    for enc in encounters:
        period = enc.get("period") or {}
        start = period.get("start")
        if start:
            try:
                start_dt = datetime.fromisoformat(start.rstrip("Z"))
                if start_dt >= six_months_ago:
                    recent += 1
            except ValueError:
                continue
    return total, recent


def load_patient_frame() -> pd.DataFrame:
    settings = get_settings()
    client = get_client()
    patients = client.search_patients(settings.patient_limit)

    rows = []
    for pat in patients:
        pid = pat.get("id")
        if not pid:
            continue
        observations = client.fetch_observations(pid)
        conditions = client.fetch_conditions(pid)
        encounters = client.fetch_encounters(pid)

        sdoh_flags = _flag_from_observations(observations)
        cond_flags = _condition_flags(conditions)
        total_enc, recent_enc = _encounter_counts(encounters)

        age = None
        birth_date = pat.get("birthDate")
        if birth_date:
            try:
                bdt = datetime.fromisoformat(birth_date)
                age = (datetime.utcnow().date() - bdt.date()).days // 365
            except ValueError:
                age = None

        score, factors = scoring.score_patient(
            sdoh_flags=sdoh_flags,
            condition_flags=cond_flags,
            recent_ed_visits=recent_enc,
            age=age,
        )

        rows.append(
            {
                "id": pid,
                "name": _patient_name(pat),
                "age": age,
                "recent_encounters": recent_enc,
                "total_encounters": total_enc,
                **sdoh_flags,
                **cond_flags,
                "score": score,
                "factors": factors,
            }
        )

    df = pd.DataFrame(rows)
    if not df.empty:
        df.sort_values(by="score", ascending=False, inplace=True)
    return df


def _patient_name(pat: Dict) -> str:
    names = pat.get("name") or []
    if not names:
        return "(unknown)"
    first = names[0].get("given", [""])[0]
    last = names[0].get("family", "")
    return f"{first} {last}".strip()
