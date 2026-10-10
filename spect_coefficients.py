"""
Effective dose coefficients (mSv/MBq) for SPECT / planar scintigraphy
radiopharmaceuticals.

Data, not logic. Lookup rules (age bins, never-guess behaviour) are in
radiopharm_core.py, shared with PET.

TWO SOURCE SETS, kept distinct on purpose (every output row records which
one produced its coefficient, in `nm_coefficient_source`):

  icrp128_via_nmp   ICRP Publication 128 (2015) values, with age tables
                    (adult, 15, 10, 5, 1 y), as transcribed in the Nihon
                    Medi-Physics "ICRP data" compilation. This is a
                    SECONDARY compilation of ICRP values; two independent
                    extractions of it agreed digit-for-digit, but it has
                    not been checked against the ICRP 128 Annex itself.

  andersson2014     Andersson M, Johansson L, Eckerman K, Mattsson S.
                    EJNMMI Phys 2014;1:9 (doi 10.1186/2197-7364-1-9),
                    Table 1, column E3: adult effective dose computed with
                    ICRP/ICRU reference phantoms and ICRP 103 tissue
                    weighting (sex-averaged). ADULT ONLY. These are a
                    peer-reviewed recomputation, NOT the official ICRP 128
                    numbers, and can differ from them by tens of percent
                    for the same agent (e.g. FDG: 0.0159 here vs 0.019 in
                    ICRP 128). Used only where no age-banded ICRP 128 value
                    was obtainable.

Why two sets rather than one: the ICRP 128 Annex (the primary source) could
not be retrieved in this session. Rather than invent values, the tracers
with an obtainable ICRP 128 age table use it; the remaining common tracers
are included as adult-only entries from andersson2014 and clearly labelled.
Replace those entries with ICRP 128 Annex values when you have the report
in hand -- it is a data edit in this file only.

Deliberately NOT included (state-dependent, no single coefficient):
iodide (depends on thyroid uptake), and any tracer without a value in
hand. Tl-201 is adult-only: the source's pediatric row has an implausible
15 y -> 10 y jump (0.20 -> 0.56 mSv/MBq) that should be checked against
ICRP 128 before use.

One row = one administration. A rest + stress myocardial perfusion study
is two administrations and therefore two rows (or run the file twice).
"""

from radiopharm_core import lookup_k

ICRP128 = "icrp128_via_nmp"
ANDERSSON = "andersson2014"

_CIT_ICRP128 = (
    "ICRP Publication 128 (2015), Radiation Dose to Patients from "
    "Radiopharmaceuticals; age table via the Nihon Medi-Physics ICRP-data "
    "compilation (secondary source)."
)
_CIT_ANDERSSON = (
    "Andersson M et al., EJNMMI Phys 2014;1:9, Table 1 column E3 (ICRP 103 "
    "weighting, ICRP/ICRU phantoms, sex-averaged adult). Adult only; not the "
    "official ICRP 128 value."
)


def _age_table(adult, a15, a10, a5, a1):
    return {"adult": adult, "15": a15, "10": a10, "5": a5, "1": a1}


