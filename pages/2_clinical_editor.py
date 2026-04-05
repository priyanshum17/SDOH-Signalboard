import streamlit as st
import pandas as pd
from services.patient_repository import load_patient_frame
from services.fhir_client import get_client

st.title("Clinical Data Editor (FHIR Write-Back)")
st.caption("Bidirectional update matrix. Changes made here are securely sent to the active FHIR server system via PRAPARE Observation POSTs.")

st.warning("You are modifying live FHIR data. Audit logs are permanently appended.")

# 1. Load the original reference dataframe
@st.cache_data(show_spinner="Loading patient registry...")
def load_live_data():
    return load_patient_frame(source_mode="Live FHIR Server (HAPI)")

try:
    df = load_live_data()
except Exception as exc:
    st.error(f"Failed to connect to FHIR Server: {exc}")
    st.stop()

if df.empty:
    st.info("No patients available to edit.")
    st.stop()

st.subheader(f"Patient Registry ({len(df)} Records)")

# 2. Extract editable table
# We only want to let them edit SDOH markers to avoid breaking underlying clinical logic in this demo
editable_cols = ["housing_insecure", "food_insecure", "transport_barrier", "unemployed"]
display_df = df[["id", "name", "score"] + editable_cols].copy()

# Lock the core fields
column_config = {
    "id": st.column_config.TextColumn("FHIR ID", disabled=True),
    "name": st.column_config.TextColumn("Patient Name", disabled=True),
    "score": st.column_config.NumberColumn("Current Risk Score", disabled=True),
    "housing_insecure": st.column_config.CheckboxColumn("Housing (Homeless/Unstable)"),
    "food_insecure": st.column_config.CheckboxColumn("Food Insecure"),
    "transport_barrier": st.column_config.CheckboxColumn("Transport Barrier"),
    "unemployed": st.column_config.CheckboxColumn("Unemployed"),
}

with st.form("clinical_editor_form"):
    edited_df = st.data_editor(
        display_df, 
        column_config=column_config, 
        use_container_width=True,
        hide_index=True
    )
    
    commit_pressed = st.form_submit_button("Commit Changes to FHIR Database", type="primary")

if commit_pressed:
    client = get_client()
    changes_made = 0
    
    with st.status("Syncing with FHIR Server...", expanded=True) as status:
        # Iterate over both dataframes to find diffs
        for idx in range(len(df)):
            orig_row = display_df.iloc[idx]
            new_row = edited_df.iloc[idx]
            patient_id = orig_row["id"]
            patient_name = orig_row["name"]
            
            for col in editable_cols:
                old_val = bool(orig_row[col])
                new_val = bool(new_row[col])
                
                if old_val != new_val:
                    st.write(f"Pushing {col} update for {patient_name} (ID: {patient_id}) -> {new_val}")
                    try:
                        client.publish_sdoh_observation(patient_id, col, new_val)
                        changes_made += 1
                    except Exception as e:
                        st.error(f"Failed to post update for {patient_name}: {e}")
                        
        if changes_made > 0:
            status.update(label=f"Successfully pushed {changes_made} new FHIR observations!", state="complete", expanded=False)
            st.success("Successfully pushed exactly %d new records to the FHIR Sandbox." % changes_made)
            
            # CRITICAL: Clear the cache so the dashboard physically re-fetches the updated data!
            st.cache_data.clear()
            st.rerun()
        else:
            status.update(label="No changes detected.", state="complete", expanded=False)
            st.info("No modifications were made to the patient registry.")
