"""
Core effective-dose calculations: CT, PET/CT and SPECT(/CT).

Contract with the rest of the app:
  - Inputs are DataFrames that ALREADY carry standardized internal columns
    (produced by the column-mapping step in app.py, not here):
        "_dlp_mGycm"    float or NaN        (CT component)
        "_age_years"    float or NaN
        "_region"       canonical CT region or NaN   (CT component)
        "_activity_MBq" float or NaN        (nuclear-medicine component)
        "_radiopharm"   registry key or NaN (nuclear-medicine component)
  - Outputs are the ORIGINAL dataframe, every original column untouched,
    plus new result columns.
  - Rule: a row missing anything required, or holding an implausible value,
    gets a blank dose and a specific reason. It is never dropped, imputed or
    silently defaulted.
"""

import numpy as np
import pandas as pd

from coefficients import get_k_factor, TABLE_VERSION_ID
from radiopharm_core import lookup_k
from pet_coefficients import RADIOPHARMACEUTICALS as PET_REGISTRY
from spect_coefficients import SPECT_RADIOPHARMACEUTICALS as SPECT_REGISTRY


REQUIRED_INTERNAL_COLUMNS = ["_dlp_mGycm", "_age_years", "_region"]
REQUIRED_NM_COLUMNS = ["_age_years", "_activity_MBq", "_radiopharm"]

# Injected activities above this are almost certainly a unit error (kBq or
# uCi entered as MBq), not a real administration. Diagnostic PET/SPECT
# activities are all well below this. Flagged, never "corrected".
MAX_PLAUSIBLE_ACTIVITY_MBQ = 3000.0
MAX_PLAUSIBLE_AGE_YEARS = 130.0

# Names of the columns this module adds. The app refuses to run if the user's
# file already contains any of them (they would be silently overwritten).
CT_OUTPUT_COLUMNS = ["effective_dose_mSv", "dose_calc_status", "coefficient_table_version"]
NM_OUTPUT_COLUMNS = [
    "ct_effective_dose_mSv", "ct_dose_status",
    "nm_effective_dose_mSv", "nm_dose_status",
    "nm_coefficient_mSv_per_MBq", "nm_age_bin_used", "nm_coefficient_source",
    "total_effective_dose_mSv", "total_dose_status", "ct_coefficient_table_version",
]
INTERNAL_COLUMNS = ["_dlp_mGycm", "_age_years", "_region", "_activity_MBq", "_radiopharm"]


# =============================================================================
# CT
# =============================================================================
def _calc_one_row(dlp, age, region):
    """Returns (effective_dose_or_nan, status_string)."""
    missing = []
    if pd.isna(dlp):
        missing.append("DLP")
    if pd.isna(age):
        missing.append("age")
    if pd.isna(region) or region == "":
        missing.append("body region")
    if missing:
        return np.nan, "missing: " + ", ".join(missing)

    if dlp < 0:
        return np.nan, "invalid: DLP is negative"
    if age < 0 or age > MAX_PLAUSIBLE_AGE_YEARS:
        return np.nan, "invalid: age out of plausible range"

    result = get_k_factor(region=region, age_years=age)
    if not result.ok:
        return np.nan, f"invalid: {result.reason}"

    return round(dlp * result.k, 4), "ok"


def calculate_effective_dose(df: pd.DataFrame) -> pd.DataFrame:
    """CT only: adds effective_dose_mSv, dose_calc_status, coefficient_table_version."""
    for col in REQUIRED_INTERNAL_COLUMNS:
        if col not in df.columns:
            raise ValueError(
                f"calculate_effective_dose expects a pre-mapped dataframe "
                f"with column '{col}'. Did you run the column-mapping step?"
            )

    doses, statuses = [], []
    for _, row in df.iterrows():
        dose, status = _calc_one_row(row["_dlp_mGycm"], row["_age_years"], row["_region"])
        doses.append(dose)
        statuses.append(status)

    out = df.copy()
    out["effective_dose_mSv"] = doses
    out["dose_calc_status"] = statuses
    out["coefficient_table_version"] = TABLE_VERSION_ID
    return out


def summarize(df: pd.DataFrame) -> dict:
    """Audit summary for CT-only results."""
    return _summarize_status_column(df, "dose_calc_status")


