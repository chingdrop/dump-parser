"""Tests for the default-on redaction of Stage 1/Stage 2 output."""

import pandas as pd

from dump_parser.models import OUTPUT_COLUMNS, STAGE1_COLUMNS
from dump_parser.redact import generate_salt, redact_frame, redact_stage1_frame


def _frame(**cols):
    base = {c: [""] * len(next(iter(cols.values()))) for c in OUTPUT_COLUMNS}
    base.update(cols)
    return pd.DataFrame(base)[list(OUTPUT_COLUMNS)]


def _stage1_frame(**cols):
    base = {c: [""] * len(next(iter(cols.values()))) for c in STAGE1_COLUMNS}
    base.update(cols)
    return pd.DataFrame(base)[list(STAGE1_COLUMNS)]


def test_same_input_same_hash_within_one_salt():
    salt = generate_salt()
    df = _frame(custom_field_1=["Eagles211@", "Eagles211@"])
    out = redact_frame(df, salt)
    assert out["custom_field_1"].iloc[0] == out["custom_field_1"].iloc[1]
    assert out["custom_field_1"].iloc[0] != "Eagles211@"


def test_different_salts_differ():
    df = _frame(custom_field_1=["Eagles211@"])
    a = redact_frame(df, generate_salt())["custom_field_1"].iloc[0]
    b = redact_frame(df, generate_salt())["custom_field_1"].iloc[0]
    assert a != b


def test_empty_cells_stay_empty():
    salt = generate_salt()
    out = redact_frame(_frame(custom_field_1=["", "Falcons88"]), salt)
    assert out["custom_field_1"].iloc[0] == ""
    assert out["custom_field_1"].iloc[1] != ""


def test_multi_token_cells_hashed_independently():
    salt = generate_salt()
    df = _frame(custom_field_1=["Eagles211@|Falcons88"])
    out = redact_frame(df, salt)["custom_field_1"].iloc[0]
    parts = out.split("|")
    assert len(parts) == 2
    assert parts[0] != parts[1]
    # Each piece matches the same token hashed alone.
    solo = redact_frame(_frame(custom_field_1=["Eagles211@", "Falcons88"]), salt)["custom_field_1"]
    assert parts == [solo.iloc[0], solo.iloc[1]]


def test_source_line_dropped():
    out = redact_frame(_frame(source_line=["raw secret line"]), generate_salt())
    assert "source_line" not in out.columns


def test_email_and_link_pass_through():
    df = _frame(email=["jane@acme.io"], link=["https://acme.io/p"])
    out = redact_frame(df, generate_salt())
    assert out["email"].iloc[0] == "jane@acme.io"
    assert out["link"].iloc[0] == "https://acme.io/p"


def test_both_token_columns_redacted():
    salt = generate_salt()
    out = redact_frame(_frame(custom_field_1=["Bears00@"], custom_field_2=["Lions55"]), salt)
    assert out["custom_field_1"].iloc[0] not in ("", "Bears00@")
    assert out["custom_field_2"].iloc[0] not in ("", "Lions55")


# --- Stage 1 ---------------------------------------------------------------


def test_stage1_source_line_dropped():
    out = redact_stage1_frame(_stage1_frame(source_line=["raw secret line"]), generate_salt())
    assert "source_line" not in out.columns


def test_stage1_email_matched_text_passes_through():
    out = redact_stage1_frame(_stage1_frame(matched_text=["jane@acme.io"]), generate_salt())
    assert out["matched_text"].iloc[0] == "jane@acme.io"


def test_stage1_link_matched_text_passes_through():
    out = redact_stage1_frame(_stage1_frame(matched_text=["https://acme.io/p"]), generate_salt())
    assert out["matched_text"].iloc[0] == "https://acme.io/p"


def test_stage1_non_exposure_matched_text_hashed():
    salt = generate_salt()
    out = redact_stage1_frame(_stage1_frame(matched_text=["Eagles211@"]), salt)
    assert out["matched_text"].iloc[0] not in ("", "Eagles211@")


def test_stage1_same_token_same_hash_within_one_salt():
    salt = generate_salt()
    out = redact_stage1_frame(_stage1_frame(matched_text=["Eagles211@", "Eagles211@"]), salt)
    assert out["matched_text"].iloc[0] == out["matched_text"].iloc[1]


def test_stage1_empty_matched_text_stays_empty():
    out = redact_stage1_frame(_stage1_frame(matched_text=["", "Eagles211@"]), generate_salt())
    assert out["matched_text"].iloc[0] == ""
    assert out["matched_text"].iloc[1] != ""


def test_stage1_file_line_pattern_unchanged():
    df = _stage1_frame(file=["a.txt"], line_number=[3], pattern=["any-field"], matched_text=["Eagles211@"])
    out = redact_stage1_frame(df, generate_salt())
    assert out["file"].iloc[0] == "a.txt"
    assert out["line_number"].iloc[0] == 3
    assert out["pattern"].iloc[0] == "any-field"
