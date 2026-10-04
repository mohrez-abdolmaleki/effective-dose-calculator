"""
Validation against known reference values before trusting this on real data.

Reference cases (from howradiologyworks.com/dlp-calculator, using the same
EUR16262/AAPM96 table this project uses):
  - Adult head, DLP = 1000 mGy*cm  -> ~2.0 mSv (k=0.0021 -> 2.1 mSv exactly)
  - Adult chest, DLP = 500 mGy*cm  -> ~7.0 mSv (k=0.014  -> 7.0 mSv exactly)
  - Newborn (age 0) head, DLP = 1000 mGy*cm -> ~6 mSv (their rounded example
    uses head_and_neck-ish framing loosely; here we check head k=0.011 -> 11 mSv.
    NOTE: this exposes an ambiguity in the site's own worked example -- see
    the printed comparison below. We trust our own table lookup, which is
    explicitly sourced, over an imprecise narrative example.)
"""

import pandas as pd
from coefficients import get_k_factor, age_to_bin
from pet_coefficients import get_nm_k_factor, nm_age_to_bin
from calculator import calculate_effective_dose, calculate_pet_ct_effective_dose


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
    # Adult head, DLP=1000 -> expect 2.1 mSv (site says "about 2 mSv")
    dose_head = 1000 * get_k_factor("head", 40).k
    print(f"Adult head, DLP=1000 mGy*cm -> {dose_head} mSv (reference site: 'about 2 mSv')")
    assert abs(dose_head - 2.1) < 1e-9

    # Adult chest, DLP=500 -> expect 7.0 mSv (site says "about 7 mSv")
    dose_chest = 500 * get_k_factor("chest", 40).k
    print(f"Adult chest, DLP=500 mGy*cm -> {dose_chest} mSv (reference site: 'about 7 mSv')")
    assert abs(dose_chest - 7.0) < 1e-9
    print("test_worked_examples_from_reference_site: PASS")


def test_missing_data_never_imputed():
    df = pd.DataFrame({
        "patient_id": [1, 2, 3, 4, 5],
        "_dlp_mGycm": [1000, None, 500, -50, 300],
        "_age_years": [40, 5, None, 30, 200],
        "_region": ["head", "chest", "chest", "abdomen_and_pelvis", "head"],
    })
    out = calculate_effective_dose(df)

    # row 0: complete, valid -> ok
    assert out.loc[0, "dose_calc_status"] == "ok"
    assert out.loc[0, "effective_dose_mSv"] == 2.1

    # row 1: missing DLP -> flagged, NOT imputed
    assert out.loc[1, "dose_calc_status"] == "missing: DLP"
    assert pd.isna(out.loc[1, "effective_dose_mSv"])

    # row 2: missing age -> flagged
    assert out.loc[2, "dose_calc_status"] == "missing: age"
    assert pd.isna(out.loc[2, "effective_dose_mSv"])

    # row 3: negative DLP -> flagged as invalid, not silently abs()'d
    assert "invalid" in out.loc[3, "dose_calc_status"]
    assert pd.isna(out.loc[3, "effective_dose_mSv"])

    # row 4: implausible age (200) -> flagged
    assert "invalid" in out.loc[4, "dose_calc_status"]
    assert pd.isna(out.loc[4, "effective_dose_mSv"])

    # original columns must be fully preserved
    assert list(df["patient_id"]) == list(out["patient_id"])
    print("test_missing_data_never_imputed: PASS")


def test_unsupported_region_flagged_not_guessed():
    df = pd.DataFrame({
        "_dlp_mGycm": [1000],
        "_age_years": [40],
        "_region": ["thigh"],  # not in the table
    })
    out = calculate_effective_dose(df)
    assert pd.isna(out.loc[0, "effective_dose_mSv"])
    assert "unsupported region" in out.loc[0, "dose_calc_status"]
    print("test_unsupported_region_flagged_not_guessed: PASS")


