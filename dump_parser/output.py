"""Output writers: CSV and a console summary report.

Writers take a :class:`pandas.DataFrame` directly and delegate to
``DataFrame.to_csv``, so serialisation is a single vectorized call rather than
a Python loop writing one row at a time.
"""

from __future__ import annotations

import pandas as pd

from .models import STAGE1_COLUMNS, ScanSummary
from .patterns import FIELD_PATTERNS


def write_csv(df: pd.DataFrame, path: str) -> None:
    df.to_csv(path, index=False)


def read_stage1(path: str) -> pd.DataFrame:
    """Load a Stage 1 CSV dump back into a DataFrame for ``--stage2-only``."""

    df = pd.read_csv(path, dtype={"matched_text": str, "pattern": str, "source_line": str})
    for col in STAGE1_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    return df[list(STAGE1_COLUMNS)].fillna("")


def count_column_matches(rows: pd.DataFrame) -> dict:
    """Count non-empty extracted values per column (splitting pipe-joined cells).

    Vectorized: for each field column, a non-empty cell's match count is
    ``1 + (number of '|' separators)``, computed for the whole column with a
    single ``Series.str.count`` call rather than a per-row split-and-len loop.
    """

    counts = {}
    for name in FIELD_PATTERNS:
        cell = rows[name]
        non_empty = cell != ""
        counts[name] = int((cell[non_empty].str.count(r"\|") + 1).sum())
    return counts


def format_summary(summary: ScanSummary) -> str:
    """Render the human-readable summary report."""

    lines = [
        "=" * 52,
        "  Dump Parser — Summary Report",
        "=" * 52,
        f"  Files scanned      : {summary.files_scanned}",
        f"  Lines scanned      : {summary.lines_scanned}",
        f"  Stage 1 matches    : {summary.stage1_matches}",
    ]
    if summary.column_matches:
        lines.append("  Matches per column :")
        for name, count in summary.column_matches.items():
            lines.append(f"      {name:<16}: {count}")
    lines.append(f"  Elapsed            : {summary.elapsed_seconds:.3f}s")

    if summary.fallback_files:
        lines.append(f"  Encoding fallback  : {len(summary.fallback_files)} file(s)")
        for path in summary.fallback_files:
            lines.append(f"      ! {path}")
    if summary.failed_files:
        lines.append(f"  Failed to read     : {len(summary.failed_files)} file(s)")
        for path, reason in summary.failed_files:
            lines.append(f"      x {path} ({reason})")
    lines.append("=" * 52)
    return "\n".join(lines)


def print_summary(summary: ScanSummary) -> None:
    print(format_summary(summary))