SPECT_RADIOPHARMACEUTICALS = {
    # ---- ICRP 128 with age tables (via compilation) -------------------------
    "Tc99m_phosphonates": {
        "label": "99mTc-MDP/HDP (phosphonates, normal uptake)",
        "source_id": ICRP128,
        "age_table_mSv_per_MBq": _age_table(4.9e-3, 5.7e-3, 8.6e-3, 1.2e-2, 1.8e-2),
        "citation": _CIT_ICRP128,
        "note": "Older ICRP 80/106 gives a different adult value (about 5.7e-3); the coefficient set matters.",
    },
    "Tc99m_tetrofosmin_rest": {
        "label": "99mTc-tetrofosmin (rest)",
        "source_id": ICRP128,
        "age_table_mSv_per_MBq": _age_table(8.0e-3, 1.0e-2, 1.5e-2, 2.4e-2, 4.6e-2),
        "citation": _CIT_ICRP128,
    },
    "Tc99m_tetrofosmin_exercise": {
        "label": "99mTc-tetrofosmin (exercise)",
        "source_id": ICRP128,
        "age_table_mSv_per_MBq": _age_table(6.9e-3, 8.8e-3, 1.3e-2, 2.1e-2, 3.9e-2),
        "citation": _CIT_ICRP128,
    },
    "Tc99m_DMSA": {
        "label": "99mTc-DMSA",
        "source_id": ICRP128,
        "age_table_mSv_per_MBq": _age_table(8.8e-3, 1.1e-2, 1.5e-2, 2.1e-2, 3.7e-2),
        "citation": _CIT_ICRP128,
    },
    "Tc99m_large_colloid": {
        "label": "99mTc large colloids (sulfur/tin colloid)",
        "source_id": ICRP128,
        "age_table_mSv_per_MBq": _age_table(9.1e-3, 1.2e-2, 1.8e-2, 2.7e-2, 4.9e-2),
        "citation": _CIT_ICRP128,
        "note": "The compilation lists this under the generic ICRP 128 'large colloids' entry.",
    },
    "Tc99m_pertechnetate_iv": {
        "label": "99mTc-pertechnetate (IV, no blocking agent)",
        "source_id": ICRP128,
        "age_table_mSv_per_MBq": _age_table(1.3e-2, 1.7e-2, 2.6e-2, 4.2e-2, 7.9e-2),
        "citation": _CIT_ICRP128,
    },
    "Ga67_citrate": {
        "label": "67Ga-citrate",
        "source_id": ICRP128,
        "age_table_mSv_per_MBq": _age_table(1.0e-1, 1.3e-1, 2.0e-1, 3.3e-1, 6.4e-1),
        "citation": _CIT_ICRP128,
    },
    "I123_ioflupane": {
        "label": "123I-ioflupane (FP-CIT)",
        "source_id": ICRP128,
        "age_table_mSv_per_MBq": _age_table(2.5e-2, 3.3e-2, 5.1e-2, 7.8e-2, 1.4e-1),
        "citation": _CIT_ICRP128,
    },
    "I123_BMIPP": {
        "label": "123I-BMIPP",
        "source_id": ICRP128,
        "age_table_mSv_per_MBq": _age_table(1.6e-2, 2.0e-2, 3.1e-2, 4.7e-2, 8.7e-2),
        "citation": _CIT_ICRP128,
    },
    "Tl201_chloride": {
        "label": "201Tl-chloride",
        "source_id": ICRP128,
        "age_table_mSv_per_MBq": {"adult": 1.4e-1},
        "citation": _CIT_ICRP128,
        "note": "Adult only: the source's pediatric row looks implausible and needs checking against ICRP 128.",
    },
    # ---- Adult-only, Andersson 2014 (E3) ------------------------------------
    "Tc99m_sestamibi_rest": {
        "label": "99mTc-sestamibi (rest)",
        "source_id": ANDERSSON,
        "age_table_mSv_per_MBq": {"adult": 7.03e-3},
        "citation": _CIT_ANDERSSON,
    },
    "Tc99m_sestamibi_exercise": {
        "label": "99mTc-sestamibi (exercise)",
        "source_id": ANDERSSON,
        "age_table_mSv_per_MBq": {"adult": 6.55e-3},
        "citation": _CIT_ANDERSSON,
    },
    "Tc99m_MAA": {
        "label": "99mTc-MAA",
        "source_id": ANDERSSON,
        "age_table_mSv_per_MBq": {"adult": 1.02e-2},
        "citation": _CIT_ANDERSSON,
    },
    "Tc99m_IDA": {
        "label": "99mTc-IDA derivatives (mebrofenin etc., normal hepatobiliary)",
        "source_id": ANDERSSON,
        "age_table_mSv_per_MBq": {"adult": 8.62e-3},
        "citation": _CIT_ANDERSSON,
    },
    "Tc99m_HMPAO": {
        "label": "99mTc-HMPAO",
        "source_id": ANDERSSON,
        "age_table_mSv_per_MBq": {"adult": 1.01e-2},
        "citation": _CIT_ANDERSSON,
    },
    "Tc99m_ECD": {
        "label": "99mTc-ECD",
        "source_id": ANDERSSON,
        "age_table_mSv_per_MBq": {"adult": 5.75e-3},
        "citation": _CIT_ANDERSSON,
    },
    "Tc99m_MAG3": {
        "label": "99mTc-MAG3 (normal renal function)",
        "source_id": ANDERSSON,
        "age_table_mSv_per_MBq": {"adult": 4.65e-3},
        "citation": _CIT_ANDERSSON,
    },
    "Tc99m_RBC": {
        "label": "99mTc-labelled erythrocytes",
        "source_id": ANDERSSON,
        "age_table_mSv_per_MBq": {"adult": 2.69e-3},
        "citation": _CIT_ANDERSSON,
    },
    "Tc99m_WBC": {
        "label": "99mTc-labelled leukocytes",
        "source_id": ANDERSSON,
        "age_table_mSv_per_MBq": {"adult": 7.17e-3},
        "citation": _CIT_ANDERSSON,
    },
    "I123_MIBG": {
        "label": "123I-MIBG",
        "source_id": ANDERSSON,
        "age_table_mSv_per_MBq": {"adult": 1.32e-2},
        "citation": _CIT_ANDERSSON,
    },
    "In111_octreotide": {
        "label": "111In-octreotide (pentetreotide)",
        "source_id": ANDERSSON,
        "age_table_mSv_per_MBq": {"adult": 6.87e-2},
        "citation": _CIT_ANDERSSON,
    },
}

SPECT_LABELS = {k: v["label"] for k, v in SPECT_RADIOPHARMACEUTICALS.items()}


def get_spect_k_factor(radiopharm_key: str, age_years):
    """SPECT tracer lookup (thin wrapper over the shared lookup)."""
    return lookup_k(SPECT_RADIOPHARMACEUTICALS, radiopharm_key, age_years)
