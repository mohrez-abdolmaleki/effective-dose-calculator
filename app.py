"""
CT Effective Dose Calculator -- v1 (CT only, EUR16262/AAPM96 coefficient table)

Run with:  streamlit run app.py

Design notes for future-you (or a collaborator) reading this later:
  - This file is UI wiring only. All dosimetric logic lives in
    coefficients.py and calculator.py, and all file I/O lives in
    io_utils.py, specifically so the calculation logic can be unit-tested
    (see test_calculator.py) independent of Streamlit.
  - Nothing here imputes missing data. Every ambiguous user choice (e.g.
    "apply one age to the whole file") is presented as an explicit,
    visible assumption the user opts into, not a silent default.
"""

import pandas as pd
import streamlit as st

from coefficients import CANONICAL_REGIONS, REGION_LABELS, TABLE_CITATION, TABLE_VERSION_ID
from calculator import calculate_effective_dose, summarize
from io_utils import load_table, to_download_bytes


st.set_page_config(page_title="CT Effective Dose Calculator", layout="wide")

st.title("CT Effective Dose Calculator")
st.caption(
    "Batch DLP -> effective dose estimation for CT. "
    "Currently supports CT only; other modalities (PET/CT, radiography, "
    "mammography) are planned as separate calculators."
)

with st.expander("Methodology and limitations (read before use)", expanded=False):
    st.markdown(
        f"""
**Method:** effective dose (mSv) is estimated as `DLP (mGy*cm) x k`, where
`k` is an age- and body-region-dependent coefficient.

**Coefficient source (version `{TABLE_VERSION_ID}`):** {TABLE_CITATION}

**This is a population-reference approximation, not a patient-specific
dose.** It reflects ICRP Publication 60 (1990) tissue-weighting factors,
consistent with most current national Diagnostic Reference Level programs.
It does *not* reflect the updated ICRP Publication 103 (2007) weighting
factors, under which coefficients for some regions (notably chest) are
reported to be up to ~30% higher in newer studies. If your use case
requires ICRP 103-consistent values, do not treat this tool's output as
equivalent -- flag this explicitly in any downstream reporting.

**Age binning:** ages are binned to the nearest of five reference points
(0, 1, 5, 10, adult); the adult cutoff used here is 18 years.

**Missing or invalid data is never guessed.** Any row missing DLP, age, or
region, or containing an implausible value, is left blank in the output
with a specific reason in the `dose_calc_status` column.
        """
    )

st.header("1. Upload file")
uploaded = st.file_uploader("CSV, XLSX, or XLS file", type=["csv", "xlsx", "xls"])

if uploaded is None:
    st.info("Upload a file to begin.")
    st.stop()

try:
    df = load_table(uploaded, uploaded.name)
except ValueError as e:
    st.error(str(e))
    st.stop()

st.success(f"Loaded '{uploaded.name}': {df.shape[0]} rows, {df.shape[1]} columns.")
st.dataframe(df.head(10), width="stretch")

columns = list(df.columns)
NONE_OPTION = "(none -- not in file)"

st.header("2. Modality")
modality = st.selectbox("Modality", ["CT (available)", "PET/CT (coming soon)", "Radiography (coming soon)"])
if modality != "CT (available)":
    st.warning("Only CT is implemented in this version. Select 'CT (available)' to continue.")
    st.stop()

st.header("3. Map required fields")

# --- DLP -----------------------------------------------------------------
st.subheader("Dose Length Product (DLP, mGy*cm)")
dlp_mode = st.radio(
    "How is DLP provided in your file?",
    ["A single DLP column", "Computed from CTDIvol x scan length"],
    horizontal=True,
)
if dlp_mode == "A single DLP column":
    dlp_col = st.selectbox("Column containing DLP (mGy*cm)", [NONE_OPTION] + columns)
    ctdivol_col = length_col = None
else:
    ctdivol_col = st.selectbox("Column containing CTDIvol (mGy)", [NONE_OPTION] + columns)
    length_col = st.selectbox("Column containing scan length (cm)", [NONE_OPTION] + columns)
    dlp_col = None

# --- Age -------------------------------------------------------------------
st.subheader("Patient age")
age_mode = st.radio(
    "How is age provided?",
    ["A column in the file", "A single age for every row in this file"],
    horizontal=True,
)
if age_mode == "A column in the file":
    age_col = st.selectbox("Column containing age (years)", [NONE_OPTION] + columns)
    fixed_age = None
