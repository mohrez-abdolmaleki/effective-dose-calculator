"""
File loading and writing helpers.

Supports .csv, .xlsx, .xls. Deliberately thin -- the goal here is robust,
predictable error handling, not cleverness. Every function either returns
a usable result or raises an exception with a message a non-programmer
user (via the Streamlit UI) can act on.
"""

from pathlib import Path
import io

import pandas as pd


SUPPORTED_EXTENSIONS = {".csv", ".xlsx", ".xls"}


def load_table(file_obj, filename: str) -> pd.DataFrame:
    """Load an uploaded file (Streamlit UploadedFile or path-like) into a
    DataFrame. Raises ValueError with a user-facing message on failure.
    """
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type '{ext}'. Supported types: "
            f"{', '.join(sorted(SUPPORTED_EXTENSIONS))}."
        )

    try:
        if ext == ".csv":
            df = pd.read_csv(file_obj)
        else:  # .xlsx or .xls
            df = pd.read_excel(file_obj)
    except Exception as e:
        raise ValueError(
            f"Could not read '{filename}' as a {ext} file. "
            f"The file may be corrupted, password-protected, or not a "
            f"real {ext} despite its extension. Original error: {e}"
        )

    if df.empty:
        raise ValueError(f"'{filename}' was read successfully but contains no rows.")

    if df.shape[1] == 0:
        raise ValueError(f"'{filename}' was read successfully but contains no columns.")

    return df


def to_download_bytes(df: pd.DataFrame, original_filename: str) -> tuple[bytes, str, str]:
    """Serialize the annotated dataframe back to the same format as the
    input file. Returns (bytes, output_filename, mime_type).
    """
    ext = Path(original_filename).suffix.lower()
    stem = Path(original_filename).stem
    out_name = f"{stem}_with_effective_dose{ext}"

    if ext == ".csv":
        buf = io.StringIO()
        df.to_csv(buf, index=False)
        return buf.getvalue().encode("utf-8"), out_name, "text/csv"
    else:
        buf = io.BytesIO()
        # Always write .xlsx engine output even for .xls input, since pandas/
        # openpyxl do not support writing legacy .xls. Note this explicitly
        # rather than silently changing the extension.
        if ext == ".xls":
            out_name = f"{stem}_with_effective_dose.xlsx"
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="data")
        mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        return buf.getvalue(), out_name, mime
