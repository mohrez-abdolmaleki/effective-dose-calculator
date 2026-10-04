# Effective Dose Calculator (v2: CT and PET/CT)

Batch effective-dose estimation from a CSV/XLSX/XLS file, for CT and now
PET/CT. Architected so that additional modalities (radiography,
mammography) can be added as independent calculators later without
touching the existing ones.

## Run it

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Methodology

Effective dose (mSv) = DLP (mGy·cm) × k, where k is an age- and
body-region-dependent coefficient.

Coefficient table: `coefficients.EUR16262_AAPM96_TABLE`, sourced from the
European Commission's 1999 quality-criteria report (EUR 16262) as
reproduced in AAPM Report No. 96 (McCollough et al., 2008). This reflects
**ICRP Publication 60 (1990)** tissue-weighting factors — the version most
widely embedded in national Diagnostic Reference Level programs and IAEA
guidance, but *not* the more recent ICRP Publication 103 (2007) weighting
factors. Newer ICRP 103–consistent coefficient sets exist (Shrimpton et
al. 2010; Deak et al. 2010; Bahador et al. 2023) and differ from this
table by up to ~30% for some regions. See the in-app "Methodology and
limitations" panel.

**This tool estimates a reference-person effective dose, not a
patient-specific absorbed dose.** Do not present its output as
individualized risk.

### PET/CT

Total effective dose = CT component (`DLP x k`, same table as above) +
NM component (`injected activity (MBq) x radiopharmaceutical
coefficient`). The two components are reported, and flagged, separately
(`ct_effective_dose_mSv`/`ct_dose_status`,
`nm_effective_dose_mSv`/`nm_dose_status`), plus a combined
`total_effective_dose_mSv`/`total_dose_status` that is only "ok" when
both components succeeded.

Radiopharmaceutical coefficients (`pet_coefficients.py`), one primary
source each -- **these are not all equally settled**, unlike the single
CT table:

| Tracer | Coefficient | Age-dependent? | Source |
|---|---|---|---|
| [18F]FDG | 0.019 mSv/MBq | No (adult value used for all ages in this version) | ICRP Publication 128 |
| 68Ga-DOTATATE | 0.021 (adult) to 0.35 (newborn) mSv/MBq | Yes, full age table | NETSPOT FDA prescribing information, Table 4 |
| 68Ga-PSMA-11 | 0.0169 mSv/MBq (adult only; no pediatric indication) | No | FDA prescribing information (e.g. Illuccix); literature range is wider (~0.017–0.026), see in-app note |

**Known gap, stated rather than hidden:** pediatric FDG coefficients are
not implemented. A clean per-age mSv/MBq table from a primary source
(ICRP 128 itself, not a back-calculation from someone else's worked
examples) was not in hand at the time of writing. All FDG rows use the
adult coefficient regardless of age — this is flagged in the app's
methodology panel, not silently applied.

## Design decisions worth knowing about before you extend this

1. **Coefficient tables are versioned data, not hardcoded logic**
   (`coefficients.py`). Every calculated row is tagged with
   `coefficient_table_version`. To add an ICRP 103–based table, add a new
   dict alongside `EUR16262_AAPM96_TABLE` with its own citation and
   version id — do not overwrite the existing one, and make it
   user-selectable in the UI rather than swapping the default silently.

2. **Missing or invalid data is never imputed.** `calculator.py`'s
   `_calc_one_row` returns `NaN` + a specific reason string
   (`"missing: age"`, `"invalid: DLP is negative"`, etc.) for any row it
   cannot confidently calculate. This is enforced by
   `test_calculator.py::test_missing_data_never_imputed` — if you change
   this behavior, that test should fail loudly.

3. **Age binning is an explicit, centralized assumption**
   (`coefficients.AGE_BIN_ADULT_CUTOFF = 18`), not baked into the
   calculation logic. The source table only defines five discrete
   reference ages (0, 1, 5, 10, adult); mapping a continuous age onto
   those bins is an implementation choice, documented as such in
   `coefficients.py`.

4. **Column mapping happens once, in the UI layer** (`app.py`), producing
   three standardized internal columns (`_dlp_mGycm`, `_age_years`,
   `_region`) before calculation. `calculator.py` has no knowledge of the
   user's original column names — this is what lets the calculation
   logic be unit-tested independent of any particular file's schema.

5. **Body region free-text values are mapped explicitly by the user**,
   one distinct value at a time, rather than fuzzy-matched. Fuzzy string
   matching on clinical terminology (e.g. "C/A/P" vs "abd+pelvis" vs
   "Abdomen/Pelvis") is a plausible v2 convenience feature, but silently
   guessing a wrong region silently produces a wrong effective dose —
   not an acceptable failure mode for this kind of tool. If you add
   fuzzy matching later, it should populate suggestions for the user to
   confirm, not auto-apply them.

## Validate before trusting it on real data

```bash
python3 test_calculator.py
```

This checks the age-binning logic, reproduces the two worked examples
published on the howradiologyworks.com reference calculator (adult head,
DLP=1000 → 2.1 mSv; adult chest, DLP=500 → 7.0 mSv) as a sanity check
against an independent source, and confirms missing/invalid data is
flagged rather than guessed.

## Try it

`sample_input.csv` (CT) and `sample_pet_ct_input.csv` (PET/CT) are
included as test files with intentionally messy, realistic data: missing
ages, missing DLP, an unsupported body region ("Foot"), a lowercase/slash
region variant, a pediatric age at a bin boundary, a missing injected
activity, and a row with CT data missing but NM data present (to see
that the NM component still calculates while the total stays blank) —
upload them to the running app to see the full column-mapping and
flagging workflow.

## Known limitations (not yet built)

- Radiography (DAP-based) and mammography (AGD-based, structurally
  different pipeline) are not implemented.
- No sex stratification anywhere (the CT table doesn't have one; Deak
  et al. 2010 does, if that level of granularity is wanted later).
- No fuzzy/auto region or tracer-name matching (see design decision 5
  above) -- every distinct raw value is mapped by hand, on purpose.
- Single CT coefficient table only; ICRP 103–based tables not yet added.
- Pediatric FDG not implemented (see PET/CT section above).
- 68Ga-PSMA-11's coefficient is the least settled number in this tool --
  treat its output with more caution than FDG or DOTATATE.
