import os
from dataclasses import dataclass
from typing import Optional


def _get_env(name: str, default: Optional[str] = None) -> str:
    return os.getenv(name, default) if os.getenv(name) not in (None, "") else (default or "") # type: ignore


def _get_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    fhir_base_url: str
    patient_limit: int
    request_timeout: float


_settings = Settings(
    fhir_base_url=_get_env("FHIR_BASE_URL", "https://hapi.fhir.org/baseR4"),
    patient_limit=_get_int("PATIENT_LIMIT", 25),
    request_timeout=_get_float("REQUEST_TIMEOUT", 8.0),
)


def get_settings() -> Settings:
    return _settings
