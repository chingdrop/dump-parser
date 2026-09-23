"""Tests for the default-on redaction of Stage 2 output."""

import pandas as pd

from dump_parser.models import OUTPUT_COLUMNS
from dump_parser.redact import generate_salt, redact_frame


def _frame(**cols):
    base = {c: [""] * len(next(iter(cols.values()))) for c in OUTPUT_COLUMNS}
    base.update(cols)
    return pd.DataFrame(base)[list(OUTPUT_COLUMNS)]


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
