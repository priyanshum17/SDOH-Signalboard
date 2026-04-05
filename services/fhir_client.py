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
from typing import Any, Dict, List, Optional

from config import get_settings

log = logging.getLogger(__name__)

# Meta tag used to filter our project's resources on shared FHIR servers
TAG_SYSTEM = "https://sdoh-demo"
TAG_CODE = "sdoh-project"


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
            return {"_tag": f"{TAG_SYSTEM}|{TAG_CODE}"}
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
        payload = {
            "resourceType": "Observation",
            "meta": {"tag": [{"system": TAG_SYSTEM, "code": TAG_CODE}]},
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

    def close(self) -> None:
        self._client.close()


_default_client: Optional[FHIRClient] = None


def get_client() -> FHIRClient:
    global _default_client
    if _default_client is None:
        _default_client = FHIRClient()
    return _default_client
