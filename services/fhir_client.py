from __future__ import annotations

import httpx
from typing import Any, Dict, List, Optional

from config import get_settings


class FHIRClient:
    """Minimal FHIR client for read-only cohort pulls."""

    def __init__(self, base_url: Optional[str] = None, timeout: Optional[float] = None):
        settings = get_settings()
        self.base_url = base_url or settings.fhir_base_url.rstrip("/")
        self.timeout = timeout or settings.request_timeout
        self._client = httpx.Client(base_url=self.base_url, timeout=self.timeout)

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        resp = self._client.get(path, params=params)
        resp.raise_for_status()
        return resp.json()

    def search_patients(self, count: int = 20) -> List[Dict[str, Any]]:
        bundle = self._get("/Patient", params={"_count": count})
        return [e["resource"] for e in bundle.get("entry", []) if e.get("resource", {}).get("resourceType") == "Patient"]

    def fetch_observations(self, patient_id: str) -> List[Dict[str, Any]]:
        bundle = self._get("/Observation", params={"patient": patient_id, "_count": 200})
        return [e["resource"] for e in bundle.get("entry", []) if e.get("resource", {}).get("resourceType") == "Observation"]

    def fetch_conditions(self, patient_id: str) -> List[Dict[str, Any]]:
        bundle = self._get("/Condition", params={"patient": patient_id, "_count": 100})
        return [e["resource"] for e in bundle.get("entry", []) if e.get("resource", {}).get("resourceType") == "Condition"]

    def fetch_encounters(self, patient_id: str) -> List[Dict[str, Any]]:
        bundle = self._get("/Encounter", params={"patient": patient_id, "_count": 100})
        return [e["resource"] for e in bundle.get("entry", []) if e.get("resource", {}).get("resourceType") == "Encounter"]

    def close(self) -> None:
        self._client.close()


_default_client = FHIRClient()


def get_client() -> FHIRClient:
    return _default_client
