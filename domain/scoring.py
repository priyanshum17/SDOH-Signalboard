"""Social Risk Score engine.

Blends SDOH screening flags, chronic conditions, utilization signals, and
age into a single composite score with per-factor explanations.

Two public entry points:
  * ``score_patient_v2`` – returns ``(int, List[FactorDetail])``  (preferred)
  * ``score_patient``    – thin wrapper returning ``(int, List[str])`` for
                           backward compatibility with the dashboard and tests
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class FactorDetail:
    """One contributing factor to a patient's Social Risk Score."""

    name: str
    points: int
    severity: str        # "high" | "medium" | "low"
    explanation: str

    @property
    def as_label(self) -> str:
        return self.name


# ----- weights ---------------------------------------------------------------

_SDOH_WEIGHTS = {
    "housing_insecure":  (3, "high",   "Housing instability",             "Patient reports lacking steady housing"),
    "food_insecure":     (3, "high",   "Food insecurity",                 "Patient worried about food running out in the past 12 months"),
    "transport_barrier": (2, "medium", "Transportation barrier",          "Lack of transportation has kept patient from appointments"),
    "unemployed":        (2, "medium", "Unemployment/underemployment",    "Patient is unemployed or seeking work"),
    "high_stress":       (1, "medium", "High stress",                     "Patient reports quite a bit / very much stress"),
}

_CONDITION_WEIGHTS = {
    "diabetes":     (2, "medium", "Diabetes",     "Active diabetes diagnosis"),
    "hypertension": (2, "medium", "Hypertension", "Active hypertension diagnosis"),
}

# Tiered ED-visit scoring
_ED_TIERS: List[Tuple[int, int, str]] = [
    # (min_visits, points, label)
    (3, 3, "Very high recent ED utilization (≥3 visits)"),
    (2, 2, "High recent ED utilization (2 visits)"),
    (1, 1, "Recent ED utilization (1 visit)"),
]

# Tiered age scoring
_AGE_TIERS: List[Tuple[int, int, str]] = [
    (75, 2, "Age ≥ 75"),
    (65, 1, "Age ≥ 65"),
]


# maximum possible raw score  (3+3+2+2+1) + (2+2) + 3 + 2 = 20
MAX_RAW_SCORE: int = 20


# ----- public API ------------------------------------------------------------

def score_patient_v2(
    sdoh_flags: Dict[str, bool],
    condition_flags: Dict[str, bool],
    recent_ed_visits: int,
    age: Optional[int],
) -> Tuple[int, List[FactorDetail]]:
    """Compute Social Risk Score.  Returns ``(total_score, [FactorDetail, ...])``.

    This is the preferred interface — use ``score_patient`` if you only need
    ``(int, List[str])`` backward-compat output.
    """
    total = 0
    details: List[FactorDetail] = []

    # SDOH flags
    for flag_key, (pts, sev, name, expl) in _SDOH_WEIGHTS.items():
        if sdoh_flags.get(flag_key):
            total += pts
            details.append(FactorDetail(name=name, points=pts, severity=sev, explanation=expl))

    # Chronic conditions
    for flag_key, (pts, sev, name, expl) in _CONDITION_WEIGHTS.items():
        if condition_flags.get(flag_key):
            total += pts
            details.append(FactorDetail(name=name, points=pts, severity=sev, explanation=expl))

    # ED utilization (tiered)
    for min_visits, pts, label in _ED_TIERS:
        if recent_ed_visits >= min_visits:
            total += pts
            details.append(FactorDetail(name=label, points=pts, severity="high" if pts >= 3 else "medium",
                                        explanation=f"{recent_ed_visits} ED visit(s) in last 6 months"))
            break  # use the first (highest) matching tier

    # Age (tiered)
    if age is not None:
        for threshold, pts, label in _AGE_TIERS:
            if age >= threshold:
                total += pts
                details.append(FactorDetail(name=label, points=pts, severity="low",
                                            explanation=f"Patient is {age} years old"))
                break

    return total, details


def score_patient(
    sdoh_flags: Dict[str, bool],
    condition_flags: Dict[str, bool],
    recent_ed_visits: int,
    age: Optional[int],
) -> Tuple[int, List[str]]:
    """Legacy wrapper — returns ``(total_score, [factor_name, ...])``."""
    total, details = score_patient_v2(sdoh_flags, condition_flags, recent_ed_visits, age)
    return total, [d.name for d in details]
