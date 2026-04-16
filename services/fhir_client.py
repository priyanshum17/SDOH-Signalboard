"""FHIR client layer using fhirclient (SMART on FHIR Python library).

Wraps the official SMART on FHIR Python client for server communication
and uses fhir.resources (Pydantic) for resource validation.

For open servers (like HAPI FHIR public test), no OAuth is needed.
For protected servers, the fhirclient supports SMART launch with:
  - authorize_url / callback flow
  - access token refresh
  - scope-based permissions

See: https://docs.smarthealthit.org/client-py/
"""

from __future__ import annotations

import datetime
import httpx
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from config import get_settings


log = logging.getLogger(__name__)


class FHIRError(Exception):
    """Base class for all FHIR client errors."""


class FHIRNotFoundError(FHIRError):
    """Raised on HTTP 404."""


class FHIRServerError(FHIRError):
    """Raised on HTTP 5xx."""

def _next_url(bundle: Dict[str, Any]) -> Optional[str]:
    for link in bundle.get("link") or []:
        if link.get("relation") == "next":
            return link.get("url")
    return None


class FHIRClient:
    """FHIR R4 client with SMART on FHIR awareness.

    Uses httpx for HTTP transport and supports:
    - Open servers (HAPI FHIR public) - no auth needed
    - Tag-based filtering to isolate project data on shared servers
    - Retry with exponential backoff
    - Pagination for large result sets

    For SMART on FHIR protected servers, this client would be extended
    with OAuth2 authorization via fhirclient.client.FHIRClient:

        from fhirclient import client
        smart = client.FHIRClient(settings={
            'app_id': 'sdoh-risk-dashboard',
            'api_base': 'https://launch.smarthealthit.org/v/r4/sim/...',
            'redirect_uri': 'http://localhost:8501/callback',
        })
        # smart.authorize_url -> redirect user for login
        # smart.handle_callback(url) -> exchange code for token
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        max_retries: int = 2,
        retry_backoff: float = 0.5,
        max_pages: int = 10,
        use_tag_filter: bool = True,
    ):
        settings = get_settings()
        self.base_url = (base_url or settings.fhir_base_url).rstrip("/")
        self.timeout = timeout or settings.request_timeout
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        self.max_pages = max_pages
        self.use_tag_filter = use_tag_filter
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=self.timeout,
            headers={"Accept": "application/fhir+json"},
        )

    def __enter__(self) -> "FHIRClient":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def check_connection(self) -> Dict[str, Any]:
        """Ping the FHIR server metadata endpoint.

        Returns server info dict on success, raises FHIRError on failure.
        """
        try:
            data = self._get("/metadata")
            return {
                "status": "connected",
                "server": self.base_url,
                "fhir_version": data.get("fhirVersion", "unknown"),
                "software": (data.get("software") or {}).get("name", "unknown"),
            }
        except Exception as exc:
            return {
                "status": "error",
                "server": self.base_url,
                "error": str(exc),
            }

    def _get(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        absolute_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        last_exc: Exception = RuntimeError("no attempts")
        for attempt in range(self.max_retries + 1):
            try:
                resp = (
                    self._client.get(absolute_url)
                    if absolute_url
                    else self._client.get(path, params=params)
                )
                if resp.status_code == 404:
                    raise FHIRNotFoundError(f"Not found: {absolute_url or path}")
                if resp.status_code >= 500:
                    raise FHIRServerError(f"Server error {resp.status_code}")
                resp.raise_for_status()
                return resp.json()
            except FHIRNotFoundError:
                raise
            except (FHIRServerError, httpx.TimeoutException, httpx.NetworkError) as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    time.sleep(self.retry_backoff * (2**attempt))
            except httpx.HTTPStatusError as exc:
                raise FHIRError(str(exc)) from exc
        raise FHIRError("Max retries exceeded") from last_exc

    def _get_all_entries(
        self, path: str, params: Dict[str, Any], resource_type: str
    ) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        next_url: Optional[str] = None
        for _ in range(self.max_pages):
            bundle = (
                self._get(path, absolute_url=next_url)
                if next_url
                else self._get(path, params=params)
            )
            results.extend(self._extract(bundle, resource_type))
            next_url = _next_url(bundle)
            if not next_url:
                break
        else:
            log.warning(
                "Pagination limit (%d pages) reached for %s",
                self.max_pages,
                path,
            )
        return results

    @staticmethod
    def _extract(
        bundle: Dict[str, Any], resource_type: str
    ) -> List[Dict[str, Any]]:
        out = []
        for entry in bundle.get("entry") or []:
            resource = entry.get("resource") or {}
            if resource.get("resourceType") == resource_type:
                out.append(resource)
        return out

    def _tag_param(self) -> Dict[str, str]:
        """Return tag filter param if enabled."""
        if self.use_tag_filter:
            s = get_settings()
            return {"_tag": f"{s.system_tag}|{s.code_tag}"}
        return {}

    def search_patients(self, count: int = 20) -> List[Dict[str, Any]]:
        params = {"_count": count, **self._tag_param()}
        return self._get_all_entries("/Patient", params, "Patient")

    def fetch_patient(self, patient_id: str) -> Dict[str, Any]:
        return self._get(f"/Patient/{patient_id}")

    def fetch_observations(self, patient_id: str) -> List[Dict[str, Any]]:
        return self._get_all_entries(
            "/Observation", {"patient": patient_id, "_count": 200}, "Observation"
        )

    def fetch_sdoh_observations(self, patient_id: str) -> List[Dict[str, Any]]:
        params = {
            "patient": patient_id,
            "category": "social-history",
            "_count": 200,
        }
        return self._get_all_entries("/Observation", params, "Observation")

    def fetch_conditions(self, patient_id: str) -> List[Dict[str, Any]]:
        return self._get_all_entries(
            "/Condition", {"patient": patient_id, "_count": 100}, "Condition"
        )

    def fetch_encounters(self, patient_id: str) -> List[Dict[str, Any]]:
        return self._get_all_entries(
            "/Encounter", {"patient": patient_id, "_count": 100}, "Encounter"
        )
      
    def fetch_care_plans(self, patient_id: str) -> List[Dict[str, Any]]:
        """Return CarePlan resources for a patient, tag-filtered if enabled.
 
        Ordered by last-updated descending if the server supports _sort.
        """
        params: Dict[str, Any] = {
            "patient": patient_id,
            "_count": 50,
            "_sort": "-_lastUpdated",
            **self._tag_param(),
        }
        return self._get_all_entries("/CarePlan", params, "CarePlan")
 
    def publish_sdoh_observation(self, patient_id: str, feature_key: str, positive_risk: bool) -> Dict[str, Any]:
        """Creates a brand new FHIR Observation detailing an SDOH risk status."""
        
        # Mappings: feature_key -> (LOINC Code, LOINC Display, Positive Answer Code, Negative Answer Code)
        mappings = {
            "housing_insecure": ("71802-3", "Housing status", "LA30186-3", "LA30190-5"),
            "food_insecure": ("88122-7", "Food insecurity", "LA33-6", "LA32-8"),
            "transport_barrier": ("93030-5", "Transportation barrier", "LA33-6", "LA32-8"),
            "unemployed": ("67875-5", "Employment status", "LA17958-2", "LA17956-6"),
        }
        
        if feature_key not in mappings:
            raise ValueError(f"Unknown SDOH feature key: {feature_key}")
            
        loinc, display, pos_ans, neg_ans = mappings[feature_key]
        answer_code = pos_ans if positive_risk else neg_ans
        
        # Build FHIR R4 Observation payload
        s = get_settings()
        payload = {
            "resourceType": "Observation",
            "meta": {"tag": [{"system": s.system_tag, "code": s.code_tag}]},
            "status": "final",
            "category": [{
                "coding": [{"system": "http://terminology.hl7.org/CodeSystem/observation-category", "code": "social-history", "display": "Social History"}]
            }],
            "code": {
                "coding": [{"system": "http://loinc.org", "code": loinc, "display": display}]
            },
            "subject": {"reference": f"Patient/{patient_id}"},
            "effectiveDateTime": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "valueCodeableConcept": {
                "coding": [{"system": "http://loinc.org", "code": answer_code}]
            }
        }
        
        # Post to server
        resp = self._client.post("/Observation", json=payload)
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise FHIRError(f"Failed to publish observation: {exc.response.text}") from exc
            
        return resp.json()

    # Implement optional documentation feature to write back CarePlan or ServiceRequest resources to the FHIR server

    def write_care_plan(
        self,
        patient_id: str,
        tier: Optional[str] = None,
        score: Optional[int] = None,
        factors: Optional[list] = None,
        *,
        resource: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """POST a CarePlan resource for a patient to the FHIR server.
 
        Two calling conventions:
          1. New:    write_care_plan(patient_id, resource=<dict>)
                     -- caller has already built the full FHIR CarePlan dict
                     (used by pages/3_care_plan.py).
          2. Legacy: write_care_plan(patient_id, tier, score, factors)
                     -- builds a minimal CarePlan from scoring factors
                     (used by the dashboard's HIGH-tier quick-action button).
        """
        if resource is None:
            # Legacy path — preserves original dashboard behavior.
            if tier is None or score is None:
                raise ValueError(
                    "write_care_plan requires either `resource=<dict>` or "
                    "(tier, score, factors)."
                )
            explanations = [f.name for f in (factors or [])]
            s = get_settings()
            resource = {
                "resourceType": "CarePlan",
                "meta": {"tag": [{"system": s.system_tag, "code": s.code_tag}]},
                "status": "active",
                "intent": "plan",
                "title": f"SDOH Risk Management Plan — {tier} ({score}/20)",
                "subject": {"reference": f"Patient/{patient_id}"},
                "created": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "identifier": [{
                    "system": f"{s.org_identifier_system}/careplan-ids",
                    "value": f"sdoh-cp-{patient_id}",
                }],
                "note": [{"text": "; ".join(explanations) if explanations else "No risk factors recorded."}],
                "activity": self._build_activities(explanations),
            }
        else:
            # New path — trust the caller's resource, but assert subject matches.
            subj = (resource.get("subject") or {}).get("reference", "")
            if subj and not subj.endswith(f"/{patient_id}"):
                raise ValueError(
                    f"CarePlan subject {subj!r} does not match patient_id {patient_id!r}"
                )
 
        resp = self._client.post("/CarePlan", json=resource)
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise FHIRError(f"Failed to publish CarePlan: {exc.response.text}") from exc
        return resp.json()

    def write_service_request(self, patient_id: str, tier: str, score: int, reason: str = "Social Work Referral") -> Dict[str, Any]:
        """POST a ServiceRequest referral resource for a patient."""
        s = get_settings()
        resource = {
            "resourceType": "ServiceRequest",
            "meta": {"tag": [{"system": s.system_tag, "code": s.code_tag}]},
            "status": "active",
            "intent": "order",
            "priority": "urgent" if tier == "HIGH" else "routine",
            "code": {
                "coding": [{"system": "http://snomed.info/sct", "code": "306206005", "display": "Referral to social work"}],
                "text": reason,
            },
            "subject": {"reference": f"Patient/{patient_id}"},
            "authoredOn": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "identifier": [{"system": f"{s.org_identifier_system}/sr-ids", "value": f"sdoh-sr-{patient_id}"}],
            "note": [{"text": f"SDOH score: {score}/20 ({tier}). Reason: {reason}"}],
        }
        resp = self._client.post("/ServiceRequest", json=resource)
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise FHIRError(f"Failed to publish ServiceRequest: {exc.response.text}") from exc
        return resp.json()

    @staticmethod
    def _build_activities(explanations: list) -> list:
        _MAP = {
            "housing":       ("Housing assistance referral",       "Connect patient with local housing authority."),
            "food":          ("Food security referral",            "Refer to food bank or SNAP enrollment."),
            "transport":     ("Transportation assistance",         "Arrange non-emergency medical transport."),
            "unemploy":      ("Employment services referral",      "Refer to workforce development center."),
            "stress":        ("Behavioral health referral",        "Connect with counseling or stress management."),
            "diabetes":      ("Diabetes self-management education","Enroll in DSMES program."),
            "hypertension":  ("Blood pressure monitoring",        "Schedule 30-day BP follow-up."),
            "ed utilization":("Care transitions follow-up",       "Schedule post-ED follow-up within 7 days."),
        }
        activities, seen = [], set()
        for exp in explanations:
            for keyword, (title, detail) in _MAP.items():
                if keyword in exp.lower() and title not in seen:
                    seen.add(title)
                    activities.append({"detail": {"status": "not-started", "code": {"text": title}, "description": detail}})
        if not activities:
            activities.append({"detail": {"status": "not-started", "code": {"text": "General social needs assessment"}, "description": "Care manager review required."}})
        return activities

    def close(self) -> None:
        self._client.close()


_default_client: Optional[FHIRClient] = None


def get_client() -> FHIRClient:
    global _default_client
    if _default_client is None:
        _default_client = FHIRClient()
    return _default_client
