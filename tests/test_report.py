"""Tests for the Markdown exposure/reuse report.

Inputs are already-redacted frames: token columns hold arbitrary fixed
hash-shaped strings, never real hashing. Assertions are purely structural.
"""

import pandas as pd

from dump_parser.models import ScanSummary
from dump_parser.report import build_report


def _frame(rows):
    cols = ["file", "line_number", "email", "link", "custom_field_1", "custom_field_2"]
    return pd.DataFrame(rows, columns=cols)


def _summary():
    return ScanSummary(files_scanned=2, lines_scanned=4, stage1_matches=4)


def test_no_reuse():
    df = _frame(
        [
            ["a.txt", 1, "u1@x.io", "", "hashAAAA", ""],
            ["a.txt", 2, "u2@x.io", "", "hashBBBB", ""],
        ]
    )
    out = build_report(df, _summary())
    assert "Distinct email addresses: 2" in out
    assert "Distinct email addresses with an associated token: 2" in out
    assert "No reuse clusters found" in out
    assert "0 of 2 accounts with any token (0.0%) participate" in out


def test_one_cluster_and_empty_token_and_multiple_files():
    df = _frame(
        [
            ["a.txt", 1, "u1@x.io", "", "shared01", ""],
            ["a.txt", 2, "u2@x.io", "", "shared01", ""],
            ["b.txt", 1, "u3@x.io", "", "", "solo99"],  # empty cf1 token
        ]
    )
    out = build_report(df, _summary())
    assert "Files contributing at least one row: 2" in out
    assert "Distinct email addresses: 3" in out
    # Two accounts share shared01 -> exactly one cluster of 2 in custom_field_1.
    assert "Cluster 1: 2 distinct accounts share a value" in out
    assert "Cluster 2" not in out
    # 2 of 3 accounts with a token are in a cluster (u3 has a token but no reuse).
    assert "2 of 3 accounts with any token (66.7%) participate" in out


def test_no_hash_or_email_value_leaks():
    df = _frame(
        [
            ["a.txt", 1, "u1@x.io", "", "shared01", ""],
            ["a.txt", 2, "u2@x.io", "", "shared01", ""],
        ]
    )
    out = build_report(df, _summary())
    assert "shared01" not in out
    assert "u1@x.io" not in out
    assert "u2@x.io" not in out


def test_pipe_joined_tokens_counted_per_token():
    df = _frame(
        [
            ["a.txt", 1, "u1@x.io", "", "tokAAAA|tokSHARED", ""],
            ["a.txt", 2, "u2@x.io", "", "tokSHARED|tokBBBB", ""],
        ]
    )
    out = build_report(df, _summary())
    # Only tokSHARED is reused across the two accounts.
    assert "Cluster 1: 2 distinct accounts share a value" in out
    assert "Cluster 2" not in out
