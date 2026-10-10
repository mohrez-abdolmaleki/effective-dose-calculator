"""
Effective Dose Calculator -- CT, PET/CT and SPECT (v3)

Run with:  streamlit run app.py

Design notes for future-you (or a collaborator):
  - UI wiring only. Dosimetry lives in coefficients.py (CT),
    pet_coefficients.py / spect_coefficients.py (radiopharmaceuticals, shared
    lookup in radiopharm_core.py) and calculator.py. File handling lives in
    io_utils.py. The calculation code is unit-tested without Streamlit.
  - Nothing here imputes missing data. Every "apply one value to the whole
    file" choice is an explicit, visible opt-in.
  - PET/CT and SPECT share ONE nuclear-medicine workflow (nm_workflow); they
    differ only in the tracer registry, the calculator function and a few
    labels.
"""

import pandas as pd
import streamlit as st

from coefficients import CANONICAL_REGIONS, REGION_LABELS, TABLE_CITATION, TABLE_VERSION_ID
from pet_coefficients import RADIOPHARMACEUTICALS as PET_REGISTRY, RADIOPHARM_LABELS as PET_LABELS
from spect_coefficients import SPECT_RADIOPHARMACEUTICALS as SPECT_REGISTRY, SPECT_LABELS
from calculator import (
    calculate_effective_dose, summarize,
    calculate_pet_ct_effective_dose, calculate_spect_effective_dose, summarize_nm,
    CT_OUTPUT_COLUMNS, NM_OUTPUT_COLUMNS, INTERNAL_COLUMNS, MAX_PLAUSIBLE_ACTIVITY_MBQ,
)
from io_utils import (
    load_table, list_excel_sheets, find_collisions, to_numeric_with_report, to_download_bytes,
)

st.set_page_config(page_title="Effective Dose Calculator", layout="wide")

NONE_OPTION = "(none -- not in file)"
SKIP_OPTION = "(unsupported / skip)"
MCI_TO_MBQ = 37.0

st.title("Effective Dose Calculator")
st.caption(
    "Batch effective-dose estimation for CT, PET/CT and SPECT. "
    "Radiography and mammography are planned as separate calculators."
)

# =============================================================================
# 1. Upload
# =============================================================================
st.header("1. Upload file")
uploaded = st.file_uploader("CSV, XLSX, or XLS file", type=["csv", "xlsx", "xls"])
if uploaded is None:
    st.info("Upload a file to begin.")
    st.stop()

try:
    sheets = list_excel_sheets(uploaded, uploaded.name)
    sheet_choice = None
    if len(sheets) > 1:
        sheet_choice = st.selectbox("This workbook has several sheets. Which one holds the patient data?", sheets)
        st.info("Only this sheet is processed and written to the output file; the other sheets are not copied.")
    elif sheets:
        sheet_choice = sheets[0]
    df, file_info = load_table(uploaded, uploaded.name, sheet_choice)
except ValueError as e:
    st.error(str(e))
    st.stop()

st.success(f"Loaded '{uploaded.name}': {df.shape[0]} rows, {df.shape[1]} columns.")
st.dataframe(df.head(10), width="stretch")
columns = list(df.columns)

# =============================================================================
# 2. Modality
# =============================================================================
st.header("2. Modality")
MOD_CT = "CT"
MOD_PET = "PET/CT"
MOD_SPECT = "SPECT (also planar scintigraphy; optional CT for SPECT/CT)"
modality = st.selectbox(
    "Modality",
    [MOD_CT, MOD_PET, MOD_SPECT, "Radiography (coming soon)", "Mammography (coming soon)"],
)
if modality not in (MOD_CT, MOD_PET, MOD_SPECT):
    st.warning("Only CT, PET/CT and SPECT are implemented in this version.")
    st.stop()

# Never overwrite the user's own columns.
output_cols = CT_OUTPUT_COLUMNS if modality == MOD_CT else NM_OUTPUT_COLUMNS
clashes = find_collisions(df, list(output_cols) + INTERNAL_COLUMNS)
if clashes:
    st.error(
        f"Your file already contains column(s) named {clashes}, which this tool uses for its "
        "results. Rename or remove them in your file and upload again, so nothing of yours is overwritten."
    )
    st.stop()


# =============================================================================
# Shared mapping widgets
# =============================================================================
def numeric_column(column_name):
    """Column -> numbers, warning about text that could not be parsed."""
    numeric, warning = to_numeric_with_report(df[column_name], column_name)
    if warning:
        st.warning(warning)
    return numeric


