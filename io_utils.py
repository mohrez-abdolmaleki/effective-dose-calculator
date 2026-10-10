"""
File loading and writing helpers.

Supports .csv, .xlsx, .xls. The goal is predictable, explainable behaviour:
every function either returns a usable result or raises ValueError with a
message a non-programmer can act on.

Things this layer handles on purpose (each was a way the "your file is
updated" promise could silently break):
  - CSV encodings: UTF-8 (with or without BOM) and Windows cp1252 exports.
  - CSV delimiters: comma, semicolon, tab, pipe (semicolon is the default
    export in many locales, where a comma is the decimal mark).
  - Multi-sheet Excel workbooks: the user picks the sheet; the output file
    contains that sheet only, and the app says so.
  - Legacy .xls: readable (needs xlrd) but NOT writable by modern pandas, so
    the output is a .xlsx and the file name says so.
  - Column-name collisions: result columns must never overwrite a user's
    column of the same name (see find_collisions).
  - Non-numeric text in a numeric column (see to_numeric_with_report).
"""

import csv
import io
from pathlib import Path

import pandas as pd


SUPPORTED_EXTENSIONS = {".csv", ".xlsx", ".xls"}
_CSV_ENCODINGS = ("utf-8-sig", "cp1252")
_CSV_DELIMITERS = ",;\t|"


def _check_duplicate_headers(names):
    """pandas silently renames duplicate headers ('a', 'a.1'), which would change
    the user's column names in the output file. Check the RAW header instead."""
    cleaned = [str(n).strip() for n in names if n is not None and str(n).strip() not in ("", "nan")]
    dupes = sorted({n for n in cleaned if cleaned.count(n) > 1})
    if dupes:
        raise ValueError(
            f"Duplicate column names found: {dupes}. Rename them so every column is unique, "
            "then upload again."
        )


def _read_bytes(file_obj) -> bytes:
    raw = file_obj.read()
    if hasattr(file_obj, "seek"):
        file_obj.seek(0)
    return raw.encode("utf-8") if isinstance(raw, str) else raw


def list_excel_sheets(file_obj, filename: str) -> list:
    """Sheet names of an Excel workbook; [] for CSV. Raises ValueError if unreadable."""
    ext = Path(filename).suffix.lower()
    if ext not in (".xlsx", ".xls"):
        return []
    try:
        names = pd.ExcelFile(io.BytesIO(_read_bytes(file_obj))).sheet_names
    except ImportError as e:
        raise ValueError(
            f"Reading '{ext}' files needs an extra package ({e}). "
            "Install the requirements (pip install -r requirements.txt)."
        )
    except Exception as e:
        raise ValueError(
            f"Could not open '{filename}' as an Excel workbook. It may be corrupted, "
            f"password-protected, or not a real {ext} file. Original error: {e}"
        )
    return names


