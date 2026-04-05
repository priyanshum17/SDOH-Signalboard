# Care Manager Workflow & Use Cases

This document details the intended operational workflow of the SDOH Risk Stratification Dashboard and specifically outlines the duties assigned to its primary end-user: Population Health Care Managers (or Clinical Social Workers).

## The Core Concept: Actionable Intelligence
The dashboard does not exist simply to display medical charts; it exists to computationally analyze a patient's medical and social vulnerabilities, score them, and surface the most at-risk patients to the top of a daily queue. The system automatically handles the heavy lifting of finding the "needle in the haystack." 

The end-user's duty is to **act** on that intelligence.

---

## Daily Operational Duties

Imagine logging into this dashboard at 8:00 AM on a Monday morning to manage a clinic's population. Your workflow consists of the following four primary duties:

### Duty 1: Triage via the Priority Watchlist
The dashboard forces the highest-risk, most vulnerable patients to the very top of the grid.
*   **Action**: Ignore the "Low Risk" and "Medium Risk" patients initially. 
*   **Focus**: Immediately isolate patients flagged with a **HIGH** tier. These are individuals where the system has detected a dangerous intersection of chronic clinical illness and severe social instability.

### Duty 2: Investigate the "Why" (Root Cause Analysis)
A raw score is meaningless without context. Underneath each high-priority patient is an expandable profile view.
*   **Action**: Open the profile for the highest risk patient.
*   **Focus**: Review the transparent breakdown of their risk factors. The user must synthesize the clinical history alongside the Social Determinants of Health (SDOH) markers. 
*   *Example Finding*: The system highlights that the patient has recent Emergency Department utilization and poorly controlled Hypertension, but importantly, it also flags them as physically "Homeless" with a "Transportation Barrier" based on their recent PRAPARE survey.

### Duty 3: Coordinate Holistic Interventions
Knowing *why* a patient is high-risk changes the clinical approach. Treating hypertension medically will fail if the patient has no steady housing to store medication or no transport to pick it up. 
*   **Action**: Initiate targeted out-of-band protocols outside the dashboard based on the highlighted deficits.
*   **Intervention Examples**:
    *   **Housing**: Dispatch a referral to an internal social worker to begin emergency housing placement or shelter coordination.
    *   **Transportation**: Arrange Non-Emergency Medical Transportation (NEMT) or provide transit vouchers prior to their next scheduled cardiology clinic visit.
    *   **Food Insecurity**: Prescribe a "food pharmacy" box or enroll the patient in a community SNAP assistance outreach program.

### Duty 4: Proactive Outreach
The highest intent of this dashboard is preventing the *next* adverse event.
*   **Action**: Log the intervention and trigger proactive clinical outreach.
*   **Focus**: Call the patient proactively to check in on their medication adherence and social stability *before* their vulnerabilities put them back in the Emergency Room.

---

## Summary of the Interface's Role vs. The User's Role

| The System's Role (Automated) | The User's Role (Human) |
| :--- | :--- |
| Pull standard FHIR records (Conditions, Encounters). | Review the daily sorted Watchlist. |
| Parse PRAPARE SDOH Observations. | Expand and read transparent risk breakdowns. |
| Execute Risk Engine mathematical scoring. | Understand how a patient's social life impacts their clinical care. |
| Enforce a sorted, priority-tiered ranking system. | Launch targeted social work and proactive clinical interventions. |
