# Effective Dose Calculator (v3: CT, PET/CT, SPECT)

Batch effective-dose estimation from a CSV / XLSX / XLS file. The result is the
original file plus new columns (nothing of yours is changed or dropped).

```bash
pip install -r requirements.txt
streamlit run app.py
python3 test_calculator.py && python3 test_io_utils.py
```

## What each modality computes

| Modality | Effective dose (mSv) |
|---|---|
| CT | `DLP x k(region, age)` |
| PET/CT | `CT component (optional)` + `injected activity (MBq) x tracer coefficient(age)` |
| SPECT / planar | same as PET/CT; CT component optional (SPECT/CT) |

These are **reference-person effective doses, not patient-specific absorbed doses.**
Tracer coefficients assume normal biokinetics (normal renal function, standard voiding).

## Coefficient sources (the part to scrutinise)

* **CT** (`coefficients.py`): EUR 16262 / AAPM Report 96 table (ICRP 60 weighting), the
  basis of most national DRL programs. Newer ICRP 103-based tables differ by up to ~30%
  for some regions (notably chest). Adult cutoff 18 y.
* **PET** (`pet_coefficients.py`): FDG = ICRP 128 age table (adult to 1 y); 68Ga-DOTATATE =
  NETSPOT FDA label age table; 68Ga-PSMA-11 = FDA label, adult-only (literature range
  about 0.017-0.026 mSv/MBq, the least settled value here).
* **SPECT** (`spect_coefficients.py`), two source sets recorded per row in `nm_coefficient_source`:
  * `icrp128_via_nmp`: ICRP 128 age tables (adult, 15, 10, 5, 1 y) for 99mTc-phosphonates,
    tetrofosmin (rest/exercise), DMSA, large colloids, pertechnetate, 67Ga, 123I-ioflupane,
    123I-BMIPP, and adult-only 201Tl. **Transcribed from a manufacturer's compilation of
    ICRP 128 (secondary source); two extractions agreed, but NOT yet checked against the
    ICRP 128 Annex.**
  * `andersson2014`: adult-only values (EJNMMI Phys 2014;1:9, Table 1, column E3, ICRP 103
    weighting) for sestamibi (rest/exercise), MAA, IDA/mebrofenin, HMPAO, ECD, MAG3, RBC,
    WBC, 123I-MIBG, 111In-octreotide. A peer-reviewed recomputation, **not** the official
    ICRP 128 number; can differ by tens of percent (e.g. FDG 0.0159 vs 0.019).

## Behaviour rules (enforced by tests)

* Missing / non-numeric / implausible input -> blank result plus a specific reason; never imputed.
* An age with no tabulated coefficient (e.g. a child with an adult-only tracer, or a newborn
  where the table starts at 1 y) -> **flagged, never given the adult value.**
* Age bin = reference age at or below the patient's age (rounds a child's coefficient up).
* Activity <= 0 or > 3000 MBq -> flagged as a probable unit error.
* CT part, NM part and total are reported separately; one failing part does not hide the other.
* Output audit columns: coefficient used, age bin used, coefficient source, CT table version.
* One row = one administration (rest + stress myocardial perfusion = two rows).

## File handling (`io_utils.py`)

CSV: UTF-8 (BOM or not) and cp1252; comma, semicolon, tab or pipe delimiter; output keeps the
input delimiter. Excel: sheet picker (output holds that sheet only); legacy .xls readable
(needs `xlrd`) but written back as .xlsx. Refused with a clear message: duplicate headers,
empty files, header-only files, and files that already contain a result column name.
Text in numeric columns is reported (count, examples, decimal-comma hint).

## Status and known gaps

* Unit tests: dosimetry (17) and file handling (8) pass.
* **The Streamlit UI for SPECT has not been click-tested end to end** (app starts and the
  upload step renders; the SPECT mapping flow was not completed in an automated browser run).
* ICRP 128 Annex values not yet verified for the SPECT tracers above.
* No sex-specific coefficients; no fuzzy matching of region / tracer names (mapped by hand on
  purpose); radiography and mammography not implemented; single CT table only.
* Multi-administration studies in one row are not supported.

## Sample files

`sample_input.csv` (CT), `sample_pet_ct_input.csv` (PET/CT), `sample_spect_input.csv`
(semicolon-delimited SPECT/CT with a missing age, missing activity, a child with an adult-only
tracer, a 5000 MBq activity and a decimal-comma activity).
