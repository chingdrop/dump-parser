"""Shared schema and aggregate types passed between pipeline stages.

Records flow through the pipeline as :class:`pandas.DataFrame` objects rather
than per-row objects, so extraction and aggregation can be expressed as
vectorized ``Series``/``DataFrame`` operations instead of Python-level loops
over rows. These tuples define the column order each stage produces/expects.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Columns of the Stage 1 (search) result DataFrame.
STAGE1_COLUMNS: tuple[str, ...] = (
    "file",
    "line_number",
    "matched_text",
    "pattern",
    "source_line",
)

# Columns of the Stage 2 (extraction) output DataFrame — CSV header, JSON key
# order, console table order.
OUTPUT_COLUMNS: tuple[str, ...] = (
    "file",
    "line_number",
    "email",
    "link",
    "custom_field_1",
    "custom_field_2",
    "source_line",
)


@dataclass
class ScanSummary:
    """Aggregate statistics for a run, used to build the summary report."""

    files_scanned: int = 0
    lines_scanned: int = 0
    stage1_matches: int = 0
    # Per-column match totals for Stage 2, keyed by column name.
    column_matches: dict[str, int] = field(default_factory=dict)
    # (path, reason) for every file that could not be read.
    failed_files: list[tuple[str, str]] = field(default_factory=list)
    # Files that decoded only after falling back off UTF-8.
    fallback_files: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0
