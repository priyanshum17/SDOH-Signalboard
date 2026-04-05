# Project Architecture & Technical Specifications

This document outlines the system architecture, data flow, and underlying mechanisms of the SDOH Risk Stratification Dashboard.

## High-Level Architecture

The system operates across three primary stages: **Simulated Data Generation**, **FHIR REST Integration**, and **Risk Orchestration & Visualization**.

## Component Breakdown

### 1. Data Generation Pipeline (Synthea + Python)
Since HIPAA restricts real medical records, the project uses **Synthea**, an open-source health IT simulator. Synthea naturally produces detailed synthetic histories comprising `Condition`, `Encounter`, `Medication`, and `Patient` resources.

Because Synthea does *not* natively understand social screening tools, the project intercepts this data:
*   **`enrich_synthea.py`**: Interrogates the Synthea transaction bundle, locates the Patient node, and synthetically layers in **Observation** resources mapped to the exact LOINC codes used by the PRAPARE Social Determinants of Health questionnaire (e.g., *71802-3* for Housing, *88122-7* for Food Security). It also assigns a specific meta tag (`meta.tag = sdoh-project`) to every resource.
*   **`upload_data.py`**: Overcomes strict public FHIR server limitations (like transaction size bounds) by unwrapping the bundles, preserving only necessary component references, and firing singular robust `POST` statements synchronously to the cloud.

### 2. The FHIR Client Abstraction (`fhir_client.py`)
This micro-service handles external networking. It is designed around the SMART on FHIR architecture paradigm:
*   It currently uses `httpx` and supports tag-based server-side filtering so that a public server (like HAPI, which contains data from thousands of users globally) only returns our project's data. 
*   It implements robust paging and exponential back-off logic to ensure server reliability won't crash the frontend dashboard.
*   It is structured to gracefully accept future upgrades to Full SMART OAuth tokenized flows via the `fhirclient` python package.

### 3. Pydantic Validation & The Repository (`patient_repository.py`)
Upon fetching data, it isn't blindly passed to the frontend. The `fhir.resources` package acts as a rigorous type-checker. Every raw dictionary fetched from the internet is parsed into its corresponding FHIR R4 Pydantic structure.
*   If a `Patient` object has mismatched types or missing mandatory fields, the validation boundary traps it.
*   The repository then maps complex nested FHIR arrays into a flattened, easily digestible structure suitable for a Pandas DataFrame.

### 4. The Domain Logic: Risk Engine (`scoring.py`)
The engine accepts the flattened patient dict mapping and calculates the final risk tier logic. The engine operates dynamically, reacting strongly to **medical-social interaction**:
- **Medical Rules**: Accumulate base points for Chronic issues (e.g., Diabetes) and Recent Utilization.
- **Social Rules**: Triggers point influxes if Housing or Food insecurity observations exist in the patient's FHIR record.
- **Amplification Mechanism**: Patients suffering from *both* chronic illnesses and fundamental social insecurities receive a multiplicative scoring bump, recognizing that their readmission probability is statistically exponential rather than linear.

### 5. Frontend UI / Dashboard (`app.py`)
Built purely with Streamlit components, styled via `config.toml`, to emulate strict enterprise constraints.
*   Fetches the validated pandas dataframe at load.
*   Enacts automatic column configurations mapping risk integers directly to color-coded flags using optimized Streamlit `data_editor` columns.
*   Presents interactive expanders yielding transparent calculation breakdowns so clinical users can instantly trust the ML/Scoring output.
