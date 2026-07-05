"""Command-line entry point.

Examples::

    # Full pipeline over a directory, CSV + JSON out
    python -m dump_parser data/ -o out/results --format both

    # Stage 1 only: dump matched lines for later processing
    python -m dump_parser data/ --stage1-only -o out/hits.csv

    # Stage 2 only: parse a previously saved Stage 1 dump
    python -m dump_parser out/hits.csv --stage2-only -o out/parsed.csv

    # Intra-file parallelism on one huge file, one row per match
    python -m dump_parser big.txt --blocksize 64MB --one-row-per-match -o out/r
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from typing import List, Optional, Pattern, Tuple

from . import extractor, output, scanner
from .models import ScanSummary


def _parse_blocksize(value: Optional[str]) -> Optional[int]:
    """Parse a human blocksize like ``64MB`` / ``16kb`` / ``1048576`` into bytes."""

    if value is None:
        return None
    text = value.strip().upper()
    units = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3}
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([KMG]?B)?", text)
    if not match:
        raise argparse.ArgumentTypeError(f"invalid blocksize: {value!r}")
    number, unit = match.groups()
    return int(float(number) * units[unit or "B"])


def _build_search_patterns(
    exprs: Optional[List[str]],
) -> Optional[List[Tuple[str, Pattern[str]]]]:
    if not exprs:
        return None
    return [(f"pattern_{i}", re.compile(e)) for i, e in enumerate(exprs)]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dump_parser",
        description="Search large unstructured .txt dumps and extract fields by "
        "pattern (delimiter-agnostic), using Dask for parallel/out-of-core work.",
    )
    parser.add_argument(
        "input",
        help="A .txt file or a directory (searched recursively). For "
        "--stage2-only, a Stage 1 CSV/JSON dump instead.",
    )
    parser.add_argument(
        "-o", "--output",
        help="Output path base. Extension is added per format "
        "(e.g. '-o out/r' -> out/r.csv, out/r.json). If omitted, results go to "
        "stdout as CSV.",
    )
    parser.add_argument(
        "--format",
        choices=("csv", "json", "both"),
        default="csv",
        help="Output format (default: csv).",
    )
    parser.add_argument(
        "-p", "--pattern",
        action="append",
        metavar="REGEX",
        help="Stage 1 search regex (repeatable). Default: any line containing "
        "an email, link, or custom token.",
    )
    parser.add_argument(
        "--blocksize",
        type=_parse_blocksize,
        default=None,
        help="Split large files into newline-aligned blocks of this size for "
        "intra-file parallelism, e.g. 64MB. Default: one task per file.",
    )
    parser.add_argument(
        "--fallback-encoding",
        default="latin-1",
        help="Encoding used for lines that are not valid UTF-8 (default: latin-1).",
    )
    parser.add_argument(
        "--scheduler",
        choices=("threads", "processes", "synchronous"),
        default="threads",
        help="Dask scheduler (default: threads). 'processes' gives true CPU "
        "parallelism for regex.",
    )
    parser.add_argument(
        "--one-row-per-match",
        action="store_true",
        help="Emit one output row per individual match instead of pipe-joining "
        "multiple matches into a single cell.",
    )
    stage = parser.add_mutually_exclusive_group()
    stage.add_argument(
        "--stage1-only", action="store_true",
        help="Run only Stage 1 (search) and dump matched lines.",
    )
    stage.add_argument(
        "--stage2-only", action="store_true",
        help="Run only Stage 2 (extraction) on a Stage 1 CSV/JSON dump.",
    )
    parser.add_argument(
        "--no-summary", action="store_true",
        help="Suppress the summary report on stderr.",
    )
    return parser


def _write_outputs(
    args: argparse.Namespace,
    *,
    stage1_matches=None,
    stage2_rows=None,
) -> None:
    """Write results to files (if -o given) or stdout (CSV)."""

    if args.output is None:
        # Stream CSV to stdout.
        import csv as _csv

        if stage1_matches is not None:
            writer = _csv.DictWriter(
                sys.stdout,
                fieldnames=["file", "line_number", "matched_text", "pattern", "source_line"],
            )
            writer.writeheader()
            for m in stage1_matches:
                writer.writerow(m.as_dict())
        else:
            from .models import OUTPUT_COLUMNS

            writer = _csv.DictWriter(sys.stdout, fieldnames=list(OUTPUT_COLUMNS))
            writer.writeheader()
            for row in stage2_rows:
                writer.writerow(row.as_dict())
        return

    base = args.output
    out_dir = os.path.dirname(base)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    want_csv = args.format in ("csv", "both")
    want_json = args.format in ("json", "both")

    if stage1_matches is not None:
        if want_csv:
            output.write_stage1_csv(stage1_matches, _with_ext(base, ".csv"))
        if want_json:
            output.write_stage1_json(stage1_matches, _with_ext(base, ".json"))
    else:
        if want_csv:
            output.write_stage2_csv(stage2_rows, _with_ext(base, ".csv"))
        if want_json:
            output.write_stage2_json(stage2_rows, _with_ext(base, ".json"))


def _with_ext(base: str, ext: str) -> str:
    """Add ``ext`` to ``base`` unless it already ends with it."""

    return base if base.lower().endswith(ext) else base + ext


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    patterns = _build_search_patterns(args.pattern)

    if args.stage2_only:
        # Input is a Stage 1 dump; skip scanning.
        matches = output.read_stage1(args.input)
        summary = ScanSummary(
            files_scanned=len({m.file for m in matches}),
            lines_scanned=len(matches),
            stage1_matches=len(matches),
        )
    else:
        matches, summary = scanner.scan_paths(
            args.input,
            patterns=patterns,
            blocksize=args.blocksize,
            fallback_encoding=args.fallback_encoding,
            scheduler=args.scheduler,
        )

    if args.stage1_only:
        _write_outputs(args, stage1_matches=matches)
    else:
        rows = extractor.extract_all(matches, one_row_per_match=args.one_row_per_match)
        summary.column_matches = output.count_column_matches(rows)
        _write_outputs(args, stage2_rows=rows)

    if not args.no_summary:
        print(output.format_summary(summary), file=sys.stderr)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
