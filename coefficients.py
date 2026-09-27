"""
DLP -> Effective Dose conversion coefficients for CT.

Design principle: coefficient tables are DATA, not logic. Each table is
versioned and carries its own citation so that (a) two tables are never
silently mixed within one calculation run, and (b) adding a new table later
(e.g. an ICRP 103-based one) is a data addition, not a code change.

CURRENT DEFAULT TABLE: "eur16262_aapm96"
------------------------------------------
Age-and-region-dependent k (mSv per mGy*cm), based on ICRP Publication 60
(1990) tissue-weighting factors. This is the table lineage of the European
Commission's 1999 quality-criteria report (EUR 16262) as reproduced in
AAPM Report No. 96 (McCollough et al., 2008), and is the table most widely
embedded in national Diagnostic Reference Level programs and IAEA guidance.

KNOWN LIMITATION (do not remove this comment): ICRP updated tissue-weighting
factors in Publication 103 (2007). Coefficients derived from ICRP 103
(e.g. Shrimpton et al. 2010, Deak et al. 2010, or newer empirical tables)
differ from this table by up to ~30% for some regions (notably chest).
This table reflects regulatory precedent, not the most current radiobiological
consensus. If/when an ICRP 103-based table is added, both tables should
remain independently selectable and clearly labeled in all outputs.

Age binning policy (an explicit implementation choice, not part of the
source table, which only defines five discrete reference ages):
    age <  1               -> "0"      (neonate/infant reference point)
    1  <= age <  5          -> "1"
    5  <= age <  10          -> "5"
    10 <= age <  18          -> "10"
    age >= 18 (or age is None with explicit "adult" flag) -> "adult"
This 18-year adult cutoff matches the ICRP reference-person convention.
A different cutoff (e.g. 15y, used by some national programs) is a
legitimate alternative choice -- it is centralized here in ONE place
(AGE_BIN_ADULT_CUTOFF) specifically so it can be changed without touching
calculation logic.
"""

from dataclasses import dataclass
from typing import Optional


AGE_BIN_ADULT_CUTOFF = 18  # years; see docstring above

# k in mSv / (mGy*cm)
EUR16262_AAPM96_TABLE = {
    "head_and_neck":      {"0": 0.013, "1": 0.0085, "5": 0.0057, "10": 0.0042, "adult": 0.0031},
    "head":                {"0": 0.011, "1": 0.0067, "5": 0.0040, "10": 0.0032, "adult": 0.0021},
    "neck":                {"0": 0.017, "1": 0.012,  "5": 0.011,  "10": 0.0079, "adult": 0.0059},
    "chest":               {"0": 0.039, "1": 0.026,  "5": 0.018,  "10": 0.013,  "adult": 0.014},
    "abdomen_and_pelvis":  {"0": 0.049, "1": 0.030,  "5": 0.020,  "10": 0.015,  "adult": 0.015},
    "trunk":               {"0": 0.044, "1": 0.028,  "5": 0.019,  "10": 0.014,  "adult": 0.015},
}

TABLE_CITATION = (
    "European Commission (1999). European Guidelines on Quality Criteria for "
    "Computed Tomography, Report EUR 16262. As reproduced in: McCollough CH "
    "et al., AAPM Report No. 96: The Measurement, Reporting, and Management "
    "of Radiation Dose in CT (2008). Coefficients reflect ICRP Publication 60 "
    "(1990) tissue-weighting factors."
)

TABLE_VERSION_ID = "eur16262_aapm96_icrp60_v1"

CANONICAL_REGIONS = list(EUR16262_AAPM96_TABLE.keys())

# Human-readable labels for the Streamlit UI dropdown
REGION_LABELS = {
    "head_and_neck": "Head and Neck",
    "head": "Head",
    "neck": "Neck",
    "chest": "Chest",
    "abdomen_and_pelvis": "Abdomen and Pelvis",
    "trunk": "Trunk (chest + abdomen + pelvis, combined acquisition)",
}


@dataclass
class KFactorResult:
    k: Optional[float]
    age_bin_used: Optional[str]
    table_version: str
    ok: bool
    reason: Optional[str] = None  # populated when ok is False


def age_to_bin(age_years: Optional[float]) -> Optional[str]:
    """Map a continuous age (years) to one of the table's five reference bins.

    Returns None if age_years is None or negative (caller must treat this as
    missing/invalid data -- NOT silently defaulted to adult or any other bin).
    """
    if age_years is None:
        return None
    if age_years < 0:
        return None
    if age_years < 1:
        return "0"
    if age_years < 5:
        return "1"
    if age_years < 10:
        return "5"
    if age_years < AGE_BIN_ADULT_CUTOFF:
        return "10"
    return "adult"


def get_k_factor(region: str, age_years: Optional[float]) -> KFactorResult:
    """Look up k (mSv / mGy*cm) for a canonical region + age.

    This function NEVER guesses. If the region is not in the table, or age
    is missing/invalid, it returns ok=False with a specific reason string --
    the caller is responsible for surfacing that as a per-row flag, not for
    substituting a default value.
    """
    if region not in EUR16262_AAPM96_TABLE:
        return KFactorResult(
            k=None, age_bin_used=None, table_version=TABLE_VERSION_ID,
            ok=False,
            reason=f"unsupported region '{region}' (supported: {CANONICAL_REGIONS})",
        )

    age_bin = age_to_bin(age_years)
    if age_bin is None:
        return KFactorResult(
            k=None, age_bin_used=None, table_version=TABLE_VERSION_ID,
            ok=False, reason="missing or invalid age",
        )

    k = EUR16262_AAPM96_TABLE[region][age_bin]
    return KFactorResult(
        k=k, age_bin_used=age_bin, table_version=TABLE_VERSION_ID, ok=True,
    )
