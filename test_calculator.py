"""
Validation tests. Run with:  python3 test_calculator.py

CT reference cases come from howradiologyworks.com/dlp-calculator (same
EUR16262/AAPM96 table this project uses): adult head DLP=1000 -> 2.1 mSv,
adult chest DLP=500 -> 7.0 mSv.

The nuclear-medicine tests check three different things:
  1. specific looked-up values (so a typo in a coefficient file is caught),
  2. the never-guess behaviour (missing / implausible / untabulated -> blank
     plus a reason, never a default),
  3. structural sanity of every coefficient table (positive values, adult
     present, coefficients non-increasing with age) -- a cheap transcription
     check that would have caught the odd Tl-201 pediatric row.
"""

import math

import pandas as pd

from coefficients import get_k_factor, age_to_bin
from radiopharm_core import nm_age_to_bin, BIN_DESCRIPTIONS
from pet_coefficients import get_nm_k_factor, RADIOPHARMACEUTICALS
from spect_coefficients import get_spect_k_factor, SPECT_RADIOPHARMACEUTICALS
from calculator import (
    calculate_effective_dose,
    calculate_pet_ct_effective_dose,
    calculate_spect_effective_dose,
)

NAN = float("nan")


def close(a, b, tol=1e-9):
    return abs(a - b) < tol


# ----------------------------------------------------------------------------
# CT
# ----------------------------------------------------------------------------
def test_age_binning():
    assert age_to_bin(0) == "0"
    assert age_to_bin(0.5) == "0"
    assert age_to_bin(1) == "1"
    assert age_to_bin(4.9) == "1"
    assert age_to_bin(5) == "5"
    assert age_to_bin(9.9) == "5"
    assert age_to_bin(10) == "10"
    assert age_to_bin(17.9) == "10"
    assert age_to_bin(18) == "adult"
    assert age_to_bin(45) == "adult"
    assert age_to_bin(None) is None
    assert age_to_bin(-1) is None
    print("test_age_binning: PASS")


def test_known_k_factors():
    r = get_k_factor("head", 40)
    assert r.ok and r.k == 0.0021, r
    r = get_k_factor("chest", 40)
    assert r.ok and r.k == 0.014, r
    r = get_k_factor("head", 0)
    assert r.ok and r.k == 0.011, r
    print("test_known_k_factors: PASS")


def test_worked_examples_from_reference_site():
    assert close(1000 * get_k_factor("head", 40).k, 2.1)
    assert close(500 * get_k_factor("chest", 40).k, 7.0)
    print("test_worked_examples_from_reference_site: PASS")


def test_missing_data_never_imputed():
    df = pd.DataFrame({
        "patient_id": [1, 2, 3, 4, 5],
        "_dlp_mGycm": [1000, None, 500, -50, 300],
        "_age_years": [40, 5, None, 30, 200],
        "_region": ["head", "chest", "chest", "abdomen_and_pelvis", "head"],
    })
    out = calculate_effective_dose(df)
    assert out.loc[0, "dose_calc_status"] == "ok"
    assert out.loc[0, "effective_dose_mSv"] == 2.1
    assert out.loc[1, "dose_calc_status"] == "missing: DLP"
    assert pd.isna(out.loc[1, "effective_dose_mSv"])
    assert out.loc[2, "dose_calc_status"] == "missing: age"
    assert pd.isna(out.loc[2, "effective_dose_mSv"])
    assert "invalid" in out.loc[3, "dose_calc_status"]
    assert pd.isna(out.loc[3, "effective_dose_mSv"])
    assert "invalid" in out.loc[4, "dose_calc_status"]
    assert pd.isna(out.loc[4, "effective_dose_mSv"])
    assert list(df["patient_id"]) == list(out["patient_id"])
    print("test_missing_data_never_imputed: PASS")


def test_unsupported_region_flagged_not_guessed():
    df = pd.DataFrame({"_dlp_mGycm": [1000], "_age_years": [40], "_region": ["thigh"]})
    out = calculate_effective_dose(df)
    assert pd.isna(out.loc[0, "effective_dose_mSv"])
    assert "unsupported region" in out.loc[0, "dose_calc_status"]
    print("test_unsupported_region_flagged_not_guessed: PASS")


