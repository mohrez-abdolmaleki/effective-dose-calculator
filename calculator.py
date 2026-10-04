"""
Core CT effective-dose calculation.

Contract with the rest of the app:
  - Input: a pandas DataFrame that ALREADY has three standardized columns
    (produced by the column-mapping step in app.py, not here):
        "_dlp_mGycm"   : float or NaN
        "_age_years"   : float or NaN
        "_region"      : one of coefficients.CANONICAL_REGIONS, or NaN
  - Output: the ORIGINAL dataframe (all original columns preserved and
    untouched) with two new columns appended:
        "effective_dose_mSv" : float or blank (NaN) -- NEVER imputed
        "dose_calc_status"   : "ok" or a specific reason the row could not
                                be calculated (e.g. "missing: age")
  - Rule: a row that is missing anything required gets a blank dose and an
    explanatory status. It is never dropped, never filled with a mean/
    default, and never silently skipped. This is the "no action on missing
    data" behavior requested -- made explicit and auditable rather than
    implicit.
"""

import numpy as np
import pandas as pd

from coefficients import get_k_factor, TABLE_VERSION_ID
from pet_coefficients import get_nm_k_factor, RADIOPHARMACEUTICALS


REQUIRED_INTERNAL_COLUMNS = ["_dlp_mGycm", "_age_years", "_region"]
REQUIRED_PET_COLUMNS = ["_age_years", "_activity_MBq", "_radiopharm"]


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
    if age < 0 or age > 130:
        return np.nan, "invalid: age out of plausible range"

    result = get_k_factor(region=region, age_years=age)
    if not result.ok:
        return np.nan, f"invalid: {result.reason}"

    effective_dose = dlp * result.k
    return round(effective_dose, 4), "ok"


def calculate_effective_dose(df: pd.DataFrame) -> pd.DataFrame:
    """Vectorized-ish wrapper: adds effective_dose_mSv and dose_calc_status.

    Row-wise (not fully vectorized) because the missing-data and validity
    checks need to short-circuit per row with a specific reason -- clarity
    over micro-optimized speed here, since this runs on the scale of
    thousands of rows at most, not millions.
    """
    for col in REQUIRED_INTERNAL_COLUMNS:
        if col not in df.columns:
            raise ValueError(
                f"calculate_effective_dose expects a pre-mapped dataframe "
                f"with column '{col}'. Did you run the column-mapping step?"
            )

    doses = []
    statuses = []
    for _, row in df.iterrows():
        dose, status = _calc_one_row(row["_dlp_mGycm"], row["_age_years"], row["_region"])
        doses.append(dose)
        statuses.append(status)

    out = df.copy()
    out["effective_dose_mSv"] = doses
    out["dose_calc_status"] = statuses
    out["coefficient_table_version"] = TABLE_VERSION_ID
    return out


def _calc_ct_component(dlp, age, region):
    """Same logic as _calc_one_row, factored out so the PET/CT path can
    reuse it for the CT portion without duplicating the validation rules.
    """
    return _calc_one_row(dlp, age, region)


def _calc_nm_component(age, activity, radiopharm):
    missing = []
    if pd.isna(activity):
        missing.append("activity")
    if pd.isna(radiopharm) or radiopharm == "":
        missing.append("radiopharmaceutical")
    if missing:
        return np.nan, "missing: " + ", ".join(missing)

    if activity < 0:
        return np.nan, "invalid: activity is negative"

    entry = RADIOPHARMACEUTICALS.get(radiopharm)
    if entry is not None and entry["age_dependent"] and pd.isna(age):
        return np.nan, "missing: age (required for this radiopharmaceutical)"
    if not pd.isna(age) and (age < 0 or age > 130):
        return np.nan, "invalid: age out of plausible range"

    result = get_nm_k_factor(radiopharm, age if not pd.isna(age) else None)
    if not result.ok:
        return np.nan, f"invalid: {result.reason}"

    return round(activity * result.k, 4), "ok"


