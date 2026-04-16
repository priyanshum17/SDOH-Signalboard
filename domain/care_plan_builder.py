"""Pure builder for FHIR R4 CarePlan resources.

Separated from the FHIR client so the write-back UI can construct, preview,
and edit a CarePlan payload without touching the network. All functions are
pure (no I/O) and return plain dicts that conform to FHIR R4 CarePlan.

The suggestion engine maps risk factors (from domain.scoring.FactorDetail)
onto concrete CarePlan.activity entries drawn from a clinically grounded
catalog. Clinicians can then add, remove, or rewrite activities before
submission.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional


# Activity catalog — keyed by factor substring (case-insensitive)

@dataclass(frozen=True)
class ActivitySuggestion:
    """A single recommended activity, pre-populated from risk factors."""

    title: str
    description: str
    category: str          # "social" | "clinical" | "behavioral" | "utilization"
    status: str = "not-started"

    def to_fhir(self) -> Dict[str, Any]:
        return {
            "detail": {
                "status": self.status,
                "code": {"text": self.title},
                "description": self.description,
            }
        }


# Keyword -> suggestion. Keywords are matched against factor.name.lower().
# Order matters only for display; dedup happens by title.
_SUGGESTION_CATALOG: List[tuple[str, ActivitySuggestion]] = [
    ("housing", ActivitySuggestion(
        title="Housing assistance referral",
        description="Connect patient with local housing authority or shelter services; document outcome within 14 days.",
        category="social",
    )),
    ("food", ActivitySuggestion(
        title="Food security referral",
        description="Refer to food bank and initiate SNAP enrollment if eligible.",
        category="social",
    )),
    ("transport", ActivitySuggestion(
        title="Transportation assistance",
        description="Arrange non-emergency medical transport for scheduled appointments.",
        category="social",
    )),
    ("unemploy", ActivitySuggestion(
        title="Employment services referral",
        description="Refer to workforce development center; share job-training resources.",
        category="social",
    )),
    ("stress", ActivitySuggestion(
        title="Behavioral health referral",
        description="Warm handoff to counseling or stress management program.",
        category="behavioral",
    )),
    ("diabetes", ActivitySuggestion(
        title="Diabetes self-management education",
        description="Enroll patient in DSMES program; schedule A1C follow-up in 90 days.",
        category="clinical",
    )),
    ("hypertension", ActivitySuggestion(
        title="Blood pressure monitoring",
        description="Schedule 30-day BP follow-up; consider home BP cuff program.",
        category="clinical",
    )),
    ("ed utilization", ActivitySuggestion(
        title="Care transitions follow-up",
        description="Schedule post-ED follow-up within 7 days; reconcile medications.",
        category="utilization",
    )),
    ("age", ActivitySuggestion(
        title="Geriatric care review",
        description="Consider fall-risk assessment and medication review for older adult.",
        category="clinical",
    )),
]

# Fallback when no risk factors match
_DEFAULT_ACTIVITY = ActivitySuggestion(
    title="General social needs assessment",
    description="Care manager to complete comprehensive social needs screen within 14 days.",
    category="social",
)


def suggest_activities(factor_names: Iterable[str]) -> List[ActivitySuggestion]:
    """Map a list of factor names to a deduped list of suggested activities.

    Matches are substring-based (case-insensitive). If nothing matches, returns
    a single fallback activity so the CarePlan is never empty.
    """
    seen: set[str] = set()
    out: List[ActivitySuggestion] = []
    lowered = [f.lower() for f in factor_names]

    for keyword, suggestion in _SUGGESTION_CATALOG:
        if suggestion.title in seen:
            continue
        if any(keyword in name for name in lowered):
            out.append(suggestion)
            seen.add(suggestion.title)

    if not out:
        out.append(_DEFAULT_ACTIVITY)
    return out


# CarePlan input + resource builder

@dataclass
class CarePlanInput:
    """Form-level inputs collected from the UI."""

    patient_id: str
    patient_name: str
    tier: str                           # "HIGH" | "MEDIUM" | "LOW"
    score: int
    title: str
    status: str = "active"              # draft | active | on-hold | completed | revoked
    intent: str = "plan"                # proposal | plan | order | option
    period_start: Optional[datetime.date] = None
    period_end: Optional[datetime.date] = None
    clinical_note: str = ""
    activities: List[ActivitySuggestion] = field(default_factory=list)
    risk_factors: List[str] = field(default_factory=list)


def build_care_plan_resource(
    inp: CarePlanInput,
    *,
    system_tag: str,
    code_tag: str,
    identifier_system: str,
    now: Optional[datetime.datetime] = None,
) -> Dict[str, Any]:
    """Construct a FHIR R4 CarePlan resource dict from form input.

    Pure function: no network, no side effects. The returned dict is suitable
    to preview (st.json), POST to a FHIR server, or store to disk.
    """
    if now is None:
        now = datetime.datetime.now(datetime.timezone.utc)

    status = inp.status if inp.status in {
        "draft", "active", "on-hold", "completed", "revoked", "entered-in-error", "unknown"
    } else "active"
    intent = inp.intent if inp.intent in {
        "proposal", "plan", "order", "option", "directive"
    } else "plan"

    resource: Dict[str, Any] = {
        "resourceType": "CarePlan",
        "meta": {"tag": [{"system": system_tag, "code": code_tag}]},
        "status": status,
        "intent": intent,
        "title": inp.title,
        "subject": {
            "reference": f"Patient/{inp.patient_id}",
            "display": inp.patient_name,
        },
        "created": now.isoformat(),
        "identifier": [{
            "system": f"{identifier_system}/careplan-ids",
            "value": f"sdoh-cp-{inp.patient_id}-{int(now.timestamp())}",
        }],
    }

    # Period (optional)
    period: Dict[str, str] = {}
    if inp.period_start:
        period["start"] = inp.period_start.isoformat()
    if inp.period_end:
        period["end"] = inp.period_end.isoformat()
    if period:
        resource["period"] = period

    # Description — human-readable risk context
    if inp.risk_factors:
        resource["description"] = (
            f"Social Risk Score {inp.score}/20 ({inp.tier}). "
            f"Contributing factors: {', '.join(inp.risk_factors)}."
        )
    else:
        resource["description"] = (
            f"Social Risk Score {inp.score}/20 ({inp.tier}). No specific factors recorded."
        )

    # Clinician note
    if inp.clinical_note.strip():
        resource["note"] = [{
            "text": inp.clinical_note.strip(),
            "time": now.isoformat(),
        }]

    # Category — always tag as assess-plan for SDOH context
    resource["category"] = [{
        "coding": [{
            "system": "http://hl7.org/fhir/us/core/CodeSystem/careplan-category",
            "code": "assess-plan",
            "display": "Assessment and Plan of Treatment",
        }],
        "text": "SDOH risk management plan",
    }]

    # Activities
    resource["activity"] = [a.to_fhir() for a in inp.activities] or [
        _DEFAULT_ACTIVITY.to_fhir()
    ]

    return resource
