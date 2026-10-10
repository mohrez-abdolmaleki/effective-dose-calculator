"""
Effective dose coefficients (mSv/MBq) for PET radiopharmaceuticals.

Data, not logic: each entry carries its own age table, source id and
citation. Lookup rules live in radiopharm_core.py (shared with SPECT).

CHANGE vs. the first PET/CT version: the earlier version used the single
adult coefficient for every age for FDG and PSMA-11. For a child that is a
silent guess, which contradicts the project's missing-data rule. Now:
  - FDG has an age table (ICRP 128, adult to 1 year); newborns (<1 y) are
    flagged, not defaulted.
  - PSMA-11 is adult-only (no pediatric indication, no pediatric
    coefficient); a patient under 18 is flagged, not defaulted.
  - Age is therefore required for every tracer.

Source ids:
  icrp128_via_nmp     ICRP Publication 128 values as transcribed in the
                      Nihon Medi-Physics "ICRP data" compilation (a
                      SECONDARY compilation; adult/15/10/5/1 y only).
  netspot_fda_2023    NETSPOT FDA prescribing information, Table 4.
  fda_gozetotide      FDA label for Ga-68 gozetotide (PSMA-11), adult.
"""

from radiopharm_core import lookup_k, nm_age_to_bin, NM_AGE_BIN_ADULT_CUTOFF, NMKFactorResult  # noqa: F401

RADIOPHARMACEUTICALS = {
    "F18_FDG": {
        "label": "[18F]FDG",
        "source_id": "icrp128_via_nmp",
        "age_table_mSv_per_MBq": {
            "adult": 0.019, "15": 0.024, "10": 0.037, "5": 0.056, "1": 0.095,
        },
        "citation": (
            "ICRP Publication 128 (2015), Radiation Dose to Patients from "
            "Radiopharmaceuticals. Age table transcribed from the Nihon "
            "Medi-Physics ICRP-data compilation (secondary source; verify "
            "against the ICRP 128 Annex before regulatory use). The adult "
            "value 0.019 mSv/MBq is independently cross-confirmed in many "
            "clinical dosimetry papers."
        ),
        "note": "No newborn (<1 y) coefficient in the source table: such rows are flagged, not defaulted.",
    },
    "Ga68_DOTATATE": {
        "label": "68Ga-DOTATATE",
        "source_id": "netspot_fda_2023",
        "age_table_mSv_per_MBq": {
            "0": 0.35, "1": 0.13, "5": 0.064, "10": 0.04, "15": 0.025, "adult": 0.021,
        },
        "citation": (
            "NETSPOT (kit for the preparation of gallium Ga 68 dotatate "
            "injection), FDA full prescribing information, Table 4 "
            "(effective dose per injected activity), Advanced Accelerator "
            "Applications USA / Novartis, revised 10/2023."
        ),
    },
    "Ga68_PSMA11": {
        "label": "68Ga-PSMA-11",
        "source_id": "fda_gozetotide",
        "age_table_mSv_per_MBq": {"adult": 0.0169},
        "citation": (
            "FDA prescribing information for gallium Ga 68 gozetotide "
            "injection (e.g. Illuccix), Radiation Dosimetry section, adult "
            "effective dose per administered activity."
        ),
        "note": (
            "Least settled number in the tool: independent studies report "
            "adult values from about 0.017 to 0.026 mSv/MBq. Adult-only: "
            "patients under 18 are flagged (no pediatric indication)."
        ),
    },
}

RADIOPHARM_LABELS = {k: v["label"] for k, v in RADIOPHARMACEUTICALS.items()}


def get_nm_k_factor(radiopharm_key: str, age_years):
    """PET tracer lookup (thin wrapper over the shared lookup)."""
    return lookup_k(RADIOPHARMACEUTICALS, radiopharm_key, age_years)