# ----------------------------------------------------------------------------
# Shared age binning for radiopharmaceuticals
# ----------------------------------------------------------------------------
def test_nm_age_binning_and_nan():
    assert nm_age_to_bin(0.3) == "0"
    assert nm_age_to_bin(1) == "1"
    assert nm_age_to_bin(4.99) == "1"
    assert nm_age_to_bin(5) == "5"
    assert nm_age_to_bin(10) == "10"
    assert nm_age_to_bin(14.9) == "10"
    assert nm_age_to_bin(15) == "15"
    assert nm_age_to_bin(17.9) == "15"
    assert nm_age_to_bin(18) == "adult"
    assert nm_age_to_bin(None) is None
    assert nm_age_to_bin(-1) is None
    # Regression: NaN must NOT fall through to "adult".
    assert nm_age_to_bin(NAN) is None
    print("test_nm_age_binning_and_nan: PASS")


# ----------------------------------------------------------------------------
# PET
# ----------------------------------------------------------------------------
def test_pet_coefficients():
    assert get_nm_k_factor("F18_FDG", 45).k == 0.019
    assert get_nm_k_factor("F18_FDG", 16).k == 0.024
    assert get_nm_k_factor("F18_FDG", 12).k == 0.037
    assert get_nm_k_factor("F18_FDG", 8).k == 0.056     # was the adult value before the fix
    assert get_nm_k_factor("F18_FDG", 2).k == 0.095
    r = get_nm_k_factor("F18_FDG", 0.5)                  # newborn: not tabulated
    assert not r.ok and "no coefficient" in r.reason, r

    assert get_nm_k_factor("Ga68_DOTATATE", 45).k == 0.021
    assert get_nm_k_factor("Ga68_DOTATATE", 16).k == 0.025
    assert get_nm_k_factor("Ga68_DOTATATE", 12).k == 0.04
    assert get_nm_k_factor("Ga68_DOTATATE", 7).k == 0.064
    assert get_nm_k_factor("Ga68_DOTATATE", 2).k == 0.13
    assert get_nm_k_factor("Ga68_DOTATATE", 0.2).k == 0.35

    assert get_nm_k_factor("Ga68_PSMA11", 60).k == 0.0169
    r = get_nm_k_factor("Ga68_PSMA11", 16)               # adult-only tracer, minor
    assert not r.ok and "no coefficient" in r.reason, r

    for age in (None, NAN):
        r = get_nm_k_factor("F18_FDG", age)
        assert not r.ok and "age" in r.reason, r
    print("test_pet_coefficients: PASS")


def test_pet_ct_worked_example():
    df = pd.DataFrame({
        "_dlp_mGycm": [800.0], "_age_years": [50.0], "_region": ["trunk"],
        "_activity_MBq": [300.0], "_radiopharm": ["F18_FDG"],
    })
    out = calculate_pet_ct_effective_dose(df, include_ct=True)
    assert out.loc[0, "ct_effective_dose_mSv"] == 12.0, out.loc[0]      # 800 x 0.015
    assert out.loc[0, "nm_effective_dose_mSv"] == 5.7, out.loc[0]       # 300 x 0.019
    assert out.loc[0, "total_effective_dose_mSv"] == 17.7, out.loc[0]
    assert out.loc[0, "total_dose_status"] == "ok"
    assert out.loc[0, "nm_coefficient_source"] == "icrp128_via_nmp"
    assert out.loc[0, "nm_age_bin_used"] == "adult"
    assert out.loc[0, "nm_coefficient_mSv_per_MBq"] == 0.019
    print("test_pet_ct_worked_example: PASS")


def test_pet_ct_partial_results_not_hidden():
    df = pd.DataFrame({
        "_dlp_mGycm": [800.0, None], "_age_years": [50.0, 50.0], "_region": ["trunk", "trunk"],
        "_activity_MBq": [300.0, 300.0], "_radiopharm": ["F18_FDG", "F18_FDG"],
    })
    out = calculate_pet_ct_effective_dose(df, include_ct=True)
    assert out.loc[0, "total_dose_status"] == "ok"
    assert pd.isna(out.loc[1, "ct_effective_dose_mSv"])
    assert out.loc[1, "nm_effective_dose_mSv"] == 5.7
    assert pd.isna(out.loc[1, "total_effective_dose_mSv"])
    assert "CT:" in out.loc[1, "total_dose_status"]
    print("test_pet_ct_partial_results_not_hidden: PASS")


