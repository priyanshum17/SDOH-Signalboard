import os
from dataclasses import dataclass, field
from typing import Optional


import streamlit as st

def _get_raw(name: str) -> Optional[str]:
    try:
        if name in st.secrets:
            val = st.secrets[name]
            return str(val) if val is not None else None
    except Exception:
        pass
    return os.getenv(name)

def _get_env(name: str, default: Optional[str] = None) -> str:
    raw = _get_raw(name)
    return raw if raw not in (None, "") else (default or "")  # type: ignore


def _get_float(name: str, default: float) -> float:
    raw = _get_raw(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _get_int(name: str, default: int) -> int:
    raw = _get_raw(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _get_bool(name: str, default: bool) -> bool:
    raw = _get_raw(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes")


@dataclass(frozen=True)
class Settings:
    fhir_base_url: str
    patient_limit: int
    request_timeout: float
    use_demo_data: bool
    demo_data_dir: str
    system_tag: str
    code_tag: str
    org_identifier_system: str
    azure_tenant_id: str
    azure_client_id: str
    azure_client_secret: str


_settings = Settings(
    fhir_base_url=_get_env("FHIR_BASE_URL", "https://hapi.fhir.org/baseR4"),
    patient_limit=_get_int("PATIENT_LIMIT", 30),
    request_timeout=_get_float("REQUEST_TIMEOUT", 15.0),
    use_demo_data=_get_bool("USE_DEMO_DATA", False),
    demo_data_dir=_get_env("DEMO_DATA_DIR", os.path.join(os.path.dirname(__file__), "demo_data", "fhir_bundles")),
    system_tag=_get_env("SYSTEM_TAG", "https://sdoh-demo"),
    code_tag=_get_env("CODE_TAG", "sdoh-project"),
    org_identifier_system=_get_env("ORG_IDENTIFIER_SYSTEM", "https://sdoh-demo"),
    azure_tenant_id=_get_env("AZURE_TENANT_ID", ""),
    azure_client_id=_get_env("AZURE_CLIENT_ID", ""),
    azure_client_secret=_get_env("AZURE_CLIENT_SECRET", ""),
)


def get_settings() -> Settings:
    return _settings
