# Project Plan (SDOH Risk Stratification)

## Part 1: Topic & Background
- **Goal**: SMART on FHIR population-health app that surfaces a prioritized outreach list using SDOH and clinical data.
- **Motivation**: SDOH data is captured (e.g., PRAPARE) but underused; manual chart review is slow and inconsistent. Automated scoring + explanations supports proactive outreach.

## Part 2: Technical Design
- **Frontend/UI**: Streamlit (Python).
- **FHIR Integration**: Read-only SMART-ish client using `httpx` + `fhir.resources`; resources used: Patient, Observation (PRAPARE/SDOH), Condition, Encounter. Optional write-back: CarePlan / ServiceRequest.
- **App Logic**: Pure Streamlit app (no FastAPI needed initially) with modular services and domain layers.
- **Database**: Not required for read-only demo; SQLite reserved for future caching/persistence.
- **Deployment**: Streamlit Cloud or similar.
- **CI/CD**: GitHub Actions (future).

### Data Sources
- Primary: Public HAPI FHIR test server (synthetic records).

## Part 3: Implementation Plan (mapped to code)
- **Data retrieval layer**: `services/fhir_client.py`, `services/patient_repository.py` (complete for read-only pull).
- **Scoring**: Rule-based engine in `domain/scoring.py` (complete, tunable).
- **Dashboard**: `app.py` (complete: filters, factors, per-patient details).
- **Documentation**: README, this plan file, `.env.example` (complete); add future sections for deployment and CI.
- **Testing**: Pytest unit tests for scoring in `tests/` (complete); integration tests planned (see TODOs).

## Outstanding Work / TODOs
- Add PRAPARE/SDOH code mappings with authoritative LOINC/SDC lists (currently placeholders).
- Add encounter classification (ED vs primary care) to refine utilization scoring.
- Implement optional CarePlan/ServiceRequest write-back gated by feature flag and server permissions.
- Create Streamlit Cloud deployment workflow (non-Docker) and GitHub Actions CI for tests/lint.
- Build integration test with recorded HAPI responses (e.g., VCR) to avoid network flakiness.
- Create UI mock screenshots and architecture diagram for project report.
- Add accessibility and usability review with test users; capture feedback loop in docs.

## Acceptance Criteria Trace
- Pulls Patient, Observation, Condition, Encounter from FHIR ✔
- Computes composite social risk score with SDOH + clinical + utilization ✔
- Displays prioritized patient list with explanations ✔
- Supports configuration of FHIR endpoint and limits via env ✔
- Optional write-back hooks defined (to be implemented) ◻
