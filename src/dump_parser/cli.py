"""Command-line entry point, built on Click.

Examples::

    # Full pipeline over a directory, CSV out
    dump-parser data/ -o out/results

    # Stage 1 only: search for a domain and dump matched lines
    dump-parser data/ -p '@blueshiftdefense.com' --stage1-only -o out/hits.csv

    # Stage 2 only: parse a previously saved Stage 1 dump
    dump-parser out/hits.csv --stage2-only -o out/parsed.csv

    # Intra-file parallelism on one huge file, one row per match
    dump-parser big.txt --blocksize 64MB --one-row-per-match -o out/r
"""

from __future__ import annotations

import os
import re
import sys
from re import Pattern

import click

from . import extractor, output, redact, scanner
from .models import ScanSummary

_EXAMPLES = """\b
Examples:
  dump-parser data/ -o out/results
  dump-parser data/ -p '@blueshiftdefense.com' --stage1-only -o out/hits.csv
  dump-parser out/hits.csv --stage2-only -o out/parsed.csv
  dump-parser big.txt --blocksize 64MB --one-row-per-match -o out/r
  dump-parser dumps/ -p 'ACCT\\d{6}' -p '(?i)password'
"""


class _BlockSizeParam(click.ParamType):
    """Click type for a human blocksize like ``64MB`` / ``16kb`` / ``1048576``."""

    name = "size"
    _UNITS = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3}

    def convert(self, value, param, ctx) -> int | None:
        if value is None:
            return None
        text = str(value).strip().upper()
        match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([KMG]?B)?", text)
        if not match:
            self.fail(f"invalid blocksize: {value!r}", param, ctx)
        assert match is not None  # self.fail() always raises
        number, unit = match.groups()
        return int(float(number) * self._UNITS[unit or "B"])


BLOCKSIZE = _BlockSizeParam()

NO_REDACT_WARNING = (
    "WARNING: --no-redact outputs plaintext credential-shaped data. Do not use "
    "this for demos, samples, or anything shared outside a live authorized "
    "engagement."
)


def _build_search_patterns(
    exprs: tuple[str, ...],
) -> list[tuple[str, Pattern[str]]] | None:
    if not exprs:
        return None
    return [(f"pattern_{i}", re.compile(e)) for i, e in enumerate(exprs)]


def _with_ext(base: str, ext: str) -> str:
    """Add ``ext`` to ``base`` unless it already ends with it."""

    return base if base.lower().endswith(ext) else base + ext


def _write_outputs(df, output_base: str | None) -> None:
    """Write ``df`` as CSV to a file (if ``output_base`` given) or stdout."""

    if output_base is None:
        df.to_csv(sys.stdout, index=False)
        return

    out_dir = os.path.dirname(output_base)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    output.write_csv(df, _with_ext(output_base, ".csv"))


@click.command(
    context_settings={"help_option_names": ["-h", "--help"]},
    epilog=_EXAMPLES,
)
@click.argument("input_path", metavar="INPUT")
@click.option(
    "-o",
    "--output",
    "output_base",
    help="Output path base; '.csv' is added if not already present "
    "(e.g. '-o out/r' -> out/r.csv). If omitted, results go to stdout as CSV.",
)
@click.option(
    "-p",
    "--pattern",
    "patterns",
    multiple=True,
    metavar="REGEX",
    help="Stage 1 search regex (repeatable). Default: any line containing an email, link, or custom token.",
)
@click.option(
    "--blocksize",
    type=BLOCKSIZE,
    default=None,
    help="Split large files into newline-aligned blocks of this size for "
    "intra-file parallelism, e.g. 64MB. Default: one task per file.",
)
@click.option(
    "--fallback-encoding",
    default="latin-1",
    show_default=True,
    help="Encoding used for lines that are not valid UTF-8.",
)
@click.option(
    "--scheduler",
    type=click.Choice(("threads", "processes", "synchronous")),
    default="processes",
    show_default=True,
    help="Dask scheduler. 'processes' gives true CPU parallelism for regex "
    "(the default, for PowerGREP-like speed); 'threads' mainly overlaps I/O.",
)
@click.option(
    "--one-row-per-match",
    is_flag=True,
    help="Emit one output row per individual match instead of pipe-joining multiple matches into a single cell.",
)
@click.option(
    "--stage1-only",
    is_flag=True,
    help="Run only Stage 1 (search) and dump matched lines.",
)
@click.option(
    "--stage2-only",
    is_flag=True,
    help="Run only Stage 2 (extraction) on a Stage 1 CSV dump.",
)
@click.option(
    "--redact/--no-redact",
    "redact_output",
    default=True,
    show_default=True,
    help="Hash custom_field_1/custom_field_2 tokens with a per-run salted "
    "HMAC-SHA256 and drop source_line from Stage 2 output. --no-redact emits "
    "plaintext and is for authorized live engagements only.",
)
@click.option(
    "--no-summary",
    is_flag=True,
    help="Suppress the summary report on stderr.",
)
def _cli(
    input_path: str,
    output_base: str | None,
    patterns: tuple[str, ...],
    blocksize: int | None,
    fallback_encoding: str,
    scheduler: str,
    one_row_per_match: bool,
    stage1_only: bool,
    stage2_only: bool,
    redact_output: bool,
    no_summary: bool,
) -> int:
    """Search large unstructured .txt dumps and extract fields by pattern
    (delimiter-agnostic), using Dask for parallel/out-of-core work.

    INPUT is a .txt file or a directory (searched recursively). With
    --stage2-only, INPUT is a Stage 1 CSV dump instead.
    """

    if stage1_only and stage2_only:
        raise click.UsageError("--stage1-only and --stage2-only are mutually exclusive")

    if not redact_output:
        print(NO_REDACT_WARNING, file=sys.stderr)

    compiled_patterns = _build_search_patterns(patterns)

    if stage2_only:
        # Input is a Stage 1 dump; skip scanning.
        matches = output.read_stage1(input_path)
        summary = ScanSummary(
            files_scanned=int(matches["file"].nunique()),
            lines_scanned=len(matches),
            stage1_matches=len(matches),
        )
    else:
        matches, summary = scanner.scan_paths(
            input_path,
            patterns=compiled_patterns,
            blocksize=blocksize,
            fallback_encoding=fallback_encoding,
            scheduler=scheduler,
        )

    if stage1_only:
        _write_outputs(matches, output_base)
    else:
        rows = extractor.build_stage2_frame(matches, one_row_per_match=one_row_per_match)
        summary.column_matches = output.count_column_matches(rows)
        if redact_output:
            # Rebind so the raw frame can't reach any writer below.
            rows = redact.redact_frame(rows, redact.generate_salt())
        _write_outputs(rows, output_base)

    if not no_summary:
        print(output.format_summary(summary), file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Programmatic entry point returning an exit code (0 on success).

    Runs the Click command with ``standalone_mode=False`` so it returns/raises
    instead of calling ``sys.exit`` itself, keeping this a plain callable for
    tests and other in-process callers.
    """

    try:
        return _cli.main(args=argv, standalone_mode=False) or 0
    except click.ClickException as exc:
        exc.show()
        return exc.exit_code
    except click.exceptions.Exit as exc:
        return exc.exit_code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
