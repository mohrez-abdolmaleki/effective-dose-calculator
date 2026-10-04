"""
Effective dose coefficients (mSv/MBq) for PET radiopharmaceuticals.

Same design principle as coefficients.py: data, not logic, each entry
independently cited, nothing interpolated or guessed beyond what's
explicitly documented below.

IMPORTANT ASYMMETRY vs. the CT table: unlike CT (one coefficient table,
EUR16262/AAPM96, used for all regions), radiopharmaceutical dose
coefficients come from DIFFERENT KINDS of primary sources with different
reliability:

  - F-18 FDG: ICRP Publication 128 gives a single, widely-reproduced adult
    coefficient (0.019 mSv/MBq) cross-confirmed across many independent
    papers. ICRP 128 does contain pediatric biokinetic data, but a clean
    per-age mSv/MBq summary table was not available to use as a primary
    source for this project at the time of writing -- rather than
    back-calculate one from example effective-dose/activity pairs in a
    secondary source (which would quietly introduce rounding and
    weight-assumption artifacts of my own making), pediatric FDG is left
    UNSUPPORTED in this version. See age_dependent=False below.

  - Ga-68-DOTATATE: the NETSPOT (Advanced Accelerator Applications /
    Novartis) FDA prescribing information gives a full age-banded table
    (newborn/1y/5y/10y/15y/adult) directly as mSv/MBq -- this is used
    as-is, full age dependence supported.

  - Ga-68-PSMA-11: NOT a single-manufacturer, single-label situation --
    multiple approved products (e.g. Illuccix/gozetotide) and many
    independent dosimetry papers report adult effective dose coefficients
    ranging from about 0.017 to 0.026 mSv/MBq depending on method and
    cohort. There is no pediatric indication (prostate cancer), so no
    pediatric coefficient is needed. The FDA package-insert value is used
    as the default, but this is a genuinely less-settled number than FDG
    or DOTATATE -- say so in any output that uses it.

Do not add a radiopharmaceutical to this file without a specific,
checkable citation for the number you enter.
"""

from dataclasses import dataclass
from typing import Optional

# Age bin thresholds for the radiopharmaceuticals that DO have an age-banded
# table (currently only Ga68_DOTATATE). Six bins (vs. five for CT) because
# the NETSPOT label itself reports a "15 years" reference point that the
# CT table does not have -- this is NOT the same binning function as
# coefficients.age_to_bin, and deliberately kept separate rather than
# forced to share code, since conflating two different source tables'
# bin structures would misrepresent both.
NM_AGE_BIN_ADULT_CUTOFF = 18


def nm_age_to_bin(age_years: Optional[float]) -> Optional[str]:
    if age_years is None or age_years < 0:
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


RADIOPHARMACEUTICALS = {
    "F18_FDG": {
        "label": "[18F]FDG",
        "age_dependent": False,
        "adult_k_mSv_per_MBq": 0.019,
        "citation": (
            "ICRP Publication 128 (2015), International Commission on "
            "Radiological Protection: Radiation Dose to Patients from "
            "Radiopharmaceuticals. Adult effective dose coefficient for "
            "2-[18F]FDG = 0.019 mSv/MBq, cross-confirmed in multiple "
            "independent clinical dosimetry studies."
        ),
        "note": "Pediatric coefficients not implemented in this version -- see module docstring.",
    },
    "Ga68_DOTATATE": {
        "label": "68Ga-DOTATATE",
        "age_dependent": True,
        "age_table_mSv_per_MBq": {
            "0": 0.35, "1": 0.13, "5": 0.064, "10": 0.04, "15": 0.025, "adult": 0.021,
        },
        "citation": (
            "NETSPOT (kit for the preparation of gallium Ga 68 dotatate "
            "injection), FDA full prescribing information, Table 4 "
            "(Estimated Radiation Effective Dose per Injection Activity). "
            "Advanced Accelerator Applications USA, Inc. / Novartis AG, "
            "revised 10/2023."
        ),
    },
    "Ga68_PSMA11": {
        "label": "68Ga-PSMA-11",
        "age_dependent": False,
        "adult_k_mSv_per_MBq": 0.0169,
        "citation": (
            "FDA prescribing information for gallium Ga 68 gozetotide "
            "injection (e.g. Illuccix), Radiation Dosimetry section, "
            "adult effective dose per administered activity."
        ),
        "note": (
            "Less settled than FDG or DOTATATE: independent dosimetry "
            "studies report adult values from ~0.017 to ~0.026 mSv/MBq "
            "(e.g. Afshar-Oromieh et al. 2016: 0.023; Sandstrom-style "
            "cohort studies: up to 0.026). No pediatric indication exists "
            "for this tracer (prostate cancer)."
        ),
    },
}

RADIOPHARM_LABELS = {k: v["label"] for k, v in RADIOPHARMACEUTICALS.items()}


@dataclass
class NMKFactorResult:
    k: Optional[float]
    age_bin_used: Optional[str]
    ok: bool
    reason: Optional[str] = None


def get_nm_k_factor(radiopharm_key: str, age_years: Optional[float]) -> NMKFactorResult:
    """Look up the effective dose coefficient (mSv/MBq) for a radiopharmaceutical.

    Never guesses: unsupported tracer, or (for age-dependent tracers)
    missing/invalid age, returns ok=False with a specific reason.
    """
    if radiopharm_key not in RADIOPHARMACEUTICALS:
        return NMKFactorResult(
            k=None, age_bin_used=None, ok=False,
            reason=f"unsupported radiopharmaceutical '{radiopharm_key}'",
        )

    entry = RADIOPHARMACEUTICALS[radiopharm_key]

    if not entry["age_dependent"]:
        return NMKFactorResult(k=entry["adult_k_mSv_per_MBq"], age_bin_used="adult (fixed)", ok=True)

    age_bin = nm_age_to_bin(age_years)
    if age_bin is None:
        return NMKFactorResult(
            k=None, age_bin_used=None, ok=False,
            reason=f"missing or invalid age (required for age-dependent tracer {entry['label']})",
        )

    k = entry["age_table_mSv_per_MBq"][age_bin]
    return NMKFactorResult(k=k, age_bin_used=age_bin, ok=True)