def load_table(file_obj, filename: str, sheet_name=None):
    """Load an uploaded file. Returns (DataFrame, info dict).

    info keys: format, sep (CSV), encoding (CSV), sheet (Excel), other_sheets (Excel).
    """
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type '{ext}'. Supported types: "
            f"{', '.join(sorted(SUPPORTED_EXTENSIONS))}."
        )

    raw = _read_bytes(file_obj)
    if not raw.strip():
        raise ValueError(f"'{filename}' is empty.")

    info = {"format": ext.lstrip(".")}

    if ext == ".csv":
        text, used_encoding = None, None
        for enc in _CSV_ENCODINGS:
            try:
                text, used_encoding = raw.decode(enc), enc
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            text, used_encoding = raw.decode("latin-1"), "latin-1"

        sample = text[:8192]
        try:
            sep = csv.Sniffer().sniff(sample, delimiters=_CSV_DELIMITERS).delimiter
        except csv.Error:
            sep = ","
        _check_duplicate_headers(next(csv.reader(io.StringIO(text), delimiter=sep), []))
        try:
            df = pd.read_csv(io.StringIO(text), sep=sep)
        except Exception as e:
            raise ValueError(
                f"Could not read '{filename}' as a CSV file (tried delimiter {sep!r}, "
                f"encoding {used_encoding}). Original error: {e}"
            )
        info.update(sep=sep, encoding=used_encoding)
    else:
        names = list_excel_sheets(io.BytesIO(raw), filename)
        if not names:
            raise ValueError(f"'{filename}' contains no sheets.")
        chosen = names[0] if sheet_name is None else sheet_name
        if chosen not in names:
            raise ValueError(f"Sheet '{chosen}' not found in '{filename}'. Sheets: {names}")
        try:
            raw_header = pd.read_excel(io.BytesIO(raw), sheet_name=chosen, header=None, nrows=1)
            if len(raw_header):
                _check_duplicate_headers(raw_header.iloc[0].tolist())
        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f"Could not read sheet '{chosen}' of '{filename}'. Original error: {e}")
        try:
            df = pd.read_excel(io.BytesIO(raw), sheet_name=chosen)
        except Exception as e:
            raise ValueError(f"Could not read sheet '{chosen}' of '{filename}'. Original error: {e}")
        info.update(sheet=chosen, other_sheets=[n for n in names if n != chosen])

    # Drop columns that are completely empty AND unnamed (stray Excel/CSV artefacts);
    # never touch named columns or any data.
    unnamed_empty = [c for c in df.columns if str(c).startswith("Unnamed:") and df[c].isna().all()]
    if unnamed_empty:
        df = df.drop(columns=unnamed_empty)

    if df.shape[1] == 0:
        raise ValueError(f"'{filename}' was read but contains no usable columns.")
    if df.empty:
        raise ValueError(
            f"'{filename}' has a header row but no data rows."
        )
    if df.columns.duplicated().any():
        dupes = sorted({str(c) for c in df.columns[df.columns.duplicated()]})
        raise ValueError(
            f"Duplicate column names found: {dupes}. Rename them so every column is unique, then upload again."
        )

    df.columns = [str(c) for c in df.columns]
    return df, info


def find_collisions(df: pd.DataFrame, new_columns) -> list:
    """Names in `new_columns` that already exist in df (they would be overwritten)."""
    existing = set(df.columns)
    return [c for c in new_columns if c in existing]


def to_numeric_with_report(series: pd.Series, label: str):
    """Convert to numbers; returns (numeric_series, warning_or_None).

    Text that cannot be parsed becomes NaN (so the row is flagged as missing),
    but the user is told how many such cells there were, with examples, and a
    hint when they look like decimal commas -- instead of a bare "missing".
    """
    numeric = pd.to_numeric(series, errors="coerce")
    bad_mask = series.notna() & numeric.isna()
    n_bad = int(bad_mask.sum())
    if n_bad == 0:
        return numeric, None

    examples = [repr(v) for v in series[bad_mask].astype(str).unique()[:4]]
    msg = (
        f"{n_bad} value(s) in column '{label}' are not numbers (e.g. {', '.join(examples)}) "
        "and were treated as missing."
    )
    if series[bad_mask].astype(str).str.fullmatch(r"\s*\d+,\d+\s*").any():
        msg += " Some use a decimal comma (e.g. '1,5'); replace it with a decimal point."
    return numeric, msg


def to_download_bytes(df: pd.DataFrame, original_filename: str, info: dict):
    """Serialize the annotated dataframe. Returns (bytes, output_filename, mime)."""
    ext = Path(original_filename).suffix.lower()
    stem = Path(original_filename).stem

    if ext == ".csv":
        out_name = f"{stem}_with_effective_dose.csv"
        text = df.to_csv(index=False, sep=info.get("sep", ","))
        # BOM so Excel opens non-ASCII text correctly; same delimiter as the input.
        return text.encode("utf-8-sig"), out_name, "text/csv"

    # .xlsx and .xls both leave as .xlsx (modern pandas cannot write legacy .xls).
    out_name = f"{stem}_with_effective_dose.xlsx"
    sheet = str(info.get("sheet", "data"))[:31] or "data"
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet)
    mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return buf.getvalue(), out_name, mime
