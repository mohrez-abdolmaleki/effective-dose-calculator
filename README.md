# CT Effective Dose Calculator

A Streamlit-based tool for batch estimation of CT effective dose from DLP data in CSV/XLSX/XLS files.

**Current version: v1 — CT only**

The calculator is deliberately structured so that additional imaging modalities (e.g., PET/CT, radiography, and mammography) can be added as independent calculators without modifying the existing CT calculation logic.

## Features

* Batch CT effective-dose estimation from CSV/XLSX/XLS files
* Age- and body-region-dependent DLP-to-effective-dose coefficients
* Explicit user-controlled body-region mapping
* Missing and invalid data are flagged rather than imputed
* Per-row calculation status and reason reporting
* Versioned coefficient tables
* Streamlit web interface
* Built-in validation tests
* Sample input file with intentionally messy, realistic data

## Quick Start

Clone the repository and enter the project directory:

```bash
git clone <repository-url>
cd <repository-directory>
```

Install the required dependencies:

```bash
python -m pip install -r requirements.txt
```

Run the application:

```bash
python -m streamlit run app.py
```

The application will be available at:

```text
http://localhost:8501
```

## Input Data

The application accepts CSV, XLSX, and XLS files containing CT examination data.

At minimum, the input dataset should contain information corresponding to:

* **DLP** — dose-length product in mGy·cm
* **Age** — patient age in years
* **Body region** — anatomical region corresponding to the CT examination

Because clinical datasets frequently use different column names, the application allows the user to map their original columns to the standardized internal fields used by the calculator.

The application does not automatically infer ambiguous body-region terminology.

## Output

For each row that can be confidently calculated, the application reports the estimated effective dose in mSv together with the coefficient-table version used for the calculation.

Rows with missing, invalid, or unsupported information are retained and flagged with a specific reason rather than being silently excluded or imputed.

Examples include:

```text
missing: age
missing: DLP
invalid: DLP is negative
unsupported: body region
```

## Methodology

The calculator uses:

```text
Effective dose (mSv) = DLP (mGy·cm) × k
```

where `k` is an age- and body-region-dependent conversion coefficient.

The current coefficient table is:

```text
coefficients.EUR16262_AAPM96_TABLE
```

It is based on the European Commission's 1999 quality-criteria report (EUR 16262), as reproduced in AAPM Report No. 96 (McCollough et al., 2008). AAPM Report 96 explicitly describes the use of DLP-to-effective-dose conversion factors for estimating effective dose from CT dose data.

This coefficient set reflects **ICRP Publication 60 (1990)** tissue-weighting factors. It does **not** use the more recent ICRP Publication 103 (2007) tissue-weighting factors.

Newer ICRP 103-consistent conversion-factor approaches have subsequently been published. For example, Deak et al. (2010) developed sex- and age-specific conversion factors based on Monte Carlo calculations using both ICRP 60 and ICRP 103 recommendations. Their results demonstrated substantial differences from previously published conversion factors for some regions and patient groups.

### Important interpretation

This tool estimates a **reference-person effective dose** from DLP.

It does not estimate:

* patient-specific absorbed dose,
* organ-specific absorbed dose,
* individualized radiation risk, or
* a patient's actual biological effect.

Therefore, the calculated effective dose should not be presented as an individualized patient risk estimate.

## Age Binning

The source coefficient table provides five discrete reference-age categories:

```text
0 years
1 year
5 years
10 years
Adult
```

The mapping of continuous patient age to these categories is an explicit implementation assumption.

The adult cutoff is defined centrally as:

```python
coefficients.AGE_BIN_ADULT_CUTOFF = 18
```

This assumption is kept separate from the calculation logic so that it can be reviewed or modified independently if an alternative age-binning scheme is adopted.

## Design Decisions

### 1. Coefficient tables are versioned data

Coefficient tables are stored in `coefficients.py` rather than being hardcoded into the calculation logic.

Every calculated row is tagged with:

```text
coefficient_table_version
```

If an ICRP 103-based coefficient table is added in a future version, it should be introduced as a new independently identified table rather than replacing the existing EUR 16262/AAPM96 table.

The user interface should allow the coefficient table to be selected explicitly rather than silently changing the default methodology.

### 2. Missing or invalid data are never imputed

`calculator.py` does not attempt to guess missing or invalid input values.

The `_calc_one_row` function returns `NaN` together with a specific reason string whenever a row cannot be confidently calculated.

For example:

```text
missing: age
missing: DLP
invalid: DLP is negative
```

This behavior is enforced by:

```text
test_calculator.py::test_missing_data_never_imputed
```

Any future change that introduces automatic imputation should therefore require an explicit methodological decision rather than occurring implicitly.

### 3. Age binning is centralized

Age classification is defined in `coefficients.py` rather than being embedded directly in the calculation function.

This makes the age-mapping assumption visible and independently testable.

### 4. Column mapping occurs in the UI layer

