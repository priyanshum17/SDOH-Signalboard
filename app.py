import streamlit as st

# The master page config must be set here on the main entrypoint
st.set_page_config(page_title="SDOH Signal Board", layout="wide")

dash = st.Page("pages/1_dashboard.py", title="Dashboard", default=True)
editor = st.Page("pages/2_clinical_editor.py", title="Clinical Editor")

pg = st.navigation([dash, editor])
pg.run()
