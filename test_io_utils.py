"""
File-handling tests. Run with:  python3 test_io_utils.py

Covers the ways a user's file can differ from the happy path: delimiters,
encodings, multi-sheet workbooks, legacy .xls, duplicate headers, empty
files, column-name collisions and non-numeric text in numeric columns.
"""

import io
import shutil
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

from io_utils import (
    load_table, list_excel_sheets, find_collisions, to_numeric_with_report, to_download_bytes,
)


def expect_value_error(fn, *fragments):
    try:
        fn()
    except ValueError as e:
        for frag in fragments:
            assert frag.lower() in str(e).lower(), f"'{frag}' not in: {e}"
        return
    raise AssertionError("expected ValueError")


def test_csv_comma_and_semicolon_and_roundtrip():
    comma = b"id,age,dlp\n1,40,500\n2,50,600\n"
    df, info = load_table(io.BytesIO(comma), "a.csv")
    assert list(df.columns) == ["id", "age", "dlp"] and info["sep"] == ","

    semi = "id;age;dlp\n1;40;500\n2;50;600\n".encode()
    df, info = load_table(io.BytesIO(semi), "b.csv")
    assert list(df.columns) == ["id", "age", "dlp"] and info["sep"] == ";"
    assert df["dlp"].tolist() == [500, 600]

    out_bytes, out_name, mime = to_download_bytes(df.assign(result=[1.0, 2.0]), "b.csv", info)
    assert out_name == "b_with_effective_dose.csv" and mime == "text/csv"
    again, info2 = load_table(io.BytesIO(out_bytes), out_name)
    assert info2["sep"] == ";" and list(again.columns) == ["id", "age", "dlp", "result"]
    print("test_csv_comma_and_semicolon_and_roundtrip: PASS")


def test_csv_encodings():
    bom = "﻿id,name\n1,abc\n".encode("utf-8")
    df, info = load_table(io.BytesIO(bom), "bom.csv")
    assert list(df.columns) == ["id", "name"], df.columns          # BOM must not stick to 'id'

    cp = "id,name\n1,Müller\n".encode("cp1252")
    df, info = load_table(io.BytesIO(cp), "cp.csv")
    assert df.loc[0, "name"] == "Müller" and info["encoding"] == "cp1252"
    print("test_csv_encodings: PASS")


def test_bad_inputs_give_clear_errors():
    expect_value_error(lambda: load_table(io.BytesIO(b""), "e.csv"), "empty")
    expect_value_error(lambda: load_table(io.BytesIO(b"   \n"), "e.csv"), "empty")
    expect_value_error(lambda: load_table(io.BytesIO(b"a,b\n"), "h.csv"), "no data rows")
    expect_value_error(lambda: load_table(io.BytesIO(b"x"), "f.txt"), "unsupported")
    expect_value_error(lambda: load_table(io.BytesIO(b"not an excel file"), "f.xlsx"), "could not open")
    expect_value_error(lambda: load_table(io.BytesIO(b"a,a\n1,2\n"), "d.csv"), "duplicate")
    print("test_bad_inputs_give_clear_errors: PASS")


def test_excel_multi_sheet_and_selection():
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        pd.DataFrame({"a": [1, 2]}).to_excel(writer, index=False, sheet_name="first")
        pd.DataFrame({"b": [3, 4, 5]}).to_excel(writer, index=False, sheet_name="second")
    raw = buf.getvalue()

    assert list_excel_sheets(io.BytesIO(raw), "w.xlsx") == ["first", "second"]
    df, info = load_table(io.BytesIO(raw), "w.xlsx")                       # default: first sheet
    assert list(df.columns) == ["a"] and info["other_sheets"] == ["second"]
    df, info = load_table(io.BytesIO(raw), "w.xlsx", "second")
    assert list(df.columns) == ["b"] and len(df) == 3 and info["sheet"] == "second"
    expect_value_error(lambda: load_table(io.BytesIO(raw), "w.xlsx", "nope"), "not found")

    out_bytes, out_name, _ = to_download_bytes(df, "w.xlsx", info)
    assert out_name == "w_with_effective_dose.xlsx"
    assert list_excel_sheets(io.BytesIO(out_bytes), out_name) == ["second"]
    print("test_excel_multi_sheet_and_selection: PASS")


def test_legacy_xls_read_and_output_name():
    soffice = shutil.which("soffice")
    if not soffice:
        print("test_legacy_xls_read_and_output_name: SKIPPED (LibreOffice not installed)")
        return
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "legacy.csv"
        src.write_text("id,age,dlp\n1,40,500\n2,50,600\n")
        subprocess.run([soffice, "--headless", "--convert-to", "xls", "--outdir", tmp, str(src)],
                       check=True, capture_output=True, timeout=120)
        xls = Path(tmp) / "legacy.xls"
        assert xls.exists()
        df, info = load_table(io.BytesIO(xls.read_bytes()), "legacy.xls")
        assert list(df.columns) == ["id", "age", "dlp"] and df["dlp"].tolist() == [500, 600]
        _, out_name, _ = to_download_bytes(df, "legacy.xls", info)
        assert out_name == "legacy_with_effective_dose.xlsx"      # .xls cannot be written
    print("test_legacy_xls_read_and_output_name: PASS")


def test_unnamed_empty_columns_dropped_named_kept():
    csv = b"id,age,,notes\n1,40,,\n2,50,,\n"
    df, _ = load_table(io.BytesIO(csv), "u.csv")
    assert list(df.columns) == ["id", "age", "notes"], df.columns   # named-but-empty 'notes' is kept
    print("test_unnamed_empty_columns_dropped_named_kept: PASS")


def test_collisions():
    df = pd.DataFrame({"id": [1], "total_effective_dose_mSv": [3.0]})
    assert find_collisions(df, ["nm_effective_dose_mSv", "total_effective_dose_mSv"]) == ["total_effective_dose_mSv"]
    assert find_collisions(df, ["x", "y"]) == []
    print("test_collisions: PASS")


def test_numeric_report():
    s = pd.Series(["10", "20.5", "n/a", "1,5", None, 7])
    numeric, warning = to_numeric_with_report(s, "dlp")
    assert numeric.notna().sum() == 3                               # 10, 20.5 and 7 parse; the rest do not
    assert warning and "2 value(s)" in warning and "decimal comma" in warning, warning

    clean, warning = to_numeric_with_report(pd.Series([1, 2, None]), "dlp")
    assert warning is None                                          # genuine blanks are not 'non-numeric'
    print("test_numeric_report: PASS")


if __name__ == "__main__":
    test_csv_comma_and_semicolon_and_roundtrip()
    test_csv_encodings()
    test_bad_inputs_give_clear_errors()
    test_excel_multi_sheet_and_selection()
    test_legacy_xls_read_and_output_name()
    test_unnamed_empty_columns_dropped_named_kept()
    test_collisions()
    test_numeric_report()
    print("\nAll IO tests passed.")
