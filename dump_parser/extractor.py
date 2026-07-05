"""Stage 2 — parse a matched line into columns by pattern matching.

Every column is populated by scanning the *whole raw line* with the field's
regex (:mod:`dump_parser.patterns`), never by splitting on a delimiter. A line
may yield several matches for one category; by default they are joined with
``|`` into a single cell, or the row can be exploded into one row per match.
"""

from __future__ import annotations

from typing import Dict, List

from .models import Stage1Match, Stage2Row
from .patterns import FIELD_PATTERNS, strip_url

# Character used to join multiple matches within one cell.
MULTI_JOIN = "|"


def extract_fields(line: str) -> Dict[str, List[str]]:
    """Extract every field match from ``line``.

    Returns a dict keyed by column name (``email``, ``link``,
    ``custom_field_1``, ``custom_field_2``) whose values are the ordered,
    de-duplicated list of matched strings for that column.
    """

    results: Dict[str, List[str]] = {}
    for name, pattern in FIELD_PATTERNS.items():
        seen: List[str] = []
        for m in pattern.finditer(line):
            value = strip_url(m.group(0)) if name == "link" else m.group(0)
            if value and value not in seen:
                seen.append(value)
        results[name] = seen
    return results


def to_rows(match: Stage1Match, one_row_per_match: bool = False) -> List[Stage2Row]:
    """Turn a Stage 1 match into one or more Stage 2 output rows.

    Args:
        match: The captured line from Stage 1.
        one_row_per_match: If False (default), emit a single row whose cells hold
            all matches for each category pipe-joined. If True, emit the "long"
            form: one row per individual match, with only that match's column
            populated (useful for downstream per-value analysis).
    """

    fields = extract_fields(match.source_line)

    if not one_row_per_match:
        return [
            Stage2Row(
                file=match.file,
                line_number=match.line_number,
                email=MULTI_JOIN.join(fields["email"]),
                link=MULTI_JOIN.join(fields["link"]),
                custom_field_1=MULTI_JOIN.join(fields["custom_field_1"]),
                custom_field_2=MULTI_JOIN.join(fields["custom_field_2"]),
                source_line=match.source_line,
            )
        ]

    rows: List[Stage2Row] = []
    for column, values in fields.items():
        for value in values:
            rows.append(
                Stage2Row(
                    file=match.file,
                    line_number=match.line_number,
                    email=value if column == "email" else "",
                    link=value if column == "link" else "",
                    custom_field_1=value if column == "custom_field_1" else "",
                    custom_field_2=value if column == "custom_field_2" else "",
                    source_line=match.source_line,
                )
            )
    # A matched line with no extractable field still deserves a row so the source
    # line is not silently dropped.
    if not rows:
        rows.append(
            Stage2Row(
                file=match.file,
                line_number=match.line_number,
                email="",
                link="",
                custom_field_1="",
                custom_field_2="",
                source_line=match.source_line,
            )
        )
    return rows


def extract_all(
    matches: List[Stage1Match], one_row_per_match: bool = False
) -> List[Stage2Row]:
    """Run :func:`to_rows` across every Stage 1 match, preserving order."""

    rows: List[Stage2Row] = []
    for match in matches:
        rows.extend(to_rows(match, one_row_per_match=one_row_per_match))
    return rows
