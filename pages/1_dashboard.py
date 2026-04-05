"""SDOH Risk Stratification Dashboard — pure Streamlit components."""

import streamlit as st
import pandas as pd

from config import get_settings
from services.patient_repository import load_patient_frame
from services.fhir_client import get_client
from domain.scoring import score_to_tier

settings = get_settings()

# ---- Sidebar controls ----

with st.sidebar:
    st.header("Settings")
    data_source = st.radio(
        "Data Source Integration",
        options=[
            "Live FHIR Server (HAPI)",
            "Local Generation (Synthea)",
            "Legacy Demo Data (Backup)",
        ],
        index=0,
        help="Switch dynamically between live REST connections and local static bundles."
    )

    st.header("Filters")
    min_score = st.slider("Minimum Risk Score", 0, 50, 0)
    
# ---- Load data ----

@st.cache_data(show_spinner="Loading patient data…")
def load_data(source: str):
    return load_patient_frame(source_mode=source)

try:
    df = load_data(data_source)
except Exception as exc:
    st.error(f"Failed to load data: {exc}")
    st.stop()

if df.empty:
    st.info("No patients returned.")
    st.stop()

# ---- Header ----

st.title("SDOH Risk Stratification Dashboard")
st.caption(f"FHIR R4 · PRAPARE-aligned · Source: **{data_source}** · {len(df)} patients")

with st.sidebar:
    st.subheader("SDOH Flags")
    f_housing = st.checkbox("Housing instability")
    f_food = st.checkbox("Food insecurity")
    f_transport = st.checkbox("Transport barrier")
    f_unemployed = st.checkbox("Unemployed")

    st.subheader("Conditions")
    f_diabetes = st.checkbox("Diabetes")
    f_htn = st.checkbox("Hypertension")

    st.subheader("Risk Tier")
    tier = st.radio("Show", ["All", "High (≥ 12)", "Medium (7–11)", "Low (0–6)"], label_visibility="collapsed")

# ---- Apply filters ----

filtered = df[df["score"] >= min_score].copy()
if f_housing:   filtered = filtered[filtered["housing_insecure"]]
if f_food:      filtered = filtered[filtered["food_insecure"]]
if f_transport: filtered = filtered[filtered["transport_barrier"]]
if f_unemployed:filtered = filtered[filtered["unemployed"]]
if f_diabetes:  filtered = filtered[filtered["diabetes"]]
if f_htn:       filtered = filtered[filtered["hypertension"]]
if "High" in tier:   filtered = filtered[filtered["score"] >= 12]
elif "Medium" in tier: filtered = filtered[(filtered["score"] >= 7) & (filtered["score"] <= 11)]
elif "Low" in tier:  filtered = filtered[filtered["score"] <= 6]

# ---- Metrics row ----

c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("HIGH Risk", int((df["score"] >= 8).sum()))
c2.metric("MEDIUM", int(((df["score"] >= 4) & (df["score"] <= 7)).sum()))
c3.metric("LOW", int((df["score"] <= 3).sum()))
c4.metric("Housing Issues", int(df["housing_insecure"].sum()))
c5.metric("Food Issues", int(df["food_insecure"].sum()))
c6.metric("Avg Score", round(df["score"].mean(), 1))

# ---- Score distribution ----

st.subheader("Score Distribution")
chart = df["score"].value_counts().sort_index().reset_index()
chart.columns = ["Score", "Count"]
st.bar_chart(chart, x="Score", y="Count", height=200)

# ---- Patient table ----

def _tier(s):
    return score_to_tier(s).value

st.subheader(f"Prioritized Patients ({len(filtered)} of {len(df)})")

tbl = filtered[["name","age","gender","score","recent_ed_visits","recent_encounters",
                 "housing_insecure","food_insecure","transport_barrier","unemployed",
                 "diabetes","hypertension"]].copy()
tbl.insert(3, "tier", tbl["score"].apply(_tier))
tbl.columns = ["Patient","Age","Gender","Tier","Score","ED (6mo)","Visits (6mo)",
               "Housing","Food","Transport","Unemployed","Diabetes","HTN"]
