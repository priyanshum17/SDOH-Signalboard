import os
from dataclasses import dataclass, field
from typing import Optional


def _get_env(name: str, default: Optional[str] = None) -> str:
    return os.getenv(name, default) if os.getenv(name) not in (None, "") else (default or "")  # type: ignore


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


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
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


_settings = Settings(
    fhir_base_url=_get_env("FHIR_BASE_URL", "https://hapi.fhir.org/baseR4"),
    patient_limit=_get_int("PATIENT_LIMIT", 30),
    request_timeout=_get_float("REQUEST_TIMEOUT", 15.0),
    use_demo_data=_get_bool("USE_DEMO_DATA", False),
    demo_data_dir=_get_env("DEMO_DATA_DIR", os.path.join(os.path.dirname(__file__), "demo_data", "fhir_bundles")),
)


def get_settings() -> Settings:
    return _settings
