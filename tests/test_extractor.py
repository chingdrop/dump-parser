"""Stage 2 extraction tests: joining, exploding, dedup, delimiter-agnostic input."""

import pandas as pd

from dump_parser.extractor import build_stage2_frame, extract_fields


def _stage1_df(lines):
    return pd.DataFrame(
        {
            "file": ["f.txt"] * len(lines),
            "line_number": list(range(1, len(lines) + 1)),
            "matched_text": [""] * len(lines),
            "pattern": ["any-field"] * len(lines),
            "source_line": lines,
        }
    )


def test_extract_fields_mixed_delimiters():
    line = "jane@acme.io,https://acme.io/p|Eagles211@ Falcons88"
    fields = extract_fields(pd.Series([line]))
    assert fields["email"].iloc[0] == ["jane@acme.io"]
    assert fields["link"].iloc[0] == ["https://acme.io/p"]
    assert fields["custom_field_1"].iloc[0] == ["Eagles211@", "Falcons88"]


def test_joined_row_pipe_delimits_multiple():
    df = build_stage2_frame(_stage1_df(["a@x.io b@y.io Eagles211@ Falcons88"]))
    assert len(df) == 1
    assert df.iloc[0]["email"] == "a@x.io|b@y.io"
    assert df.iloc[0]["custom_field_1"] == "Eagles211@|Falcons88"


def test_dedup_within_cell():
    df = build_stage2_frame(_stage1_df(["a@x.io, a@x.io, Colts03@, Colts03@"]))
    assert df.iloc[0]["email"] == "a@x.io"
    assert df.iloc[0]["custom_field_1"] == "Colts03@"


def test_one_row_per_match_explodes():
    df = build_stage2_frame(_stage1_df(["a@x.io https://x.io/p Eagles211@"]), one_row_per_match=True)
    values = set(zip(df["email"], df["link"], df["custom_field_1"], df["custom_field_2"], strict=True))
    assert ("a@x.io", "", "", "") in values
    assert ("", "https://x.io/p", "", "") in values
    assert ("", "", "Eagles211@", "") in values


def test_matched_line_without_fields_still_yields_row():
    df = build_stage2_frame(_stage1_df(["nothing extractable here"]), one_row_per_match=True)
    assert len(df) == 1
    assert df.iloc[0]["source_line"] == "nothing extractable here"


def test_extract_all_preserves_order():
    df = build_stage2_frame(_stage1_df(["a@x.io", "b@y.io"]))
    assert list(df["email"]) == ["a@x.io", "b@y.io"]


def test_empty_input_yields_empty_frame_with_columns():
    df = build_stage2_frame(_stage1_df([]))
    assert list(df.columns) == [
        "file",
        "line_number",
        "email",
        "link",
        "custom_field_1",
        "custom_field_2",
        "source_line",
    ]
    assert len(df) == 0