def calculate_pet_ct_effective_dose(df: pd.DataFrame, include_ct: bool) -> pd.DataFrame:
    """PET/CT effective dose = CT component (DLP x k) + NM component
    (activity x radiopharmaceutical coefficient).

    Unlike calculate_effective_dose, this reports each component's value
    and status SEPARATELY, plus a combined total. This is deliberate: if
    only one component can be calculated for a given row, the user should
    still see that partial result and know exactly why the total is
    incomplete, rather than getting a single blank cell with no
    diagnostic information.

    If include_ct is False, the CT component is skipped entirely (e.g. for
    PET-only acquisitions with no diagnostic CT) and total == NM component.
    """
    for col in REQUIRED_PET_COLUMNS:
        if col not in df.columns:
            raise ValueError(f"calculate_pet_ct_effective_dose expects column '{col}'")
    if include_ct:
        for col in ["_dlp_mGycm", "_region"]:
            if col not in df.columns:
                raise ValueError(f"calculate_pet_ct_effective_dose (include_ct=True) expects column '{col}'")

    ct_doses, ct_statuses = [], []
    nm_doses, nm_statuses = [], []
    total_doses, total_statuses = [], []

    for _, row in df.iterrows():
        age = row["_age_years"]

        if include_ct:
            ct_dose, ct_status = _calc_ct_component(row["_dlp_mGycm"], age, row["_region"])
        else:
            ct_dose, ct_status = np.nan, "not included"
        ct_doses.append(ct_dose)
        ct_statuses.append(ct_status)

        nm_dose, nm_status = _calc_nm_component(age, row["_activity_MBq"], row["_radiopharm"])
        nm_doses.append(nm_dose)
        nm_statuses.append(nm_status)

        ct_ok = (ct_status == "ok") or (not include_ct)
        nm_ok = (nm_status == "ok")
        if ct_ok and nm_ok:
            ct_part = ct_dose if include_ct else 0.0
            total_doses.append(round(ct_part + nm_dose, 4))
            total_statuses.append("ok")
        else:
            total_doses.append(np.nan)
            reasons = []
            if include_ct and not ct_ok:
                reasons.append(f"CT: {ct_status}")
            if not nm_ok:
                reasons.append(f"NM: {nm_status}")
            total_statuses.append("incomplete -- " + "; ".join(reasons))

    out = df.copy()
    out["ct_effective_dose_mSv"] = ct_doses
    out["ct_dose_status"] = ct_statuses
    out["nm_effective_dose_mSv"] = nm_doses
    out["nm_dose_status"] = nm_statuses
    out["total_effective_dose_mSv"] = total_doses
    out["total_dose_status"] = total_statuses
    out["ct_coefficient_table_version"] = TABLE_VERSION_ID if include_ct else "n/a"
    return out


def summarize_pet(df: pd.DataFrame) -> dict:
    n_total = len(df)
    n_ok = int((df["total_dose_status"] == "ok").sum())
    n_failed = n_total - n_ok
    failure_reasons = (
        df.loc[df["total_dose_status"] != "ok", "total_dose_status"]
        .value_counts()
        .to_dict()
    )
    return {
        "n_total": n_total, "n_ok": n_ok, "n_failed": n_failed,
        "failure_reasons": failure_reasons,
    }


def summarize(df: pd.DataFrame) -> dict:
    """Small audit summary for the confirmation message / sidebar."""
    n_total = len(df)
    n_ok = int((df["dose_calc_status"] == "ok").sum())
    n_failed = n_total - n_ok
    failure_reasons = (
        df.loc[df["dose_calc_status"] != "ok", "dose_calc_status"]
        .value_counts()
        .to_dict()
    )
    return {
        "n_total": n_total,
        "n_ok": n_ok,
        "n_failed": n_failed,
        "failure_reasons": failure_reasons,
    }
