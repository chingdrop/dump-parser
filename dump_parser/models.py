"""Shared data structures passed between the scanner, extractor and writers.

Keeping the records in one place means Stage 1 (search) and Stage 2 (column
extraction) agree on field names, and the output writers have a single schema to
serialise.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass
class Stage1Match:
    """A single line that matched one of the Stage 1 search patterns.

    Attributes:
        file: Absolute or relative path of the source file.
        line_number: 1-based line number within ``file``.
        matched_text: The substring that satisfied the search pattern.
        pattern_name: Name of the search pattern that hit.
        source_line: The full, untruncated source line (newline stripped).
    """

    file: str
    line_number: int
    matched_text: str
    pattern_name: str
    source_line: str

    def as_dict(self) -> Dict[str, object]:
        return {
            "file": self.file,
            "line_number": self.line_number,
            "matched_text": self.matched_text,
            "pattern": self.pattern_name,
            "source_line": self.source_line,
        }


@dataclass
class Stage2Row:
    """A parsed output row: one source line split into pattern-matched columns.

    Each column holds the extracted value(s). When a line yields several matches
    for one category they are pipe-joined by default (see
    :func:`dump_parser.extractor.to_rows`), or exploded into multiple rows.
    """

    file: str
    line_number: int
    email: str
    link: str
    custom_field_1: str
    custom_field_2: str
    source_line: str

    def as_dict(self) -> Dict[str, object]:
        return {
            "file": self.file,
            "line_number": self.line_number,
            "email": self.email,
            "link": self.link,
            "custom_field_1": self.custom_field_1,
            "custom_field_2": self.custom_field_2,
            "source_line": self.source_line,
        }


# Column order used by every writer (CSV header, JSON key order, console table).
OUTPUT_COLUMNS: Tuple[str, ...] = (
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
    column_matches: Dict[str, int] = field(default_factory=dict)
    # (path, reason) for every file that could not be read.
    failed_files: List[Tuple[str, str]] = field(default_factory=list)
    # Files that decoded only after falling back off UTF-8.
    fallback_files: List[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0
