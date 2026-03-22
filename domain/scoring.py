from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

@dataclass(frozen=True)
class FactorDetail:
    name: str
    points: int
    severity: str
    explanation: str

    @property
    def as_label(self) -> str:
        return self.name


MAX_RAW_SCORE: int = 19  # sum of all max per-factor points

def score_patient(
    sdoh_flags: Dict[str, bool],
    condition_flags: Dict[str, bool],
    recent_ed_visits: int,
    age: Optional[int],
) -> Tuple[int, List[str]]:
    score = 0
    factors: List[str] = []

    if sdoh_flags.get("housing_insecure"):
        score += 3
        factors.append("Housing instability")
    if sdoh_flags.get("food_insecure"):
        score += 3
        factors.append("Food insecurity")
    if sdoh_flags.get("transport_barrier"):
        score += 2
        factors.append("Transportation barrier")
    if sdoh_flags.get("unemployed"):
        score += 2
        factors.append("Unemployment/underemployment")

    if condition_flags.get("diabetes"):
        score += 2
        factors.append("Diabetes")
    if condition_flags.get("hypertension"):
        score += 2
        factors.append("Hypertension")
    
    if recent_ed_visits >= 2:
            score += 2
            factors.append("High recent ED utilization")
    if age is not None and age >= 65:
        score += 1
        factors.append("Age ≥ 65")

    return score, factors
