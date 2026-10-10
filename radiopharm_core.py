"""
Shared lookup logic for radiopharmaceutical effective-dose coefficients
(used by both the PET/CT and the SPECT calculators).

Every tracer is described by an AGE TABLE: a dict mapping a reference-age
bin to an effective dose coefficient in mSv/MBq. A tracer that only has an
adult value simply has {"adult": value}. There is deliberately no
"fall back to the adult value" path: if a patient's age bin has no entry in
the tracer's table, the row is flagged and left blank. This is the same
"never guess" rule as the CT calculator.

Age binning (an implementation choice, centralized here):
    age <  1   -> "0"   (newborn / 3-month reference)
    1  <= age < 5   -> "1"
    5  <= age < 10  -> "5"
    10 <= age < 15  -> "10"
    15 <= age < 18  -> "15"
    age >= 18       -> "adult"
Each patient is assigned to the reference age at or BELOW their age.
Because dose coefficients fall with increasing age, this convention rounds
a child's coefficient UP (conservative), never down. A "nearest reference
age" convention is a legitimate alternative; changing it is a one-function
edit (nm_age_to_bin).
"""

from dataclasses import dataclass
from typing import Optional

NM_AGE_BIN_ADULT_CUTOFF = 18

BIN_DESCRIPTIONS = {
    "0": "<1 y",
    "1": "1 to <5 y",
    "5": "5 to <10 y",
    "10": "10 to <15 y",
    "15": "15 to <18 y",
    "adult": ">=18 y",
}


def nm_age_to_bin(age_years: Optional[float]) -> Optional[str]:
    """Map a continuous age to a reference-age bin; None if missing/invalid.

    NaN is handled explicitly: comparisons with NaN are all False, so
    without this check a missing age would silently fall through to
    "adult".
    """
    if age_years is None or age_years != age_years:  # None or NaN
        return None
    if age_years < 0:
        return None
    if age_years < 1:
        return "0"
    if age_years < 5:
        return "1"
    if age_years < 10:
        return "5"
    if age_years < 15:
        return "10"
    if age_years < NM_AGE_BIN_ADULT_CUTOFF:
        return "15"
    return "adult"


@dataclass
class NMKFactorResult:
    k: Optional[float]
    age_bin_used: Optional[str]
    source_id: Optional[str]
    ok: bool
    reason: Optional[str] = None


def lookup_k(registry: dict, key: str, age_years: Optional[float]) -> NMKFactorResult:
    """Look up the effective dose coefficient (mSv/MBq) in `registry`.

    Never guesses: unknown tracer, missing/invalid age, or an age bin with
    no tabulated coefficient all return ok=False with a specific reason.
    """
    if key not in registry:
        return NMKFactorResult(None, None, None, False, f"unsupported radiopharmaceutical '{key}'")

    entry = registry[key]
    age_bin = nm_age_to_bin(age_years)
    if age_bin is None:
        return NMKFactorResult(
            None, None, entry["source_id"], False,
            f"missing or invalid age (required for {entry['label']})",
        )

    table = entry["age_table_mSv_per_MBq"]
    if age_bin not in table:
        available = ", ".join(BIN_DESCRIPTIONS[b] for b in table)
        return NMKFactorResult(
            None, age_bin, entry["source_id"], False,
            f"no coefficient for age {BIN_DESCRIPTIONS[age_bin]} for {entry['label']} "
            f"(tabulated: {available})",
        )

    return NMKFactorResult(table[age_bin], age_bin, entry["source_id"], True)