else:
    age_col = None
    fixed_age = st.number_input(
        "Age (years) to apply to every row",
        min_value=0.0, max_value=130.0, value=40.0, step=1.0,
    )
    st.warning(
        f"This will apply age = {fixed_age} to ALL {df.shape[0]} rows. "
        "Only use this if you are certain every patient in this file is "
        "the same age -- otherwise use a per-row column instead."
    )

# --- Region ------------------------------------------------------------
st.subheader("Body region scanned")
region_mode = st.radio(
    "How is body region provided?",
    ["A column in the file (values will be mapped)", "A single region for every row in this file"],
    horizontal=True,
)
region_col = None
fixed_region = None
region_value_map = {}

if region_mode == "A column in the file (values will be mapped)":
    region_col = st.selectbox("Column containing body region", [NONE_OPTION] + columns)
    if region_col != NONE_OPTION:
        unique_vals = sorted(df[region_col].dropna().astype(str).unique())
        st.write(f"Map each distinct value found in '{region_col}' to a supported region:")
        region_choices = ["(unsupported / skip)"] + [REGION_LABELS[r] for r in CANONICAL_REGIONS]
        for val in unique_vals:
            choice = st.selectbox(f"  '{val}' ->", region_choices, key=f"map_{val}")
            if choice != "(unsupported / skip)":
                canonical = [r for r in CANONICAL_REGIONS if REGION_LABELS[r] == choice][0]
                region_value_map[val] = canonical
else:
    label_choice = st.selectbox("Region for every row", [REGION_LABELS[r] for r in CANONICAL_REGIONS])
    fixed_region = [r for r in CANONICAL_REGIONS if REGION_LABELS[r] == label_choice][0]
    st.warning(
        f"This will apply region = '{label_choice}' to ALL {df.shape[0]} rows."
    )

st.header("4. Run")
run = st.button("Calculate effective dose", type="primary")

if not run:
    st.stop()

# --- Build the standardized internal columns, validating selections first ---
errors = []
work = df.copy()

if dlp_mode == "A single DLP column":
    if dlp_col == NONE_OPTION:
        errors.append("Select a DLP column, or switch to CTDIvol x length.")
    else:
        work["_dlp_mGycm"] = pd.to_numeric(df[dlp_col], errors="coerce")
else:
    if ctdivol_col == NONE_OPTION or length_col == NONE_OPTION:
        errors.append("Select both a CTDIvol column and a scan length column.")
    else:
        ctdivol = pd.to_numeric(df[ctdivol_col], errors="coerce")
        length = pd.to_numeric(df[length_col], errors="coerce")
        work["_dlp_mGycm"] = ctdivol * length

if age_mode == "A column in the file":
    if age_col == NONE_OPTION:
        errors.append("Select an age column, or switch to a single fixed age.")
    else:
        work["_age_years"] = pd.to_numeric(df[age_col], errors="coerce")
else:
    work["_age_years"] = fixed_age

if region_mode == "A column in the file (values will be mapped)":
    if region_col == NONE_OPTION:
        errors.append("Select a region column, or switch to a single fixed region.")
    else:
        work["_region"] = df[region_col].astype(str).map(region_value_map)
else:
    work["_region"] = fixed_region

if errors:
    for e in errors:
        st.error(e)
    st.stop()

result = calculate_effective_dose(work)
# Drop the internal helper columns from the final output -- keep original
# columns plus the new effective_dose_mSv / dose_calc_status /
# coefficient_table_version columns only.
result = result.drop(columns=["_dlp_mGycm", "_age_years", "_region"])

st.header("5. Results")
stats = summarize(result)
c1, c2, c3 = st.columns(3)
c1.metric("Total rows", stats["n_total"])
c2.metric("Calculated", stats["n_ok"])
c3.metric("Flagged / not calculated", stats["n_failed"])

if stats["n_failed"] > 0:
    st.warning(
        f"{stats['n_failed']} of {stats['n_total']} rows could not be calculated. "
        "These rows were left blank rather than estimated -- see reasons below."
    )
    st.write(stats["failure_reasons"])

st.dataframe(result, width="stretch")

file_bytes, out_name, mime = to_download_bytes(result, uploaded.name)
st.success(f"Your file is updated. Download '{out_name}' below.")
st.download_button(
    "Download updated file",
    data=file_bytes,
    file_name=out_name,
    mime=mime,
    type="primary",
)