Column mapping is performed once in `app.py`.

The application converts the user's original column names into three standardized internal fields:

```text
_dlp_mGycm
_age_years
_region
```

`calculator.py` operates only on these standardized fields and therefore has no dependency on the original dataset schema.

This separation allows the calculation logic to be unit-tested independently of any particular input-file structure.

### 5. Body-region mapping is explicit

Body-region values are mapped explicitly by the user, one distinct value at a time.

The application does not currently use fuzzy matching for clinical terminology.

For example:

```text
C/A/P
abd+pelvis
Abdomen/Pelvis
```

may refer to similar examinations but are not necessarily equivalent in every dataset.

Automatically guessing the anatomical region could silently produce an incorrect effective dose. For this reason, ambiguous terminology is treated as a user-confirmation problem rather than an automatic classification problem.

A future fuzzy-matching implementation could provide suggested mappings for user confirmation, but should not silently apply them.

## Validation

Before using the calculator with real data, run:

```bash
python test_calculator.py
```

The test suite checks:

* age-binning behavior,
* expected coefficient selection,
* adult head sanity check,
* adult chest sanity check,
* missing-data handling,
* invalid-data handling, and
* the requirement that missing values are never automatically imputed.

Two worked examples from an independent reference calculator are reproduced as sanity checks:

```text
Adult head:
DLP = 1000 mGy·cm
Expected effective dose = 2.1 mSv

Adult chest:
DLP = 500 mGy·cm
Expected effective dose = 7.0 mSv
```

These examples are intended as implementation sanity checks and should not be interpreted as validation of patient-specific dose estimation.

## Sample Dataset

`sample_input.csv` is included for testing the complete application workflow.

It intentionally contains realistic problematic entries, including:

* a missing age,
* a missing DLP,
* an unsupported body region (`Foot`),
* a lowercase/slash variation of a region name, and
* a pediatric age at a bin boundary.

The file can be uploaded directly into the Streamlit application to inspect the column-mapping, region-mapping, calculation, and error-flagging workflow.

## Project Structure

```text
.
├── app.py
├── calculator.py
├── coefficients.py
├── io_utils.py
├── test_calculator.py
├── sample_input.csv
├── requirements.txt
└── README.md
```

The main responsibilities are separated as follows:

| File                 | Responsibility                                       |
| -------------------- | ---------------------------------------------------- |
| `app.py`             | Streamlit user interface and input/column mapping    |
| `calculator.py`      | Core effective-dose calculation logic                |
| `coefficients.py`    | Versioned coefficient tables and age-bin definitions |
| `io_utils.py`        | Input/output and file-handling utilities             |
| `test_calculator.py` | Automated validation tests                           |
| `sample_input.csv`   | Example/test input dataset                           |

## Current Limitations

Version 1 currently supports CT only.

The following functionality has not yet been implemented:

* **PET/CT** — CT dose component plus radiopharmaceutical dose estimation
* **Radiography** — DAP/KAP-based effective-dose estimation
* **Mammography** — AGD-based dose estimation
* ICRP 103-based coefficient tables
* Sex-stratified CT coefficients
* Fuzzy or automatic body-region matching
* Patient-specific organ dose estimation
* Individualized radiation-risk estimation

The PET/CT, radiography, and mammography calculators are intentionally not implemented as variations of the CT calculator because their dose metrics and calculation pipelines are structurally different.

## Future Development

Potential future extensions include:

1. Additional versioned CT coefficient tables, including ICRP 103-consistent approaches.
2. User-selectable coefficient methodologies.
3. Confirmable fuzzy suggestions for body-region mapping.
4. PET/CT effective-dose estimation using separate CT and radiopharmaceutical components.
5. Radiography effective-dose estimation based on DAP/KAP.
6. Mammography dose estimation based on average glandular dose.
7. Expanded automated validation against published reference cases.
8. Additional uncertainty and sensitivity analyses.

The architecture is intended to keep these extensions independent from the existing CT calculation core.

## References

1. European Commission. *European Guidelines on Quality Criteria for Computed Tomography*. EUR 16262 EN. Luxembourg: Office for Official Publications of the European Communities; 1999.

2. McCollough CH, Bushberg JT, Fletcher JG, Eckel LJ. *The Measurement, Reporting, and Management of Radiation Dose in CT*. AAPM Report No. 96. American Association of Physicists in Medicine; 2008. DOI: [10.37206/97](https://doi.org/10.37206/97).

3. International Commission on Radiological Protection. *1990 Recommendations of the International Commission on Radiological Protection*. ICRP Publication 60. Ann ICRP. 1991.

4. Deak PD, Smal Y, Kalender WA. Multisection CT protocols: sex- and age-specific conversion factors used to determine effective dose from dose-length product. *Radiology*. 2010;257(1):158–166. DOI: [10.1148/radiol.10100047](https://doi.org/10.1148/radiol.10100047).

## License

License information will be added before public release.

