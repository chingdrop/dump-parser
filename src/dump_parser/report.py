"""Minimal Markdown exposure / reuse report.

:func:`build_report` only ever receives the *already-redacted* Stage 2 frame
(see :func:`dump_parser.redact.redact_frame`), so it can't leak anything the
CSV output doesn't already contain. It emits aggregate counts only: no email,
token, or hash value is ever printed.

Works on both the wide (pipe-joined) and ``--one-row-per-match`` long forms:
every cell is melted and exploded to one value per row, and emails are
re-associated with tokens by ``(file, line_number)``, which both forms share.
"""

from __future__ import annotations

import pandas as pd

from .extractor import MULTI_JOIN
from .models import ScanSummary
from .redact import TOKEN_COLUMNS

_KEYS = ["file", "line_number"]


def _long_values(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """One row per individual non-empty value: ``file, line_number, column, value``."""

    long = df[_KEYS + columns].melt(id_vars=_KEYS, var_name="column", value_name="value")
    long["value"] = long["value"].fillna("").astype(str).str.split(MULTI_JOIN, regex=False)
    long = long.explode("value")
    return long[long["value"] != ""].reset_index(drop=True)


def _account_token_pairs(df: pd.DataFrame) -> tuple[pd.Series, pd.DataFrame]:
    """Return (distinct emails, ``column, token, email`` pairs from the same line)."""

    long = _long_values(df, ["email", *TOKEN_COLUMNS])
    emails = long.loc[long["column"] == "email", [*_KEYS, "value"]].rename(columns={"value": "email"})
    tokens = long.loc[long["column"] != "email", [*_KEYS, "column", "value"]].rename(columns={"value": "token"})
    pairs = tokens.merge(emails, on=_KEYS)[["column", "token", "email"]].drop_duplicates()
    return emails["email"].drop_duplicates(), pairs


def _pct(part: int, whole: int) -> str:
    return f"{100 * part / whole:.1f}%" if whole else "n/a"


def build_report(redacted_df: pd.DataFrame, summary: ScanSummary) -> str:
    """Render the Exposure Summary + Password Reuse report as Markdown."""

    emails, pairs = _account_token_pairs(redacted_df)
    accounts_with_token = int(pairs["email"].nunique())

    lines = [
        "# Exposure Report",
        "",
        "## Exposure Summary",
        "",
        f"- Files scanned: {summary.files_scanned}",
        f"- Lines scanned: {summary.lines_scanned}",
        f"- Files contributing at least one row: {int(redacted_df['file'].nunique())}",
        f"- Distinct email addresses: {len(emails)}",
        f"- Distinct email addresses with an associated token: {accounts_with_token}",
        "",
        "## Password Reuse",
        "",
    ]

    # Distinct accounts per (column, hashed token), broadcast back onto every
    # pair so reused accounts can be selected without a loop.
    pairs["accounts"] = pairs.groupby(["column", "token"])["email"].transform("nunique")
    reused = pairs[pairs["accounts"] >= 2]

    for column in TOKEN_COLUMNS:
        sizes = (
            reused[reused["column"] == column]
            .drop_duplicates(["token"])["accounts"]
            .sort_values(ascending=False, kind="stable")
            .reset_index(drop=True)
        )
        lines.append(f"### {column}")
        lines.append("")
        if sizes.empty:
            lines.append("No reuse clusters found (no value is shared by 2+ distinct accounts).")
        else:
            lines.extend(f"- Cluster {i}: {n} distinct accounts share a value" for i, n in enumerate(sizes, 1))
        lines.append("")

    in_cluster = int(reused["email"].nunique())
    lines.append(
        f"**{in_cluster} of {accounts_with_token} accounts with any token "
        f"({_pct(in_cluster, accounts_with_token)}) participate in a reuse cluster.**"
    )
    return "\n".join(lines) + "\n"