def dlp_ui(prefix):
    mode = st.radio(
        "How is DLP provided in your file?",
        ["A single DLP column", "Computed from CTDIvol x scan length"],
        horizontal=True, key=f"{prefix}dlp_mode",
    )
    if mode == "A single DLP column":
        col = st.selectbox("Column containing DLP (mGy*cm)", [NONE_OPTION] + columns, key=f"{prefix}dlp_col")
        return {"single": True, "dlp_col": col}
    ctdivol = st.selectbox("Column containing CTDIvol (mGy)", [NONE_OPTION] + columns, key=f"{prefix}ctdivol_col")
    length = st.selectbox("Column containing scan length (cm)", [NONE_OPTION] + columns, key=f"{prefix}length_col")
    return {"single": False, "ctdivol_col": ctdivol, "length_col": length}


def apply_dlp(work, spec, errors):
    if spec["single"]:
        if spec["dlp_col"] == NONE_OPTION:
            errors.append("Select a DLP column, or switch to CTDIvol x length.")
        else:
            work["_dlp_mGycm"] = numeric_column(spec["dlp_col"])
    else:
        if NONE_OPTION in (spec["ctdivol_col"], spec["length_col"]):
            errors.append("Select both a CTDIvol column and a scan length column.")
        else:
            work["_dlp_mGycm"] = numeric_column(spec["ctdivol_col"]) * numeric_column(spec["length_col"])


def age_ui(prefix):
    mode = st.radio(
        "How is age provided?",
        ["A column in the file", "A single age for every row in this file"],
        horizontal=True, key=f"{prefix}age_mode",
    )
    if mode == "A column in the file":
        col = st.selectbox("Column containing age (years)", [NONE_OPTION] + columns, key=f"{prefix}age_col")
        return {"column": True, "col": col}
    value = st.number_input(
        "Age (years) to apply to every row", min_value=0.0, max_value=130.0, value=40.0, step=1.0,
        key=f"{prefix}fixed_age",
    )
    st.warning(
        f"This will apply age = {value} to ALL {df.shape[0]} rows. "
        "Only use this if every patient in this file is the same age."
    )
    return {"column": False, "value": value}


def apply_age(work, spec, errors):
    if spec["column"]:
        if spec["col"] == NONE_OPTION:
            errors.append("Select an age column, or switch to a single fixed age.")
        else:
            work["_age_years"] = numeric_column(spec["col"])
    else:
        work["_age_years"] = spec["value"]


def region_ui(prefix):
    mode = st.radio(
        "How is body region provided?",
        ["A column in the file (values will be mapped)", "A single region for every row in this file"],
        horizontal=True, key=f"{prefix}region_mode",
    )
    if mode.startswith("A column"):
        col = st.selectbox("Column containing body region", [NONE_OPTION] + columns, key=f"{prefix}region_col")
        value_map = {}
        if col != NONE_OPTION:
            unique_vals = sorted(df[col].dropna().astype(str).unique())
            st.write(f"Map each distinct value found in '{col}' to a supported region:")
            choices = [SKIP_OPTION] + [REGION_LABELS[r] for r in CANONICAL_REGIONS]
            for val in unique_vals:
                choice = st.selectbox(f"  '{val}' ->", choices, key=f"{prefix}region_map_{val}")
                if choice != SKIP_OPTION:
                    value_map[val] = [r for r in CANONICAL_REGIONS if REGION_LABELS[r] == choice][0]
        return {"column": True, "col": col, "map": value_map}
    label = st.selectbox("Region for every row", [REGION_LABELS[r] for r in CANONICAL_REGIONS],
                         key=f"{prefix}fixed_region")
    st.warning(f"This will apply region = '{label}' to ALL {df.shape[0]} rows.")
    return {"column": False, "value": [r for r in CANONICAL_REGIONS if REGION_LABELS[r] == label][0]}


def apply_region(work, spec, errors):
    if spec["column"]:
        if spec["col"] == NONE_OPTION:
            errors.append("Select a region column, or switch to a single fixed region.")
        else:
            work["_region"] = df[spec["col"]].astype(str).map(spec["map"])
    else:
        work["_region"] = spec["value"]


