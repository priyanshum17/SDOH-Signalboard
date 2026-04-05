# SDOH Risk Stratification Dashboard

A comprehensive SMART on FHIR population health application that detects Social Determinants of Health (SDOH) risks and bridges the gap between clinical data and social risk factors. 

## 1. The Core Problem It Solves
Typically, SDOH data (lack of housing, food insecurity, lack of transportation, high stress, unemployment) is buried within Electronic Health Record (EHR) screening forms. Even if it is collected, it is rarely surfaced alongside clinical metrics (like recent emergency department visits or chronic conditions) to provide a holistic view of a patient's true vulnerability. 

This tool extracts both clinical and social data types in real-time, scores the patient's combined risk, and presents it in an actionable, centralized dashboard for care managers and providers.

## 2. How the Risk Engine Works
The project evaluates patients and assigns them a **Risk Score (0-100)** which maps to Priority Tiers (HIGH, MEDIUM, LOW). The scoring engine heavily weights scenarios where social needs compound medical vulnerabilities:
*   **Base Clinical Risk (0-40 points)**: Checks for the presence of chronic conditions (like Diabetes or Hypertension) and evaluates utilization history (e.g., penalizing recent Emergency Department visits).
*   **SDOH Risk (0-40 points)**: Scans FHIR `Observation` resources specifically for PRAPARE LOINC codes. Positive responses for lack of steady housing, food insecurity, unemployment, or high stress immediately spike the score.
*   **Interaction Multiplier (up to 20 bonus points)**: The system mathematically recognizes that having a severe condition *while simultaneously* being homeless or lacking transportation creates an exponentially higher risk of readmission or health decline. 

## 3. The Technical Architecture (SMART on FHIR)
The project is built to adhere strictly to healthcare interoperability standards so it can theoretically be deployed "on top" of systems like Epic, Cerner, or Athenahealth:
*   **FHIR Standard**: It strictly queries standard FHIR R4 resources (`Patient`, `Condition`, `Encounter`, `Observation`).
*   **Validation**: It utilizes Pydantic (`fhir.resources`) to strictly validate that incoming JSON payloads from the server perfectly match the HL7 FHIR specifications.
*   **Data Sourcing**: While it supports a local demo mode, it acts natively as a live FHIR client interacting with public servers (e.g., HAPI FHIR R4 server).
*   **Synthetic Integration**: The tool bypasses HIPAA limitations by using **Synthea** to generate hyper-realistic medical histories, which are then synthetically enriched with simulated PRAPARE social screening outcomes to construct robust testing cohorts.

## 4. The User Interface
The frontend is built using **Streamlit**, functioning as an enterprise-grade clinical workstation:
*   **Dark Mode & Professional Aesthetic**: A strict, emoji-free aesthetic guarantees focus remains entirely on population health data.
*   **High-Level Analytics**: The top of the dashboard provides population-level metrics (e.g., Total Patients vs. Percentage in the "High Risk" tier).
*   **Deep Dive Capabilities**: Care managers can sort their highest-risk patients, open expander views, and review the explicit breakdown of why a patient scored highly.


---

## Quick Start

```bash
uv sync             
uv run streamlit run app.py
```

To run exclusively with offline demo data instead of a live network fetch:
```bash
USE_DEMO_DATA=true uv run streamlit run app.py
```

## Repository Layout

```
app.py                          Streamlit clinical dashboard (entry point)
config.py                       Settings and environment variables
domain/
  scoring.py                    SDOH Risk Score mathematical engine 
services/
  fhir_client.py                SMART on FHIR R4 client (fhirclient)
  patient_repository.py         Pydantic validation, pipeline, and DataFrames
demo_data/
  enrich_synthea.py             Injects PRAPARE SDOH data into Synthea outputs
scripts/
  upload_data.py                Live individual REST resource upload to HAPI FHIR
tests/                          Pytest suite ensuring reliability
docs/                           Architecture diagrams and comprehensive specs
synthea/                        Synthea local instance for FHIR bundle execution
```

## Running the Data Pipeline (Synthea to HAPI FHIR)

If you want to generate your own data and push to the live server:
1. `java -jar synthea/synthea-with-dependencies.jar -p 30` (Generates base clinical patients)
2. `uv run python demo_data/enrich_synthea.py` (Injects SDOH / PRAPARE variables)
3. `uv run python scripts/upload_data.py` (Deconstructs payload and streams directly to HAPI FHIR)

## Tests

```bash
uv run pytest -v
```
## Viewing Written FHIR Resources (CarePlan and ServiceRequest)
To use the **Write-Back** feature on a HIGH-risk patient, you must be in Live FHIR Server (HAPI) mode, open a HIGH-risk patient's expander, then navigate to **Patient Details**. Scroll to the bottom for the specified patient and you will see **Documentation Write-Back (optional — writes to FHIR server)**. This presents two options, ***Create CarePlan*** and ***Create ServiceRequest***. 



After using the **Write-Back** feature on a HIGH-risk patient, you can verify the resources were successfully created on the HAPI FHIR server. The easiest way to view them is in HAPI's built-in HTML viewer:


**All CarePlans created by this project:**
https://hapi.fhir.org/baseR4/CarePlan?_tag=https://sdoh-demo|sdoh-project&_format=html

**All ServiceRequests created by this project:**
https://hapi.fhir.org/baseR4/ServiceRequest?_tag=https://sdoh-demo|sdoh-project&_format=html


Replace `PATIENT_ID` with the ID shown in the green success message after clicking **Create CarePlan** in the dashboard.

All resources written by this app are tagged with `https://sdoh-demo|sdoh-project`, isolating them from other resources on the shared public server. Each CarePlan includes a patient reference, risk score, auto-generated activities mapped from the patient's SDOH risk factors, and a note summarizing all contributing factors.

> **Note:** Write-back is only available when using **Live FHIR Server (HAPI)** as the data source. The HAPI public server does not enforce identifier uniqueness, so clicking the button multiple times will create duplicate resources — expected behavior on a shared test server.



If you want to clean up duplicates or test resources you've already written, you can delete them by ID:
DELETE https://hapi.fhir.org/baseR4/CarePlan/131683938
DELETE https://hapi.fhir.org/baseR4/CarePlan/131683939
