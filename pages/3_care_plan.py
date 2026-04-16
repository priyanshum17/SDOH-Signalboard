"""Care Plan Documentation (FHIR Write-Back).

A dedicated workspace for clinicians to author, preview, and submit FHIR R4
CarePlan resources for high-risk patients. Auto-suggests activities based on
the patient's Social Risk Score factors; all suggestions are editable, and a
dry-run toggle renders the payload without posting.
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List

import pandas as pd
import streamlit as st

from config import get_settings
from domain.care_plan_builder import (
    ActivitySuggestion,
    CarePlanInput,
    build_care_plan_resource,
    suggest_activities,
)
from domain.scoring import score_to_tier
from services.fhir_client import FHIRError, get_client
from services.patient_repository import load_patient_frame


settings = get_settings()


# Header

st.title("Care Plan Documentation")
st.caption(
    "Author FHIR R4 CarePlan resources for patients surfaced by the Social Risk Score. "
    "Suggestions are pre-filled from risk factors and fully editable before submission."
)

st.warning(
    "Write-back creates permanent records on the active FHIR server. "
    "Use **Dry-run** to preview the payload without posting."
)


# Sidebar — data source + mode

with st.sidebar:
    st.header("Settings")
    data_source = st.radio(
        "Data Source",
        options=[
            "Live FHIR Server (HAPI)",
            "Local Generation (Synthea)",
            "Legacy Demo Data (Backup)",
        ],
        index=0,
        help="Only Live FHIR supports actual POST. Other modes force dry-run.",
    )

    st.header("Write-Back Mode")
    dry_run = st.toggle(
        "Dry-run (preview JSON only, do not POST)",
        value=(data_source != "Live FHIR Server (HAPI)"),
        disabled=(data_source != "Live FHIR Server (HAPI)"),
        help="Forced ON for non-live data sources because local patient IDs don't exist on the server.",
    )


# Load cohort

@st.cache_data(show_spinner="Loading patients…")
def _load(source: str) -> pd.DataFrame:
    return load_patient_frame(source_mode=source)


try:
    df = _load(data_source)
except Exception as exc:
    st.error(f"Failed to load data: {exc}")
    st.stop()

if df.empty:
    st.info("No patients returned.")
    st.stop()


# Patient picker

st.subheader("1. Select Patient")

col_filter, col_picker = st.columns([1, 2])

with col_filter:
    tier_filter = st.selectbox(
        "Tier filter",
        ["All", "HIGH (≥12)", "MEDIUM (7–11)", "LOW (0–6)"],
        index=1,
        help="High-risk patients are the most common candidates for a CarePlan.",
    )

if tier_filter.startswith("HIGH"):
    view = df[df["score"] >= 12]
elif tier_filter.startswith("MEDIUM"):
    view = df[(df["score"] >= 7) & (df["score"] <= 11)]
elif tier_filter.startswith("LOW"):
    view = df[df["score"] <= 6]
else:
    view = df

view = view.sort_values("score", ascending=False)

if view.empty:
    st.info("No patients in the selected tier. Adjust the filter.")
    st.stop()

with col_picker:
    labels = {
        row["id"]: f"{row['name']}  —  Score {row['score']}/20  [{score_to_tier(row['score']).value}]"
        for _, row in view.iterrows()
    }
    patient_id = st.selectbox(
        "Patient",
        options=list(labels.keys()),
        format_func=lambda pid: labels[pid],
    )

patient_row = view[view["id"] == patient_id].iloc[0]
tier_value = score_to_tier(patient_row["score"]).value
factor_details = patient_row.get("details") or []
factor_names = [d.name for d in factor_details]


# Patient context (read-only summary)


st.subheader("2. Patient Context")

ctx_a, ctx_b, ctx_c = st.columns(3)
with ctx_a:
    st.markdown("**Demographics**")
    st.write(f"Name: {patient_row['name']}")
    st.write(f"Age: {patient_row.get('age', 'N/A')}")
    st.write(f"Gender: {str(patient_row.get('gender', 'N/A')).capitalize()}")
    city = patient_row.get("city", "")
    state = patient_row.get("state", "")
    st.write(f"Location: {city}, {state}" if city else "Location: N/A")

with ctx_b:
    st.markdown("**Risk Snapshot**")
    st.write(f"Score: **{patient_row['score']}/20**")
    st.write(f"Tier: **{tier_value}**")
    st.write(f"ED visits (6 mo): {int(patient_row['recent_ed_visits'])}")
    st.write(f"Encounters (6 mo): {int(patient_row['recent_encounters'])}")

with ctx_c:
    st.markdown("**Contributing Factors**")
    if factor_names:
        for name in factor_names:
            st.write(f"• {name}")
    else:
        st.write("_No specific factors recorded._")


# CarePlan form

st.subheader("3. Author CarePlan")

# Seed session state per patient so selecting a new patient refreshes suggestions
state_key = f"cp_activities_{patient_id}"
if state_key not in st.session_state:
    st.session_state[state_key] = suggest_activities(factor_names)

form_a, form_b = st.columns(2)
with form_a:
    title = st.text_input(
        "Title",
        value=f"SDOH Risk Management Plan — {tier_value} ({patient_row['score']}/20)",
        help="Human-readable title for the CarePlan.",
    )
    status = st.selectbox(
        "Status",
        ["active", "draft", "on-hold", "completed", "revoked"],
        index=0,
        help="FHIR CarePlan.status",
    )
    intent = st.selectbox(
        "Intent",
        ["plan", "proposal", "order", "option"],
        index=0,
        help="FHIR CarePlan.intent",
    )

with form_b:
    today = datetime.date.today()
    period_start = st.date_input("Period start", value=today)
    period_end = st.date_input(
        "Period end",
        value=today + datetime.timedelta(days=90),
        help="Typical outreach window is 60–90 days.",
    )
    clinical_note = st.text_area(
        "Clinician note",
        placeholder="Free-text note attached to the CarePlan (optional).",
        height=100,
    )

# Activities editor
st.markdown("**Activities** — edit, add, or remove before submitting")

activities: List[ActivitySuggestion] = st.session_state[state_key]

activity_df = pd.DataFrame([
    {
        "Title": a.title,
        "Description": a.description,
        "Category": a.category,
        "Status": a.status,
    }
    for a in activities
])

edited = st.data_editor(
    activity_df,
    width="stretch",
    hide_index=True,
    num_rows="dynamic",
    column_config={
        "Title": st.column_config.TextColumn(required=True),
        "Description": st.column_config.TextColumn(width="large"),
        "Category": st.column_config.SelectboxColumn(
            options=["social", "clinical", "behavioral", "utilization"],
            required=True,
        ),
        "Status": st.column_config.SelectboxColumn(
            options=["not-started", "scheduled", "in-progress", "on-hold", "completed", "cancelled"],
            required=True,
        ),
    },
    key=f"cp_editor_{patient_id}",
)

reset_col, _ = st.columns([1, 5])
with reset_col:
    if st.button("Reset to suggestions", help="Rebuild activities from risk factors."):
        st.session_state[state_key] = suggest_activities(factor_names)
        st.rerun()

# Convert edited table back to ActivitySuggestion objects
edited_activities: List[ActivitySuggestion] = []
for _, r in edited.iterrows():
    title_val = str(r.get("Title") or "").strip()
    if not title_val:
        continue
    edited_activities.append(ActivitySuggestion(
        title=title_val,
        description=str(r.get("Description") or "").strip(),
        category=str(r.get("Category") or "social"),
        status=str(r.get("Status") or "not-started"),
    ))


# Build + preview resource

st.subheader("4. Preview FHIR R4 Resource")

cp_input = CarePlanInput(
    patient_id=str(patient_id),
    patient_name=str(patient_row["name"]),
    tier=tier_value,
    score=int(patient_row["score"]),
    title=title,
    status=status,
    intent=intent,
    period_start=period_start,
    period_end=period_end,
    clinical_note=clinical_note,
    activities=edited_activities,
    risk_factors=factor_names,
)

resource = build_care_plan_resource(
    cp_input,
    system_tag=settings.system_tag,
    code_tag=settings.code_tag,
    identifier_system=settings.org_identifier_system,
)

with st.expander("View full CarePlan JSON", expanded=False):
    st.json(resource)

st.caption(
    f"Resource: **CarePlan** · status=`{resource['status']}` · intent=`{resource['intent']}` · "
    f"activities={len(resource['activity'])}"
)


# Submit

st.subheader("5. Submit")

submit_label = "Preview (dry-run)" if dry_run else "POST CarePlan to FHIR Server"
submit_type = "secondary" if dry_run else "primary"

if st.button(submit_label, type=submit_type, width="stretch"):
    if not edited_activities:
        st.error("At least one activity is required before submission.")
    elif dry_run:
        st.success("Dry-run: resource is well-formed. Nothing was posted.")
        st.code(str(resource), language="json")
    else:
        with st.spinner("Posting CarePlan to FHIR server..."):
            try:
                result = get_client().write_care_plan(
                    patient_id=str(patient_id),
                    resource=resource,
                )
                new_id = result.get("id", "unknown")
                st.success(f"CarePlan created — FHIR ID: **{new_id}**")
                st.cache_data.clear()  # refresh history panel below
            except FHIRError as exc:
                st.error(f"FHIR rejected the resource: {exc}")
            except Exception as exc:
                st.error(f"Unexpected error: {exc}")


# Existing CarePlans for this patient

st.subheader("6. Existing CarePlans")

if data_source != "Live FHIR Server (HAPI)":
    st.info("Existing CarePlans are only queryable against the live FHIR server.")
else:
    @st.cache_data(show_spinner="Fetching CarePlans…", ttl=60)
    def _fetch_plans(pid: str) -> List[Dict[str, Any]]:
        return get_client().fetch_care_plans(pid)

    try:
        plans = _fetch_plans(str(patient_id))
    except Exception as exc:
        st.warning(f"Could not fetch existing CarePlans: {exc}")
        plans = []

    if not plans:
        st.write("_No prior CarePlans on record for this patient._")
    else:
        rows = []
        for p in plans:
            rows.append({
                "FHIR ID": p.get("id", ""),
                "Status": p.get("status", ""),
                "Intent": p.get("intent", ""),
                "Title": p.get("title", ""),
                "Created": p.get("created", ""),
                "Activities": len(p.get("activity") or []),
            })
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

        with st.expander("Inspect raw resources"):
            for p in plans:
                st.markdown(f"**{p.get('title', '(no title)')}** — `{p.get('id', '')}`")
                st.json(p)


# Footer

st.divider()
st.caption(
    f"Care Plan Documentation · FHIR R4 · {data_source} · "
    f"Mode: {'DRY-RUN' if dry_run else 'LIVE POST'}"
)
