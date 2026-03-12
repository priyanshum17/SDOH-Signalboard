import streamlit as st
import pandas as pd

from config import get_settings
from services.patient_repository import load_patient_frame

st.set_page_config(page_title="SDOH Risk Dashboard", layout="wide")
settings = get_settings()

# --- Styling (no custom JS) -------------------------------------------------
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@500;600;700&family=Space+Grotesk:wght@500&display=swap');
    html, body, [class*="css"] { font-family: 'Manrope', sans-serif; }
    .app-hero { background: linear-gradient(135deg, #0f172a, #1e293b); color: #e2e8f0; padding: 22px 24px; border-radius: 18px; border: 1px solid #334155; }
    .pill { display:inline-flex; align-items:center; gap:6px; padding:6px 10px; border-radius:999px; background:#1e293b; color:#e2e8f0; font-size:12px; text-transform:uppercase; letter-spacing:0.04em; }
    .pill strong { color:#38bdf8; }
    .metric-card { padding:14px; border-radius:14px; border:1px solid #e2e8f0; background:#0b1727; color:#e2e8f0; }
    .badge { display:inline-flex; align-items:center; padding:6px 10px; border-radius:10px; background:#0ea5e9; color:white; font-size:12px; margin:0 6px 6px 0; }
    .badge.alt { background:#22c55e; }
    .badge.warn { background:#f59e0b; }
    .section-title { margin-top:8px; margin-bottom:4px; font-weight:700; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="app-hero">
      <div class="pill">SMART on FHIR • <strong>Social Risk</strong></div>
      <h2 style="margin:10px 0 6px; font-family:'Space Grotesk', sans-serif; font-weight:700;">SDOH Risk Stratification Dashboard</h2>
      <p style="margin:0; color:#cbd5e1; max-width:820px;">Reads synthetic patients from a FHIR server, blends SDOH + clinical + utilization signals into a transparent Social Risk Score, and highlights who needs outreach first.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

@st.cache_data(show_spinner=True)
def load_data():
    return load_patient_frame()


try:
    df = load_data()
except Exception as exc:  # pragma: no cover
    st.error(f"Failed to load data from FHIR server: {exc}")
    st.stop()

if df.empty:
    st.info("No patients returned from the FHIR server.")
    st.stop()

raw_max = df["score"].max()
max_score = int(raw_max) if pd.notnull(raw_max) else 0
slider_max = max(1, max_score)  # avoid slider errors when all scores are 0
default_score = min(3, slider_max) if slider_max > 0 else 0

high_risk = int((df["score"] >= 6).sum())
housing_need = int(df[df["housing_insecure"]].shape[0])
recent_util = int((df["recent_encounters"] >= 2).sum())

metric_cols = st.columns(3)
metric_cols[0].metric("High-risk (score ≥ 6)", high_risk)
metric_cols[1].metric("Housing flags", housing_need)
metric_cols[2].metric("Recent ED-like visits (≥2)", recent_util)

col1, col2, col3 = st.columns(3)
with col1:
    min_score = st.slider("Minimum score", 0, slider_max, default_score)
    if max_score == 0:
        st.caption("All scores are 0; adjust filters after scoring weights are tuned.")
with col2:
    require_diabetes = st.checkbox("Only diabetes", value=False)
with col3:
    require_housing = st.checkbox("Only housing instability", value=False)

filtered = df[df["score"] >= min_score]
if require_diabetes:
    filtered = filtered[filtered["diabetes"]]
if require_housing:
    filtered = filtered[filtered["housing_insecure"]]

st.subheader("Prioritized patients")
st.dataframe(
    filtered[
        [
            "name",
            "age",
            "score",
            "recent_encounters",
            "housing_insecure",
            "food_insecure",
            "transport_barrier",
            "diabetes",
            "hypertension",
        ]
    ].rename(
        columns={
            "recent_encounters": "Recent encounters",
            "housing_insecure": "Housing",
            "food_insecure": "Food",
            "transport_barrier": "Transport",
        }
    ),
    width="stretch",
)

st.subheader("Details")
for _, row in filtered.iterrows():
    with st.expander(f"{row['name']} — score {row['score']}"):
        factors = row["factors"]
        if factors:
            badges = " ".join([
                f"<span class='badge {'warn' if 'Housing' in f or 'Food' in f else 'alt' if 'Age' in f else ''}'>{f}</span>"
                for f in factors
            ])
            st.markdown(badges, unsafe_allow_html=True)
        else:
            st.write("No risk factors found for this patient.")

        info_cols = st.columns(3)
        info_cols[0].markdown(
            f"**Demographics**\n\n- Age: {row['age'] if pd.notnull(row['age']) else 'N/A'}"
        )
        info_cols[1].markdown(
            "**SDOH**\n" \
            f"- Housing instability: {'Yes' if row['housing_insecure'] else 'No'}\n" \
            f"- Food insecurity: {'Yes' if row['food_insecure'] else 'No'}\n" \
            f"- Transport barrier: {'Yes' if row['transport_barrier'] else 'No'}\n" \
            f"- Employment risk: {'Yes' if row.get('unemployed', False) else 'No'}"
        )
        info_cols[2].markdown(
            "**Clinical & Utilization**\n" \
            f"- Diabetes: {'Yes' if row['diabetes'] else 'No'}\n" \
            f"- Hypertension: {'Yes' if row['hypertension'] else 'No'}\n" \
            f"- Recent encounters (≈6 mo): {int(row['recent_encounters'])}\n" \
            f"- Total encounters: {int(row['total_encounters'])}"
        )

st.caption(
    f"FHIR base: {settings.fhir_base_url} · Showing up to {settings.patient_limit} patients"
)
