"""Output writers: CSV, JSON, and a console summary report."""

from __future__ import annotations

import csv
import json
from typing import Iterable, List, Sequence

from .models import OUTPUT_COLUMNS, ScanSummary, Stage1Match, Stage2Row
from .patterns import FIELD_PATTERNS


def write_stage2_csv(rows: Sequence[Stage2Row], path: str) -> None:
    """Write Stage 2 rows to ``path`` as CSV using :data:`OUTPUT_COLUMNS`."""

    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(OUTPUT_COLUMNS))
        writer.writeheader()
        for row in rows:
            writer.writerow(row.as_dict())


def write_stage2_json(rows: Sequence[Stage2Row], path: str) -> None:
    """Write Stage 2 rows to ``path`` as a JSON array of objects."""

    with open(path, "w", encoding="utf-8") as fh:
        json.dump([row.as_dict() for row in rows], fh, indent=2, ensure_ascii=False)


def write_stage1_csv(matches: Sequence[Stage1Match], path: str) -> None:
    """Write raw Stage 1 matches to ``path`` (used by ``--stage1-only``)."""

    fieldnames = ["file", "line_number", "matched_text", "pattern", "source_line"]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for m in matches:
            writer.writerow(m.as_dict())


def write_stage1_json(matches: Sequence[Stage1Match], path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump([m.as_dict() for m in matches], fh, indent=2, ensure_ascii=False)


def read_stage1(path: str) -> List[Stage1Match]:
    """Load a Stage 1 dump (CSV or JSON) back into records for ``--stage2-only``."""

    if path.lower().endswith(".json"):
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return [
            Stage1Match(
                file=d["file"],
                line_number=int(d["line_number"]),
                matched_text=d.get("matched_text", ""),
                pattern_name=d.get("pattern", ""),
                source_line=d["source_line"],
            )
            for d in data
        ]

    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        return [
            Stage1Match(
                file=row["file"],
                line_number=int(row["line_number"]),
                matched_text=row.get("matched_text", ""),
                pattern_name=row.get("pattern", ""),
                source_line=row["source_line"],
            )
            for row in reader
        ]


def count_column_matches(rows: Iterable[Stage2Row]) -> dict:
    """Count non-empty extracted values per column (splitting joined cells)."""

    counts = {name: 0 for name in FIELD_PATTERNS}
    for row in rows:
        for name in FIELD_PATTERNS:
            cell = getattr(row, name)
            if cell:
                counts[name] += len([v for v in cell.split("|") if v])
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