def test_pet_nm_only_mode():
    df = pd.DataFrame({
        "_age_years": [45.0], "_activity_MBq": [150.0], "_radiopharm": ["Ga68_DOTATATE"],
    })
    out = calculate_pet_ct_effective_dose(df, include_ct=False)
    assert out.loc[0, "nm_effective_dose_mSv"] == round(150.0 * 0.021, 4)
    assert out.loc[0, "total_effective_dose_mSv"] == out.loc[0, "nm_effective_dose_mSv"]
    assert out.loc[0, "total_dose_status"] == "ok"
    print("test_pet_nm_only_mode: PASS")


# ----------------------------------------------------------------------------
# SPECT
# ----------------------------------------------------------------------------
def test_spect_lookups():
    assert get_spect_k_factor("Tc99m_phosphonates", 50).k == 4.9e-3
    assert get_spect_k_factor("Tc99m_phosphonates", 16).k == 5.7e-3
    assert get_spect_k_factor("Tc99m_phosphonates", 3).k == 1.8e-2
    assert get_spect_k_factor("Tc99m_tetrofosmin_rest", 50).k == 8.0e-3
    assert get_spect_k_factor("Tc99m_tetrofosmin_exercise", 50).k == 6.9e-3
    assert get_spect_k_factor("Ga67_citrate", 50).k == 1.0e-1
    assert get_spect_k_factor("I123_ioflupane", 50).k == 2.5e-2
    assert get_spect_k_factor("Tc99m_sestamibi_rest", 50).k == 7.03e-3
    assert get_spect_k_factor("I123_MIBG", 50).k == 1.32e-2

    # Adult-only entries must refuse a child rather than reuse the adult value.
    for key in ("Tc99m_sestamibi_rest", "Tl201_chloride", "I123_MIBG", "Tc99m_MAA"):
        r = get_spect_k_factor(key, 12)
        assert not r.ok and "no coefficient" in r.reason, (key, r)

    # Newborn is not in the ICRP 128 age tables used here.
    r = get_spect_k_factor("Tc99m_phosphonates", 0.4)
    assert not r.ok, r

    r = get_spect_k_factor("Not_a_tracer", 50)
    assert not r.ok and "unsupported" in r.reason
    print("test_spect_lookups: PASS")


def test_spect_only_dose_and_audit_columns():
    df = pd.DataFrame({
        "_age_years": [50.0, 12.0],
        "_activity_MBq": [925.0, 300.0],
        "_radiopharm": ["Tc99m_phosphonates", "Tc99m_tetrofosmin_rest"],
    })
    out = calculate_spect_effective_dose(df, include_ct=False)
    assert close(out.loc[0, "nm_effective_dose_mSv"], round(925.0 * 4.9e-3, 4))
    assert close(out.loc[1, "nm_effective_dose_mSv"], 4.5)     # 300 x 1.5e-2 (10-year bin)
    assert out.loc[1, "nm_age_bin_used"] == "10"
    assert out.loc[0, "nm_coefficient_source"] == "icrp128_via_nmp"
    assert (out["total_dose_status"] == "ok").all()
    print("test_spect_only_dose_and_audit_columns: PASS")


def test_spect_ct_combined():
    df = pd.DataFrame({
        "_dlp_mGycm": [100.0], "_age_years": [55.0], "_region": ["chest"],
        "_activity_MBq": [400.0], "_radiopharm": ["Tc99m_sestamibi_rest"],
    })
    out = calculate_spect_effective_dose(df, include_ct=True)
    assert close(out.loc[0, "ct_effective_dose_mSv"], 1.4)             # 100 x 0.014
    assert close(out.loc[0, "nm_effective_dose_mSv"], 2.812)           # 400 x 7.03e-3
    assert close(out.loc[0, "total_effective_dose_mSv"], 4.212)
    assert out.loc[0, "nm_coefficient_source"] == "andersson2014"
    print("test_spect_ct_combined: PASS")


def test_spect_child_with_adult_only_tracer_is_incomplete():
    df = pd.DataFrame({
        "_dlp_mGycm": [100.0], "_age_years": [12.0], "_region": ["chest"],
        "_activity_MBq": [300.0], "_radiopharm": ["Tc99m_sestamibi_rest"],
    })
    out = calculate_spect_effective_dose(df, include_ct=True)
    assert out.loc[0, "ct_dose_status"] == "ok"                        # CT part still shown
    assert pd.isna(out.loc[0, "nm_effective_dose_mSv"])
    assert pd.isna(out.loc[0, "total_effective_dose_mSv"])
    assert out.loc[0, "total_dose_status"].startswith("incomplete")
    assert "no coefficient" in out.loc[0, "total_dose_status"]
    print("test_spect_child_with_adult_only_tracer_is_incomplete: PASS")