st.dataframe(tbl, width="stretch", height=400)

# ---- Patient details ----

st.subheader("Patient Details")

for _, row in filtered.iterrows():
    score = row["score"]
    tier_txt = score_to_tier(score).value

    with st.expander(f"{row['name']}  —  Score {score}/20  {tier_txt}"):
        # Factor breakdown
        details = row.get("details", [])
        if details:
            factors_df = pd.DataFrame([
                {"Factor": d.name, "Points": f"+{d.points}", "Severity": d.severity.upper(), "Explanation": d.explanation}
                for d in details
            ])
            st.dataframe(factors_df, hide_index=True, width="stretch")
        else:
            st.write("No risk factors identified.")

        st.divider()

        # Demographics / SDOH / Clinical in 3 columns
        d1, d2, d3 = st.columns(3)

        with d1:
            st.markdown("**Demographics**")
            age_v = row["age"] if pd.notnull(row.get("age")) else "N/A"
            st.write(f"Age: {age_v}")
            st.write(f"Gender: {str(row.get('gender','N/A')).capitalize()}")
            city = row.get("city", "")
            state = row.get("state", "")
            st.write(f"Location: {city}, {state}" if city else "Location: N/A")

        with d2:
            st.markdown("**SDOH Screening**")
            flags = [
                ("Housing instability", row["housing_insecure"]),
                ("Food insecurity", row["food_insecure"]),
                ("Transport barrier", row["transport_barrier"]),
                ("Unemployment", row["unemployed"]),
                ("High stress", row.get("high_stress", False)),
            ]
            for label, val in flags:
                icon = "[YES]" if val else " [NO]"
                st.write(f"{icon} {label}")

        with d3:
            st.markdown("**Clinical & Utilization**")
            st.write(f"{'[YES]' if row['diabetes'] else ' [NO]'} Diabetes")
            st.write(f"{'[YES]' if row['hypertension'] else ' [NO]'} Hypertension")
            st.write(f"ED visits (6 mo): {int(row['recent_ed_visits'])}")
            st.write(f"Encounters (6 mo): {int(row['recent_encounters'])}")
            st.write(f"Total encounters: {int(row['total_encounters'])}")
        # optional careplan / servicerequest write-back to fhir server
        if tier_txt == "HIGH":
            st.divider()
            st.markdown("**Documentation Write-Back** *(optional — writes to FHIR server)*")
 
            # guard against non-live modes because synthea/demo patient id's don't exist on hapi server
            if data_source != "Live FHIR Server (HAPI)":
                st.warning("Write-back is only available when using Live FHIR Server (HAPI). Switch data sources in the sidebar.")
            else:
                col_a, col_b = st.columns(2)
 
                with col_a:
                    if st.button("Create CarePlan", key=f"cp_{row['id']}"):
                        with st.spinner("Writing CarePlan..."):
                            try:
                                result = get_client().write_care_plan(
                                    patient_id=str(row['id']),
                                    tier=tier_txt,
                                    score=score,
                                    factors=row.get("details", []),
                                )
                                st.success(f"CarePlan created — ID: {result.get('id', 'unknown')}")
                            except Exception as e:
                                st.error(f"Failed: {e}")
 
                with col_b:
                    reason = st.selectbox(
                        "Referral type",
                        ["Social Work Referral", "Housing Services", "Food Assistance", "Transportation"],
                        key=f"sr_reason_{row['id']}",
                    )
                    if st.button("Create ServiceRequest", key=f"sr_{row['id']}"):
                        with st.spinner("Writing ServiceRequest..."):
                            try:
                                result = get_client().write_service_request(
                                    patient_id=str(row['id']),  
                                    tier=tier_txt,
                                    score=score,
                                    reason=reason,
                                )
                                st.success(f"ServiceRequest created — ID: {result.get('id', 'unknown')}")
                            except Exception as e:
                                st.error(f"Failed: {e}")
 

# ---- Footer ----

st.divider()
st.caption(f"SDOH Signal Board · FHIR R4 · PRAPARE · {len(filtered)}/{len(df)} patients shown")
