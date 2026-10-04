"""
Effective Dose Calculator -- CT and PET/CT (v2)

Run with:  streamlit run app.py

Design notes for future-you (or a collaborator) reading this later:
  - This file is UI wiring only. All dosimetric logic lives in
    coefficients.py (CT), pet_coefficients.py (radiopharmaceuticals), and
    calculator.py (combining them), with all file I/O in io_utils.py --
    specifically so the calculation logic stays unit-tested
    (see test_calculator.py) independent of Streamlit.
  - Nothing here imputes missing data. Every ambiguous user choice (e.g.
    "apply one age to the whole file") is presented as an explicit,
    visible assumption the user opts into, not a silent default.
  - CT and PET/CT share the same column-mapping PATTERNS (pick a column,
    or a single fixed value for the whole file) but are implemented as
    separate code paths below rather than forced into one abstraction --
    PET/CT needs an extra tracer selector and an activity-unit toggle
    that CT doesn't, and premature sharing would make both harder to
    read for the modest amount of duplication it would save.
"""

import pandas as pd
import streamlit as st

from coefficients import CANONICAL_REGIONS, REGION_LABELS, TABLE_CITATION, TABLE_VERSION_ID
from pet_coefficients import RADIOPHARMACEUTICALS, RADIOPHARM_LABELS
from calculator import (
    calculate_effective_dose, summarize,
    calculate_pet_ct_effective_dose, summarize_pet,
)
from io_utils import load_table, to_download_bytes


st.set_page_config(page_title="Effective Dose Calculator", layout="wide")

NONE_OPTION = "(none -- not in file)"

