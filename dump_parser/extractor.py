"""Stage 2 — parse matched lines into columns by pattern matching.

Every column is populated by scanning the *whole raw line* with the field's
regex (:mod:`dump_parser.patterns`), never by splitting on a delimiter. This
module operates on a :class:`pandas.DataFrame` of Stage 1 matches and applies
each field's regex as a single vectorized ``Series.str`` call across every row
at once, rather than looping over lines/patterns/matches in pure Python.
"""

from __future__ import annotations

import pandas as pd

from .models import OUTPUT_COLUMNS
from .patterns import FIELD_PATTERNS, strip_url

# Character used to join multiple matches within one cell.
MULTI_JOIN = "|"


def _dedup(values: list) -> list:
    """Order-preserving de-duplication of a single cell's match list."""

    return list(dict.fromkeys(values))


def extract_fields(source_lines: pd.Series) -> pd.DataFrame:
    """Vectorized extraction of every field from a Series of raw lines.

    Returns a DataFrame indexed like ``source_lines`` with one column per field
    in :data:`dump_parser.patterns.FIELD_PATTERNS`; each cell holds the ordered,
    de-duplicated list of matches found on that line (empty list if none).
    """

    columns: dict[str, pd.Series] = {}
    for name, pattern in FIELD_PATTERNS.items():
        # Series.str.findall runs the compiled regex over every row in one
        # vectorized pass instead of a Python-level loop calling `finditer`
        # per line.
        found = source_lines.str.findall(pattern)
        if name == "link":
            found = found.apply(lambda matches: [strip_url(m) for m in matches])
        columns[name] = found.apply(_dedup)
    return pd.DataFrame(columns, index=source_lines.index)


def build_stage2_frame(
        stage1_df: pd.DataFrame, one_row_per_match: bool = False
) -> pd.DataFrame:
    """Turn a Stage 1 matches DataFrame into the Stage 2 output DataFrame.

    Args:
        stage1_df: Columns ``file``, ``line_number``, ``source_line`` (as
            produced by :func:`dump_parser.scanner.scan_paths`).
        one_row_per_match: If False (default), emit one row per input line with
            each column's matches pipe-joined into a single cell. If True, emit
            the "long" form: one row per individual match via
            :meth:`pandas.DataFrame.explode`, with only that match's column
            populated.

    Returns:
        DataFrame with :data:`dump_parser.models.OUTPUT_COLUMNS`.
    """

    if stage1_df.empty:
        return pd.DataFrame(columns=list(OUTPUT_COLUMNS))

    base = stage1_df[["file", "line_number", "source_line"]].reset_index(drop=True)
    fields = extract_fields(base["source_line"])

    if not one_row_per_match:
        joined = fields.apply(lambda col: col.str.join(MULTI_JOIN))
        return pd.concat([base, joined], axis=1)[list(OUTPUT_COLUMNS)]

    return _explode_long(base, fields)


def _explode_long(base: pd.DataFrame, fields: pd.DataFrame) -> pd.DataFrame:
    """Build the one-row-per-match long form via melt + ``DataFrame.explode``.

    ``fields`` is reshaped wide-to-long (one row per original line per column
    per match, via :meth:`~pandas.DataFrame.melt` then
    :meth:`~pandas.Series.explode`) so every individual match becomes its own
    row without a manual per-match loop. Each result row has only its own
    column populated, matching the wide frame's column layout. A line with no
    matches in any column still contributes a single all-empty row so the
    source line is never silently dropped.
    """

    field_names = list(fields.columns)
    long = (
        fields.reset_index(names="_idx")
        .melt(id_vars="_idx", var_name="_column", value_name="_match")
        .explode("_match")
    )
    matched = long[long["_match"].notna() & (long["_match"] != "")]

    result = pd.DataFrame(index=matched.index)
    for name in field_names:
        result[name] = matched["_match"].where(matched["_column"] == name, "")
    result["_idx"] = matched["_idx"].to_numpy()
    result = result.merge(base.reset_index(names="_idx"), on="_idx", how="left")

    matched_idx = set(matched["_idx"].unique())
    empty_idx = [i for i in base.index if i not in matched_idx]
    if empty_idx:
        empty_rows = base.loc[empty_idx].reset_index(names="_idx")
        for name in field_names:
            empty_rows[name] = ""
        result = pd.concat([result, empty_rows], ignore_index=True)

    result = result.sort_values("_idx", kind="stable").drop(columns="_idx")
    result = result.reset_index(drop=True)
    return result[list(OUTPUT_COLUMNS)]