def show_and_offer_download(result, summary, total_label, partial_hint):
    st.header("5. Results")
    c1, c2, c3 = st.columns(3)
    c1.metric("Total rows", summary["n_total"])
    c2.metric(total_label, summary["n_ok"])
    c3.metric("Flagged / not calculated", summary["n_failed"])
    if summary["n_failed"] > 0:
        st.warning(
            f"{summary['n_failed']} of {summary['n_total']} rows could not be fully calculated. "
            f"They were left blank rather than estimated. {partial_hint}"
        )
        st.dataframe(
            pd.DataFrame(
                {"reason": list(summary["failure_reasons"].keys()),
                 "rows": list(summary["failure_reasons"].values())}
            ),
            width="stretch", hide_index=True,
        )
    st.dataframe(result, width="stretch")
    file_bytes, out_name, mime = to_download_bytes(result, uploaded.name, file_info)
    st.success(f"Your file is updated. Download '{out_name}' below.")
    if file_info["format"] == "xls":
        st.info("Legacy .xls cannot be written, so the updated file is saved as .xlsx.")
    st.download_button(
        "Download updated file", data=file_bytes, file_name=out_name, mime=mime,
        type="primary", on_click="ignore",
    )


# =============================================================================
# CT
# =============================================================================
if modality == MOD_CT:
    with st.expander("Methodology and limitations (read before use)", expanded=False):
        st.markdown(
            f"""
**Method:** effective dose (mSv) = `DLP (mGy*cm) x k`, where `k` depends on age and body region.

**Coefficient source (version `{TABLE_VERSION_ID}`):** {TABLE_CITATION}

**This is a population-reference approximation, not a patient-specific dose.** It reflects
ICRP Publication 60 (1990) tissue-weighting factors, consistent with most national Diagnostic
Reference Level programs. It does *not* reflect ICRP Publication 103 (2007) weighting, under
which coefficients for some regions (notably chest) are reported to be up to ~30% higher.

**Age binning:** reference ages 0, 1, 5, 10 and adult; adult cutoff 18 years.

**Missing or invalid data is never guessed.** Affected rows stay blank, with the reason in `dose_calc_status`.
            """
        )

    st.header("3. Map required fields")
    st.subheader("Dose Length Product (DLP, mGy*cm)")
    dlp_spec = dlp_ui("ct_")
    st.subheader("Patient age")
    age_spec = age_ui("ct_")
    st.subheader("Body region scanned")
    region_spec = region_ui("ct_")

    st.header("4. Run")
    if not st.button("Calculate effective dose", type="primary"):
        st.stop()

    errors, work = [], df.copy()
    apply_dlp(work, dlp_spec, errors)
    apply_age(work, age_spec, errors)
    apply_region(work, region_spec, errors)
    if errors:
        for message in errors:
            st.error(message)
        st.stop()

    result = calculate_effective_dose(work).drop(columns=["_dlp_mGycm", "_age_years", "_region"])
    show_and_offer_download(result, summarize(result), "Calculated", "See the reasons below.")


