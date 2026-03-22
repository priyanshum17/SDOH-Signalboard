A SMART-on-FHIR–style population health demo that pulls synthetic patients from a FHIR server, computes a transparent Social Risk Score using SDOH + clinical + utilization signals, and delivers a prioritized outreach list with explanations.

## What the app does
- **Connects to FHIR**: Reads `Patient`, `Observation` (SDOH/PRAPARE-like), `Condition`, and `Encounter` resources from a public HAPI FHIR endpoint (configurable).
- **Computes a composite score**: Rule-based points for housing/food/transport barriers, unemployment, diabetes/HTN, recent ED use, and age ≥ 65. Explanations are shown per patient.
- **Prioritizes for outreach**: Sortable table with filters (minimum score, condition toggles, housing flag) plus detail expanders listing the factors and utilization counts.
- **Configurable**: Environment variables for FHIR base URL, patient cohort size, and HTTP timeout. No authentication required for the default public endpoint.
- **Extensible**: Hooks exist for write-back (CarePlan/ServiceRequest) and weight tuning; TODOs are tracked in `docs/TODO.md`.

## Repository layout
- `app.py` — Streamlit UI and user-facing interactions.
- `services/` — FHIR client (`fhir_client.py`) and cohort assembly (`patient_repository.py`).
- `domain/` — Scoring logic (`scoring.py`).
- `docs/` — Project plan and backlog.
- `tests/` — Pytest suite for scoring.

## Running locally
1. Install uv if not present: `pip install uv`.
2. Copy env defaults (optional): `cp .env.example .env` and edit `FHIR_BASE_URL`, `PATIENT_LIMIT`, `REQUEST_TIMEOUT` as needed.
3. Install deps: `uv sync`.
4. Launch Streamlit: `uv run streamlit run app.py`.

## Tests
- Unit tests: `uv run pytest`.
- (Planned) Integration tests with recorded FHIR responses — see `docs/TODO.md`.

## Current limitations
- SDOH code lists use placeholder subsets; replace with authoritative PRAPARE/LOINC codes for production use.
- Encounter parsing counts all visits; ED vs. other visit classification is a TODO.
- Read-only by default; write-back of CarePlan/ServiceRequest is not yet implemented.
