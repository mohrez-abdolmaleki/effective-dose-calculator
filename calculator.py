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


REQUIRED_INTERNAL_COLUMNS = ["_dlp_mGycm", "_age_years", "_region"]


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