# =============================================================================
# Nuclear medicine (PET/CT and SPECT share this workflow)
# =============================================================================
else:
    if modality == MOD_PET:
        cfg = dict(
            prefix="pet_", registry=PET_REGISTRY, labels=PET_LABELS, calc=calculate_pet_ct_effective_dose,
            ct_default=True,
            ct_label="Include CT dose component (untick for PET-only, or when no CT dose data is available)",
            heading_note="PET/CT",
            extra_method=(
                "- **FDG** has an age table (ICRP 128; adult down to 1 year). **PSMA-11** is adult-only. "
                "A patient whose age has no tabulated coefficient is **flagged, not given the adult value**."
            ),
        )
    else:
        cfg = dict(
            prefix="spect_", registry=SPECT_REGISTRY, labels=SPECT_LABELS, calc=calculate_spect_effective_dose,
            ct_default=False,
            ct_label="Include CT dose component (tick for SPECT/CT when DLP data is available)",
            heading_note="SPECT",
            extra_method=(
                "- **Two coefficient sets** are used and recorded per row in `nm_coefficient_source`: "
                "`icrp128_via_nmp` (ICRP 128 age tables, via a secondary compilation) and `andersson2014` "
                "(adult-only, peer-reviewed recomputation with ICRP 103 weighting, *not* the official ICRP 128 "
                "number). Tracers with adult-only coefficients **flag patients under 18**.\n"
                "- **One row = one administration.** A rest + stress myocardial perfusion study is two rows."
            ),
        )
    prefix, registry, labels = cfg["prefix"], cfg["registry"], cfg["labels"]

    with st.expander("Methodology and limitations (read before use)", expanded=False):
        st.markdown(
            f"""
**Method:** total effective dose (mSv) = CT component + nuclear-medicine (NM) component.

- **CT component** (optional): `DLP x k`, same table as the CT calculator (`{TABLE_VERSION_ID}`).
- **NM component:** `injected activity (MBq) x tracer coefficient (mSv/MBq)`, from the age table of the tracer.
{cfg['extra_method']}
- Components and total are reported **separately**: if one part fails, the other is still shown and the total stays blank.
- Injected activities above {MAX_PLAUSIBLE_ACTIVITY_MBQ:.0f} MBq, zero or negative values are flagged as probable unit errors.
- Age binning: each patient takes the reference age at or **below** their age, which rounds a child's coefficient up (conservative).

**These are reference-person effective doses, not patient-specific absorbed doses**, and the tracer coefficients
assume normal biokinetics (e.g. normal renal function, standard voiding).
            """
        )
        for key, entry in registry.items():
            st.markdown(f"**{entry['label']}** (`{entry['source_id']}`): {entry['citation']}")
            if "note" in entry:
                st.caption(entry["note"])

    st.header("3. Map required fields")
    include_ct = st.checkbox(cfg["ct_label"], value=cfg["ct_default"], key=f"{prefix}include_ct")

    dlp_spec = region_spec = None
    if include_ct:
        st.subheader("CT: Dose Length Product (DLP, mGy*cm)")
        dlp_spec = dlp_ui(prefix)
        st.subheader("CT: Body region scanned")
        region_spec = region_ui(prefix)

    st.subheader("Patient age (used for both components)")
    age_spec = age_ui(prefix)

    st.subheader("Radiopharmaceutical")
    same_tracer = st.checkbox("Same radiopharmaceutical for every row in this file", value=True,
                              key=f"{prefix}same_tracer")
    tracer_key = tracer_col = None
    tracer_map = {}
    if same_tracer:
        label = st.selectbox("Radiopharmaceutical", list(labels.values()), key=f"{prefix}tracer")
        tracer_key = [k for k, v in labels.items() if v == label][0]
    else:
        tracer_col = st.selectbox("Column containing the radiopharmaceutical (values will be mapped)",
                                  [NONE_OPTION] + columns, key=f"{prefix}tracer_col")
        if tracer_col != NONE_OPTION:
            choices = [SKIP_OPTION] + list(labels.values())
            for val in sorted(df[tracer_col].dropna().astype(str).unique()):
                choice = st.selectbox(f"  '{val}' ->", choices, key=f"{prefix}tracer_map_{val}")
                if choice != SKIP_OPTION:
                    tracer_map[val] = [k for k, v in labels.items() if v == choice][0]

    st.subheader("Injected activity")
    unit = st.radio("Activity unit", ["MBq", "mCi"], horizontal=True, key=f"{prefix}unit")
    activity_from_column = st.radio(
        "How is injected activity provided?",
        ["A column in the file", "A single activity for every row in this file"],
        horizontal=True, key=f"{prefix}activity_mode",
    ) == "A column in the file"
    if activity_from_column:
        activity_col = st.selectbox("Column containing injected activity", [NONE_OPTION] + columns,
                                    key=f"{prefix}activity_col")
        fixed_activity = None
    else:
        activity_col = None
        fixed_activity = st.number_input(f"Activity ({unit}) to apply to every row", min_value=0.0,
                                         value=300.0, key=f"{prefix}fixed_activity")
        st.warning(f"This will apply activity = {fixed_activity} {unit} to ALL {df.shape[0]} rows.")

    st.header("4. Run")
    if not st.button("Calculate effective dose", type="primary", key=f"{prefix}run"):
        st.stop()

    errors, work = [], df.copy()
    if include_ct:
        apply_dlp(work, dlp_spec, errors)
        apply_region(work, region_spec, errors)
    apply_age(work, age_spec, errors)

    if same_tracer:
        work["_radiopharm"] = tracer_key
    elif tracer_col in (None, NONE_OPTION):
        errors.append("Select a radiopharmaceutical column, or switch to a single tracer for the whole file.")
    else:
        work["_radiopharm"] = df[tracer_col].astype(str).map(tracer_map)

    factor = MCI_TO_MBQ if unit == "mCi" else 1.0
    if activity_from_column:
        if activity_col == NONE_OPTION:
            errors.append("Select an activity column, or switch to a single fixed activity.")
        else:
            work["_activity_MBq"] = numeric_column(activity_col) * factor
    else:
        work["_activity_MBq"] = fixed_activity * factor

    if errors:
        for message in errors:
            st.error(message)
        st.stop()

    result = cfg["calc"](work, include_ct=include_ct)
    result = result.drop(columns=[c for c in INTERNAL_COLUMNS if c in result.columns])

    show_and_offer_download(
        result, summarize_nm(result), "Calculated (total)",
        "Check the per-component columns: one part may still be valid.",
    )
