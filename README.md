# dump-parser

A PowerGREP-style CLI for searching large, unstructured `.txt` dumps and
extracting fields **by pattern shape rather than by delimiter**. Built on
[Dask](https://www.dask.org/) (`dask.bag` / `dask.bytes`) for parallel,
out-of-core processing of multi-GB / many-file inputs.

## Why "delimiter-agnostic"?

The source lines are delimited inconsistently — the same field type can be
separated by a comma, a space, a pipe `|`, a colon `:`, or a mix, with no fixed
schema. So we never `str.split()` on a delimiter. Each line is treated as a raw
blob and every field is found by regex, anywhere on the line. See
[`patterns.py`](dump_parser/patterns.py) for the full rationale.

## Install

Dependencies are managed with [uv](https://docs.astral.sh/uv/):

```bash
uv sync
```

This creates `.venv/` and installs `dump_parser` plus its runtime and dev
dependencies (pinned in `uv.lock`). Prefix commands with `uv run`, or activate
the venv (`source .venv/bin/activate`) and drop the prefix.

## Usage

```bash
# Full pipeline over a directory (recursive), CSV + JSON output
uv run dump-parser sample_data -o out/results --format both

# Stage 1 only — dump the lines that matched, for later processing
uv run dump-parser sample_data --stage1-only -o out/hits.csv

# Stage 2 only — parse a previously saved Stage 1 dump into columns
uv run dump-parser out/hits.csv --stage2-only -o out/parsed.csv

# One huge file: split into 64 MB newline-aligned blocks for intra-file
# parallelism, and emit one row per individual match
uv run dump-parser big.txt --blocksize 64MB --one-row-per-match -o out/r

# Custom Stage 1 search patterns (repeatable); true CPU parallelism
uv run dump-parser dumps/ -p 'ACCT\d{6}' -p '(?i)password' --scheduler processes
```

`uv run python -m dump_parser ...` works identically to the `dump-parser`
console script above.

Results stream to stdout as CSV when `-o` is omitted. The summary report is
printed to stderr (suppress with `--no-summary`).

### Key flags

| Flag | Purpose |
|------|---------|
| `-p/--pattern REGEX` | Stage 1 search regex (repeatable). Default: any line with an email, link, or custom token. |
| `--blocksize 64MB` | Split large files into newline-aligned blocks for intra-file parallelism. Default: one task per file. |
| `--scheduler` | `threads` (default), `processes` (true CPU parallelism for regex), or `synchronous`. |
| `--one-row-per-match` | Emit one row per match instead of pipe-joining matches into a cell. |
| `--fallback-encoding` | Encoding for non-UTF-8 lines (default `latin-1`). |
| `--stage1-only` / `--stage2-only` | Run a single stage. |
| `--format csv\|json\|both` | Output format. |

## Output

Stage 2 columns: `file, line_number, email, link, custom_field_1,
custom_field_2, source_line`. A line with multiple matches for one category is
pipe-joined into the cell by default, or exploded with `--one-row-per-match`.

The summary report lists: files scanned, lines scanned, Stage 1 matches, matches
per column, elapsed time, files that needed an encoding fallback, and files that
failed to read.

## The four field patterns

| Column | Shape | Delimiter-safety |
|--------|-------|------------------|
| `email` | `local@domain.tld` | Char classes exclude `: , \| ` space, so a trailing `:` (e.g. `jane@acme.io:8080`) is never consumed. |
| `link` | `http(s)://…` or `www.…` | Anchored on the scheme, so a leading `\|` can't be part of it. Host stops at a delimiter `:`; a real `:port` is matched explicitly. Path/query/fragment stop at whitespace, `,`, `\|`, `:`. Trailing punctuation is stripped (balanced `)` preserved). |
| `custom_field_1` | `letters + digits + optional @`, e.g. `Eagles211@` | Left/right boundaries make it a standalone token under any delimiter. The trailing-`@` rule rejects email local parts (`Eagles211@acme.io` is *not* a token). |
| `custom_field_2` | same shape as field 1 | Separate compiled pattern; swap in a distinct regex without touching field 1. |

Run the pattern self-test / demo:

```bash
uv run python -m dump_parser.patterns
```

## How Dask splits large files (verified)

Stage 1 needs a correct **file + line number** per match. Two facts drove the
design:

1. **`dask.bag.read_text(blocksize=...)` never truncates a line.** Under the
   hood it calls `dask.bytes.read_bytes(delimiter=b"\n", blocksize=...)`, which
   advances each block boundary forward to the next newline. Verified
   empirically: 50 lines (~215 bytes each) read at a 64-byte blocksize came back
   intact, in order, and reassembled byte-for-byte.

2. **`read_text` doesn't expose a block's file/offset**, so per-file line
   numbers can't be recovered from it alone. The scanner therefore drives
   `read_bytes` directly (same newline-safe machinery), wraps the blocks into a
   `dask.bag` via `db.from_delayed`, and computes global line numbers with a
   cheap per-file prefix-sum of each block's line count.

Both read strategies produce identical results (tested):

* `blocksize=None` (default) — one streaming task per file, O(1) memory per
  file, parallel across files. Best for many files.
* `blocksize=<bytes>` — newline-aligned blocks per file, parallel *within* one
  large file. Best for a single multi-GB file.

> **Scheduler note.** `dask.bag` defaults to the multiprocessing scheduler,
> which requires an import-safe `__main__` entry point. This CLI provides one
> (`python -m dump_parser`). The library default is `threads` (safe everywhere);
> use `--scheduler processes` for true CPU-bound regex parallelism. Because
> Python's `re` holds the GIL, `threads` mainly overlaps I/O.

## Project layout

```
dump_parser/
  patterns.py    # regex definitions + delimiter-variant test cases + self-test
  scanner.py     # Stage 1 Dask pipeline (streaming + block-splitting)
  extractor.py   # Stage 2 pattern-based column extraction
  output.py      # CSV / JSON / console-summary writers
  models.py      # shared dataclasses + output schema
  cli.py         # argparse entry point (stage1-only / stage2-only / full)
tests/           # per-field regex tests + scanner + extractor + end-to-end
sample_data/     # mixed-delimiter samples (incl. a latin-1 file)
```

## Tests

```bash
uv run pytest -q
```

Covers every regex field across comma/space/pipe/colon/mixed delimiters,
delimiter-bleed regressions, block-vs-streaming equivalence, line-number
correctness, encoding fallback, unreadable-file handling, and an end-to-end
Stage 1 → Stage 2 → CSV/JSON run through the CLI.