# =============================================================================
# Nuclear-medicine component (shared by PET and SPECT)
# =============================================================================
def _calc_nm_component(age, activity, radiopharm, registry):
    """Returns (dose, status, k, age_bin, source_id) for one row."""
    missing = []
    if pd.isna(activity):
        missing.append("activity")
    if pd.isna(radiopharm) or radiopharm == "":
        missing.append("radiopharmaceutical")
    if pd.isna(age):
        missing.append("age")
    if missing:
        return np.nan, "missing: " + ", ".join(missing), np.nan, None, None

    if activity <= 0:
        return np.nan, "invalid: activity is zero or negative", np.nan, None, None
    if activity > MAX_PLAUSIBLE_ACTIVITY_MBQ:
        return (np.nan,
                f"invalid: activity above {MAX_PLAUSIBLE_ACTIVITY_MBQ:.0f} MBq (check units)",
                np.nan, None, None)
    if age < 0 or age > MAX_PLAUSIBLE_AGE_YEARS:
        return np.nan, "invalid: age out of plausible range", np.nan, None, None

    result = lookup_k(registry, radiopharm, age)
    if not result.ok:
        return np.nan, f"not calculated: {result.reason}", np.nan, result.age_bin_used, result.source_id

    return round(activity * result.k, 4), "ok", result.k, result.age_bin_used, result.source_id


def calculate_nm_effective_dose(df: pd.DataFrame, include_ct: bool, registry: dict) -> pd.DataFrame:
    """Hybrid-imaging effective dose = CT component + nuclear-medicine component.

    CT component:  DLP x k (same table as the CT calculator), optional.
    NM component:  injected activity x tracer coefficient from `registry`.

    The two components and the total are reported SEPARATELY, so that a row
    where only one part can be calculated still shows that part and the
    reason the total is blank, rather than one unexplained empty cell.
    With include_ct=False (e.g. a planar study, or SPECT without CT) the
    total equals the NM component.

    Audit columns record the coefficient, the age bin and the coefficient
    source actually used for each row.
    """
    for col in REQUIRED_NM_COLUMNS:
        if col not in df.columns:
            raise ValueError(f"expected column '{col}' (did you run the column-mapping step?)")
    if include_ct:
        for col in ["_dlp_mGycm", "_region"]:
            if col not in df.columns:
                raise ValueError(f"include_ct=True expects column '{col}'")

    cols = {name: [] for name in [
        "ct_dose", "ct_status", "nm_dose", "nm_status", "nm_k", "nm_bin", "nm_source",
        "total_dose", "total_status",
    ]}

    for _, row in df.iterrows():
        age = row["_age_years"]

        if include_ct:
            ct_dose, ct_status = _calc_one_row(row["_dlp_mGycm"], age, row["_region"])
        else:
            ct_dose, ct_status = np.nan, "not included"

        nm_dose, nm_status, k, age_bin, source = _calc_nm_component(
            age, row["_activity_MBq"], row["_radiopharm"], registry
        )

        ct_ok = (ct_status == "ok") or (not include_ct)
        nm_ok = nm_status == "ok"
        if ct_ok and nm_ok:
            total = round((ct_dose if include_ct else 0.0) + nm_dose, 4)
            total_status = "ok"
        else:
            total = np.nan
            reasons = []
            if include_ct and not ct_ok:
                reasons.append(f"CT: {ct_status}")
            if not nm_ok:
                reasons.append(f"NM: {nm_status}")
            total_status = "incomplete -- " + "; ".join(reasons)

        for name, value in zip(cols, [ct_dose, ct_status, nm_dose, nm_status, k, age_bin,
                                       source, total, total_status]):
            cols[name].append(value)

    out = df.copy()
    out["ct_effective_dose_mSv"] = cols["ct_dose"]
    out["ct_dose_status"] = cols["ct_status"]
    out["nm_effective_dose_mSv"] = cols["nm_dose"]
    out["nm_dose_status"] = cols["nm_status"]
    out["nm_coefficient_mSv_per_MBq"] = cols["nm_k"]
    out["nm_age_bin_used"] = cols["nm_bin"]
    out["nm_coefficient_source"] = cols["nm_source"]
    out["total_effective_dose_mSv"] = cols["total_dose"]
    out["total_dose_status"] = cols["total_status"]
    out["ct_coefficient_table_version"] = TABLE_VERSION_ID if include_ct else "n/a"
    return out


def calculate_pet_ct_effective_dose(df: pd.DataFrame, include_ct: bool) -> pd.DataFrame:
    return calculate_nm_effective_dose(df, include_ct, PET_REGISTRY)


def calculate_spect_effective_dose(df: pd.DataFrame, include_ct: bool) -> pd.DataFrame:
    return calculate_nm_effective_dose(df, include_ct, SPECT_REGISTRY)


def summarize_nm(df: pd.DataFrame) -> dict:
    """Audit summary for PET/CT and SPECT results."""
    return _summarize_status_column(df, "total_dose_status")


summarize_pet = summarize_nm  # backwards-compatible name


def _summarize_status_column(df: pd.DataFrame, status_col: str) -> dict:
    n_total = len(df)
    n_ok = int((df[status_col] == "ok").sum())
    failure_reasons = (
        df.loc[df[status_col] != "ok", status_col].value_counts().to_dict()
    )
    return {
        "n_total": n_total,
        "n_ok": n_ok,
        "n_failed": n_total - n_ok,
        "failure_reasons": failure_reasons,
    }