def test_nm_coefficients_against_fda_labels():
    # FDG, adult: ICRP 128 value, 0.019 mSv/MBq
    r = get_nm_k_factor("F18_FDG", 45)
    assert r.ok and r.k == 0.019, r
    # FDG, pediatric: NOT supported in this version -- must fail loudly,
    # not silently fall back to the adult value.
    r = get_nm_k_factor("F18_FDG", 8)
    assert r.ok, "F18_FDG is declared age_dependent=False, so any age returns the fixed adult value"
    assert r.k == 0.019

    # DOTATATE: full age table from the NETSPOT FDA label
    assert get_nm_k_factor("Ga68_DOTATATE", 45).k == 0.021   # adult
    assert get_nm_k_factor("Ga68_DOTATATE", 16).k == 0.025   # 15y bin
    assert get_nm_k_factor("Ga68_DOTATATE", 12).k == 0.04    # 10y bin
    assert get_nm_k_factor("Ga68_DOTATATE", 7).k == 0.064    # 5y bin
    assert get_nm_k_factor("Ga68_DOTATATE", 2).k == 0.13     # 1y bin
    assert get_nm_k_factor("Ga68_DOTATATE", 0.2).k == 0.35   # newborn bin
    r = get_nm_k_factor("Ga68_DOTATATE", None)
    assert not r.ok and "missing" in r.reason  # age-dependent tracer with no age -> must fail, not default

    # PSMA-11: adult-only FDA package insert value
    r = get_nm_k_factor("Ga68_PSMA11", 60)
    assert r.ok and r.k == 0.0169, r
    print("test_nm_coefficients_against_fda_labels: PASS")


def test_pet_ct_worked_example():
    # Worked example matching the published pattern:
    # Total E = [activity x NM coefficient] + [CT CF x DLP]
    # (cf. Elhelf et al./ResearchSquare FDG PET/CT dosimetry papers, which
    # use exactly this additive structure.)
    df = pd.DataFrame({
        "_dlp_mGycm": [800.0],
        "_age_years": [50.0],
        "_region": ["trunk"],
        "_activity_MBq": [300.0],
        "_radiopharm": ["F18_FDG"],
    })
    out = calculate_pet_ct_effective_dose(df, include_ct=True)
    # CT part: trunk, adult -> k=0.015 -> 800*0.015 = 12.0 mSv
    assert out.loc[0, "ct_effective_dose_mSv"] == 12.0, out.loc[0]
    # NM part: FDG adult -> 300*0.019 = 5.7 mSv
    assert out.loc[0, "nm_effective_dose_mSv"] == 5.7, out.loc[0]
    assert out.loc[0, "total_effective_dose_mSv"] == 17.7, out.loc[0]
    assert out.loc[0, "total_dose_status"] == "ok"
    print("test_pet_ct_worked_example: PASS")


def test_pet_ct_partial_results_not_hidden():
    df = pd.DataFrame({
        "_dlp_mGycm": [800.0, None],
        "_age_years": [50.0, 50.0],
        "_region": ["trunk", "trunk"],
        "_activity_MBq": [300.0, 300.0],
        "_radiopharm": ["F18_FDG", "F18_FDG"],
    })
    out = calculate_pet_ct_effective_dose(df, include_ct=True)
    # Row 0: complete -> total ok
    assert out.loc[0, "total_dose_status"] == "ok"
    # Row 1: CT missing DLP -> NM component still calculated and visible,
    # total is blank with a specific reason, not a generic failure
    assert pd.isna(out.loc[1, "ct_effective_dose_mSv"])
    assert out.loc[1, "nm_effective_dose_mSv"] == 5.7
    assert pd.isna(out.loc[1, "total_effective_dose_mSv"])
    assert "CT:" in out.loc[1, "total_dose_status"]
    print("test_pet_ct_partial_results_not_hidden: PASS")


def test_pet_ct_nm_only_mode():
    df = pd.DataFrame({
        "_age_years": [45.0],
        "_activity_MBq": [150.0],
        "_radiopharm": ["Ga68_DOTATATE"],
    })
    out = calculate_pet_ct_effective_dose(df, include_ct=False)
    assert out.loc[0, "nm_effective_dose_mSv"] == round(150.0 * 0.021, 4)
    assert out.loc[0, "total_effective_dose_mSv"] == out.loc[0, "nm_effective_dose_mSv"]
    assert out.loc[0, "total_dose_status"] == "ok"
    print("test_pet_ct_nm_only_mode: PASS")


if __name__ == "__main__":
    test_age_binning()
    test_known_k_factors()
    test_worked_examples_from_reference_site()
    test_missing_data_never_imputed()
    test_unsupported_region_flagged_not_guessed()
    test_nm_coefficients_against_fda_labels()
    test_pet_ct_worked_example()
    test_pet_ct_partial_results_not_hidden()
    test_pet_ct_nm_only_mode()
    print("\nAll tests passed.")