def test_nm_implausible_and_missing_inputs():
    df = pd.DataFrame({
        "_age_years":    [40.0, 40.0, 40.0, 40.0, 40.0, NAN, 200.0, 40.0],
        "_activity_MBq": [0.0, -5.0, 5000.0, NAN, 100.0, 100.0, 100.0, 100.0],
        "_radiopharm": ["Ga67_citrate", "Ga67_citrate", "Ga67_citrate", "Ga67_citrate",
                        NAN, "Ga67_citrate", "Ga67_citrate", "Foo"],
    })
    out = calculate_spect_effective_dose(df, include_ct=False)
    s = list(out["nm_dose_status"])
    assert "zero or negative" in s[0], s[0]
    assert "zero or negative" in s[1], s[1]
    assert "check units" in s[2], s[2]
    assert s[3] == "missing: activity", s[3]
    assert s[4] == "missing: radiopharmaceutical", s[4]
    assert s[5] == "missing: age", s[5]
    assert "age out of plausible range" in s[6], s[6]
    assert "unsupported radiopharmaceutical" in s[7], s[7]
    assert out["nm_effective_dose_mSv"].isna().all()
    assert out["total_effective_dose_mSv"].isna().all()
    print("test_nm_implausible_and_missing_inputs: PASS")


def test_original_columns_preserved_and_row_order_kept():
    df = pd.DataFrame({
        "patient_id": ["a", "b", "c"],
        "note": ["x", None, "z"],
        "_age_years": [50.0, NAN, 60.0],
        "_activity_MBq": [100.0, 100.0, 100.0],
        "_radiopharm": ["Ga67_citrate"] * 3,
    })
    out = calculate_spect_effective_dose(df, include_ct=False)
    assert list(out["patient_id"]) == ["a", "b", "c"]
    assert out["note"].tolist()[0] == "x" and pd.isna(out["note"].tolist()[1])
    assert len(out) == len(df)
    print("test_original_columns_preserved_and_row_order_kept: PASS")


# ----------------------------------------------------------------------------
# Coefficient-table structural sanity (PET + SPECT)
# ----------------------------------------------------------------------------
def test_coefficient_tables_are_sane():
    order = ["0", "1", "5", "10", "15", "adult"]       # young -> old
    known_sources = {"icrp128_via_nmp", "netspot_fda_2023", "fda_gozetotide", "andersson2014"}
    for name, registry in (("PET", RADIOPHARMACEUTICALS), ("SPECT", SPECT_RADIOPHARMACEUTICALS)):
        for key, entry in registry.items():
            where = f"{name}:{key}"
            assert entry["label"] and entry["citation"], where
            assert entry["source_id"] in known_sources, where
            table = entry["age_table_mSv_per_MBq"]
            assert "adult" in table, f"{where}: adult value missing"
            assert set(table) <= set(BIN_DESCRIPTIONS), f"{where}: unknown age bin"
            values = [table[b] for b in order if b in table]
            assert all(isinstance(v, float) and v > 0 and math.isfinite(v) for v in values), where
            # Dose per unit activity should not INCREASE as patients get older.
            assert all(values[i] >= values[i + 1] for i in range(len(values) - 1)), \
                f"{where}: coefficients increase with age -> probable transcription error: {values}"
    print("test_coefficient_tables_are_sane: PASS")


if __name__ == "__main__":
    test_age_binning()
    test_known_k_factors()
    test_worked_examples_from_reference_site()
    test_missing_data_never_imputed()
    test_unsupported_region_flagged_not_guessed()
    test_nm_age_binning_and_nan()
    test_pet_coefficients()
    test_pet_ct_worked_example()
    test_pet_ct_partial_results_not_hidden()
    test_pet_nm_only_mode()
    test_spect_lookups()
    test_spect_only_dose_and_audit_columns()
    test_spect_ct_combined()
    test_spect_child_with_adult_only_tracer_is_incomplete()
    test_nm_implausible_and_missing_inputs()
    test_original_columns_preserved_and_row_order_kept()
    test_coefficient_tables_are_sane()
    print("\nAll tests passed.")