st.title("Effective Dose Calculator")
st.caption(
    "Batch effective-dose estimation. Currently supports CT and PET/CT. "
    "Radiography and mammography are planned as separate calculators."
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

st.header("2. Modality")
modality = st.selectbox(
    "Modality",
    ["CT (available)", "PET/CT (available)", "Radiography (coming soon)", "Mammography (coming soon)"],
)
if modality not in ("CT (available)", "PET/CT (available)"):
    st.warning("Only CT and PET/CT are implemented in this version.")
    st.stop()


# =============================================================================
# Shared widgets: body-region and age column/fixed-value mapping
# =============================================================================
def region_mapping_ui(df, columns, key_prefix=""):
    region_mode = st.radio(
        "How is body region provided?",
        ["A column in the file (values will be mapped)", "A single region for every row in this file"],
        horizontal=True, key=f"{key_prefix}region_mode",
    )
    region_col, fixed_region, region_value_map = None, None, {}
    if region_mode == "A column in the file (values will be mapped)":
        region_col = st.selectbox(
            "Column containing body region", [NONE_OPTION] + columns, key=f"{key_prefix}region_col"
        )
        if region_col != NONE_OPTION:
            unique_vals = sorted(df[region_col].dropna().astype(str).unique())
            st.write(f"Map each distinct value found in '{region_col}' to a supported region:")
            region_choices = ["(unsupported / skip)"] + [REGION_LABELS[r] for r in CANONICAL_REGIONS]
            for val in unique_vals:
                choice = st.selectbox(f"  '{val}' ->", region_choices, key=f"{key_prefix}map_{val}")
                if choice != "(unsupported / skip)":
                    canonical = [r for r in CANONICAL_REGIONS if REGION_LABELS[r] == choice][0]
                    region_value_map[val] = canonical
    else:
        label_choice = st.selectbox(
            "Region for every row", [REGION_LABELS[r] for r in CANONICAL_REGIONS], key=f"{key_prefix}fixed_region"
        )
        fixed_region = [r for r in CANONICAL_REGIONS if REGION_LABELS[r] == label_choice][0]
        st.warning(f"This will apply region = '{label_choice}' to ALL {df.shape[0]} rows.")
    return region_mode, region_col, fixed_region, region_value_map


def age_mapping_ui(df, columns, key_prefix=""):
    age_mode = st.radio(
        "How is age provided?",
        ["A column in the file", "A single age for every row in this file"],
        horizontal=True, key=f"{key_prefix}age_mode",
    )
    if age_mode == "A column in the file":
        age_col = st.selectbox("Column containing age (years)", [NONE_OPTION] + columns, key=f"{key_prefix}age_col")
        fixed_age = None
    else:
        age_col = None
        fixed_age = st.number_input(
            "Age (years) to apply to every row",
            min_value=0.0, max_value=130.0, value=40.0, step=1.0, key=f"{key_prefix}fixed_age",
        )
        st.warning(
            f"This will apply age = {fixed_age} to ALL {df.shape[0]} rows. "
            "Only use this if certain every patient in this file is the same age."
        )
    return age_mode, age_col, fixed_age


# =============================================================================
# CT
# =============================================================================
if modality == "CT (available)":
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
reported to be up to ~30% higher in newer studies.

**Age binning:** ages are binned to the nearest of five reference points
(0, 1, 5, 10, adult); the adult cutoff used here is 18 years.

**Missing or invalid data is never guessed.** Any row missing DLP, age, or
region, or containing an implausible value, is left blank in the output
with a specific reason in the `dose_calc_status` column.
            """
        )

    st.header("3. Map required fields")

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

    st.subheader("Patient age")
    age_mode, age_col, fixed_age = age_mapping_ui(df, columns)

    st.subheader("Body region scanned")
    region_mode, region_col, fixed_region, region_value_map = region_mapping_ui(df, columns)

    st.header("4. Run")
    run = st.button("Calculate effective dose", type="primary")
    if not run:
        st.stop()

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
            work["_dlp_mGycm"] = pd.to_numeric(df[ctdivol_col], errors="coerce") * pd.to_numeric(df[length_col], errors="coerce")

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
    result = result.drop(columns=["_dlp_mGycm", "_age_years", "_region"])

    st.header("5. Results")
    stats = summarize(result)
    c1, c2, c3 = st.columns(3)
    c1.metric("Total rows", stats["n_total"])
    c2.metric("Calculated", stats["n_ok"])
    c3.metric("Flagged / not calculated", stats["n_failed"])
    if stats["n_failed"] > 0:
        st.warning(f"{stats['n_failed']} of {stats['n_total']} rows could not be calculated.")
        st.write(stats["failure_reasons"])

    st.dataframe(result, width="stretch")
    file_bytes, out_name, mime = to_download_bytes(result, uploaded.name)
    st.success(f"Your file is updated. Download '{out_name}' below.")
    st.download_button("Download updated file", data=file_bytes, file_name=out_name, mime=mime, type="primary")


# =============================================================================
# PET/CT
# =============================================================================
elif modality == "PET/CT (available)":
    with st.expander("Methodology and limitations (read before use)", expanded=False):
        st.markdown(
            f"""
**Method:** total effective dose (mSv) = CT component + NM component.

- **CT component:** `DLP x k`, same EUR16262/AAPM96 table as the CT
  calculator (version `{TABLE_VERSION_ID}`). {TABLE_CITATION}
- **NM component:** `injected activity (MBq) x radiopharmaceutical
  coefficient`. Each tracer's coefficient and citation are shown below --
  these come from different kinds of primary sources (an ICRP report, an
  FDA drug label, or the literature) and are **not** equally settled; see
  each tracer's note.

**This reports the CT and NM components separately as well as a total.**
If one component is missing or invalid for a row, that component's value
and reason are still shown; the total is left blank rather than silently
computed from only one part.

**Known gaps in this version:**
- No pediatric FDG coefficients (adult value is used for ALL ages --
  this is *not* age-corrected for FDG specifically; see tracer note below).
- 68Ga-PSMA-11 has no established single regulatory coefficient; a
  package-insert default is used, overridable per your own protocol.
- Age binning for CT (5 reference points) and for 68Ga-DOTATATE (6
  reference points, including a 15-year point) come from different
  source tables and are intentionally not unified.
            """
        )
        for key, entry in RADIOPHARMACEUTICALS.items():
            st.markdown(f"**{entry['label']}:** {entry['citation']}")
            if "note" in entry:
                st.caption(entry["note"])

    st.header("3. Map required fields")

    include_ct = st.checkbox(
        "Include CT dose component (uncheck for PET-only / no diagnostic CT data available)",
        value=True,
    )

    if include_ct:
        st.subheader("CT: Dose Length Product (DLP, mGy*cm)")
        dlp_mode = st.radio(
            "How is DLP provided in your file?",
            ["A single DLP column", "Computed from CTDIvol x scan length"],
            horizontal=True, key="pet_dlp_mode",
        )
        if dlp_mode == "A single DLP column":
            dlp_col = st.selectbox("Column containing DLP (mGy*cm)", [NONE_OPTION] + columns, key="pet_dlp_col")
            ctdivol_col = length_col = None
        else:
            ctdivol_col = st.selectbox("Column containing CTDIvol (mGy)", [NONE_OPTION] + columns, key="pet_ctdivol_col")
            length_col = st.selectbox("Column containing scan length (cm)", [NONE_OPTION] + columns, key="pet_length_col")
            dlp_col = None

        st.subheader("CT: Body region scanned")
        region_mode, region_col, fixed_region, region_value_map = region_mapping_ui(df, columns, key_prefix="pet_")

    st.subheader("Patient age (used for both CT and NM components)")
    age_mode, age_col, fixed_age = age_mapping_ui(df, columns, key_prefix="pet_")

    st.subheader("NM: Radiopharmaceutical")
    radiopharm_label_choice = st.selectbox("Radiopharmaceutical", list(RADIOPHARM_LABELS.values()))
    radiopharm_key = [k for k, v in RADIOPHARM_LABELS.items() if v == radiopharm_label_choice][0]
    same_tracer_for_all_rows = st.checkbox(
        "Same radiopharmaceutical for every row in this file", value=True,
    )
    radiopharm_col = None
    radiopharm_value_map = {}
    if not same_tracer_for_all_rows:
        radiopharm_col = st.selectbox(
            "Column containing radiopharmaceutical name (values will be mapped)",
            [NONE_OPTION] + columns,
        )
        if radiopharm_col != NONE_OPTION:
            unique_vals = sorted(df[radiopharm_col].dropna().astype(str).unique())
            choices = ["(unsupported / skip)"] + list(RADIOPHARM_LABELS.values())
            for val in unique_vals:
                choice = st.selectbox(f"  '{val}' ->", choices, key=f"pet_tracer_map_{val}")
                if choice != "(unsupported / skip)":
                    canonical = [k for k, v in RADIOPHARM_LABELS.items() if v == choice][0]
                    radiopharm_value_map[val] = canonical

    st.subheader("NM: Injected activity")
    activity_mode = st.radio(
        "How is injected activity provided?",
        ["A column in the file", "A single activity for every row in this file"],
        horizontal=True,
    )
    activity_unit = st.radio("Activity unit", ["MBq", "mCi"], horizontal=True)
    if activity_mode == "A column in the file":
        activity_col = st.selectbox("Column containing injected activity", [NONE_OPTION] + columns)
        fixed_activity = None
    else:
        activity_col = None
        fixed_activity = st.number_input(f"Activity ({activity_unit}) to apply to every row", min_value=0.0, value=300.0)
        st.warning(f"This will apply activity = {fixed_activity} {activity_unit} to ALL {df.shape[0]} rows.")

    st.header("4. Run")
    run = st.button("Calculate effective dose", type="primary")
    if not run:
        st.stop()

    errors = []
    work = df.copy()

    if include_ct:
        if dlp_mode == "A single DLP column":
            if dlp_col == NONE_OPTION:
                errors.append("Select a DLP column, or switch to CTDIvol x length.")
            else:
                work["_dlp_mGycm"] = pd.to_numeric(df[dlp_col], errors="coerce")
        else:
            if ctdivol_col == NONE_OPTION or length_col == NONE_OPTION:
                errors.append("Select both a CTDIvol column and a scan length column.")
            else:
                work["_dlp_mGycm"] = pd.to_numeric(df[ctdivol_col], errors="coerce") * pd.to_numeric(df[length_col], errors="coerce")

        if region_mode == "A column in the file (values will be mapped)":
            if region_col == NONE_OPTION:
                errors.append("Select a region column, or switch to a single fixed region.")
            else:
                work["_region"] = df[region_col].astype(str).map(region_value_map)
        else:
            work["_region"] = fixed_region

    if age_mode == "A column in the file":
        if age_col == NONE_OPTION:
            errors.append("Select an age column, or switch to a single fixed age.")
        else:
            work["_age_years"] = pd.to_numeric(df[age_col], errors="coerce")
    else:
        work["_age_years"] = fixed_age

    if same_tracer_for_all_rows:
        work["_radiopharm"] = radiopharm_key
    else:
        if radiopharm_col is None or radiopharm_col == NONE_OPTION:
            errors.append("Select a radiopharmaceutical column, or switch to a single tracer for the whole file.")
        else:
            work["_radiopharm"] = df[radiopharm_col].astype(str).map(radiopharm_value_map)

    if activity_mode == "A column in the file":
        if activity_col == NONE_OPTION:
            errors.append("Select an activity column, or switch to a single fixed activity.")
        else:
            raw_activity = pd.to_numeric(df[activity_col], errors="coerce")
            work["_activity_MBq"] = raw_activity * 37.0 if activity_unit == "mCi" else raw_activity
    else:
        activity_value = fixed_activity * 37.0 if activity_unit == "mCi" else fixed_activity
        work["_activity_MBq"] = activity_value

    if errors:
        for e in errors:
            st.error(e)
        st.stop()

    result = calculate_pet_ct_effective_dose(work, include_ct=include_ct)
    drop_cols = ["_age_years", "_activity_MBq", "_radiopharm"]
    if include_ct:
        drop_cols += ["_dlp_mGycm", "_region"]
    result = result.drop(columns=drop_cols)

    st.header("5. Results")
    stats = summarize_pet(result)
    c1, c2, c3 = st.columns(3)
    c1.metric("Total rows", stats["n_total"])
    c2.metric("Calculated (total)", stats["n_ok"])
    c3.metric("Incomplete", stats["n_failed"])
    if stats["n_failed"] > 0:
        st.warning(
            f"{stats['n_failed']} of {stats['n_total']} rows have an incomplete total. "
            "Check the per-component columns -- one part may still be valid."
        )
        st.write(stats["failure_reasons"])

    st.dataframe(result, width="stretch")
    file_bytes, out_name, mime = to_download_bytes(result, uploaded.name)
    st.success(f"Your file is updated. Download '{out_name}' below.")
    st.download_button("Download updated file", data=file_bytes, file_name=out_name, mime=mime, type="primary")
