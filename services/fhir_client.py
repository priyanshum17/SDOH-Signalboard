from __future__ import annotations

import httpx
import logging
import time
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


def _is_ed_encounter(enc: Dict[str, Any]) -> bool:
    class_code = (enc.get("class") or {}).get("code", "").upper()
    if class_code in {"EMER", "EMERGENCY"}:
        return True
    for t in enc.get("type") or []:
        if "emergency" in (t.get("text") or "").lower():
            return True
        for coding in t.get("coding") or []:
            if coding.get("code") == "50849002":  # SNOMED: ED admission
                return True
    return False
    

class FHIRClient:
    """Minimal FHIR client for read-only cohort pulls."""
    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        max_retries: int = 2,
        retry_backoff: float = 0.5,
        max_pages: int = 10,
    ):
        settings = get_settings()
        self.base_url = (base_url or settings.fhir_base_url).rstrip("/")
        self.timeout = timeout or settings.request_timeout
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        self.max_pages = max_pages
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=self.timeout,
            headers={"Accept": "application/fhir+json"},
        )
        
    def __enter__(self) -> "FHIRClient":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

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
                    time.sleep(self.retry_backoff * (2 ** attempt))
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
            log.warning("Pagination limit (%d pages) reached for %s", self.max_pages, path)
        return results

   
    @staticmethod
    def _extract(bundle: Dict[str, Any], resource_type: str) -> List[Dict[str, Any]]:
        out = []
        for entry in bundle.get("entry") or []:
            resource = entry.get("resource") or {}
            if resource.get("resourceType") == resource_type:
                out.append(resource)
        return out

    def search_patients(self, count: int = 20) -> List[Dict[str, Any]]:
        return self._get_all_entries("/Patient", {"_count": count}, "Patient")

    def fetch_patient(self, patient_id: str) -> Dict[str, Any]:
        return self._get(f"/Patient/{patient_id}")

    
    def fetch_observations(self, patient_id: str) -> List[Dict[str, Any]]:
        return self._get_all_entries(
            "/Observation", {"patient": patient_id, "_count": 200}, "Observation"
        )

    def fetch_sdoh_observations(self, patient_id: str) -> List[Dict[str, Any]]:
        return self._get_all_entries(
            "/Observation",
            {"patient": patient_id, "category": "social-history", "_count": 200},
            "Observation",
        )
    
    def fetch_conditions(self, patient_id: str) -> List[Dict[str, Any]]:
            return self._get_all_entries(
                "/Condition", {"patient": patient_id, "_count": 100}, "Condition"
            )
    def fetch_encounters(self, patient_id: str) -> List[Dict[str, Any]]:
        return self._get_all_entries(
            "/Encounter", {"patient": patient_id, "_count": 100}, "Encounter"
        )

    def fetch_ed_encounters(self, patient_id: str) -> List[Dict[str, Any]]:
        try:
            candidates = self._get_all_entries(
                "/Encounter", {"patient": patient_id, "class": "EMER", "_count": 100}, "Encounter"
            )
        except FHIRError:
            log.warning("class=EMER filter failed for %s, falling back", patient_id)
            candidates = self.fetch_encounters(patient_id)
        return [e for e in candidates if _is_ed_encounter(e)]

    def close(self) -> None:
        self._client.close()



_default_client: Optional[FHIRClient] = None

def get_client() -> FHIRClient:
    global _default_client
    if _default_client is None:
        _default_client = FHIRClient()
    return _default_client
