# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Dependencies are managed with `uv`. The package lives under `src/dump_parser`
(src layout); tests stay flat under `tests/`.

```bash
uv sync                                    # install/update the venv from uv.lock
uv run pytest -q                           # run the full test suite
uv run pytest tests/test_patterns.py -q    # run one test file
uv run pytest tests/test_scanner.py::test_blockwise_matches_streaming -q  # single test
uv run python -m dump_parser.patterns      # regex self-test/demo (pass/fail per case, no pytest)
uv run dump-parser sample_data -o out/results   # run the CLI (installed console script)
uv run python -m dump_parser ...                # equivalent, no console script needed
uv run ruff check src tests                # lint
uv run ruff format src tests               # format
uv run mypy src/dump_parser                # type check
uv run pre-commit run --all-files          # run all pre-commit hooks locally
```

`dump-parser` and `python -m dump_parser` are both required to work — the
multiprocessing scheduler re-imports the entry module in worker processes, so
any new entry point must stay behind an `if __name__ == "__main__":` guard.

CI (`.github/workflows/ci.yml`) runs `lint` (ruff check, ruff format --check,
mypy), `test` (pytest), and `build` (`uv build`) as separate jobs against
Python 3.10 (the `requires-python` floor) on every push to `main` and PR.
`mypy`'s own `python_version` is pinned to 3.12 in `pyproject.toml` — that's
unrelated to the 3.10 runtime floor; numpy's stubs use PEP 695 `type`
statements that mypy can only parse under 3.12+, so this is a static-analysis
workaround, not a support-matrix change. The `.pre-commit-config.yaml` mypy
hook runs in an isolated env with only `pandas-stubs` installed (not the full
project) — code that relies on a dependency's typed `NoReturn` (e.g. a
validator's `self.fail()`) needs an explicit `assert` afterward, since mypy
can silently lose that narrowing when the dependency itself isn't resolvable
in that isolated environment (see `cli.py`'s `_BlockSizeParam.convert`).

## Architecture

Three-stage pipeline, each stage boundary is a `pandas.DataFrame` — there is no
per-row object model (`Stage1Match`/`Stage2Row` dataclasses were deliberately
removed in favor of DataFrames flowing straight through):

1. **Stage 1 — search** (`scanner.py`): `scan_paths()` finds `.txt` files
   (recursive if given a directory), reads/decodes each file (or block — see
   below) as a whole, and returns a DataFrame with `STAGE1_COLUMNS` (`file`,
   `line_number`, `matched_text`, `pattern`, `source_line`) plus a
   `ScanSummary`.
2. **Stage 2 — extract** (`extractor.py`): `build_stage2_frame()` takes the
   Stage 1 DataFrame and pulls the four fields out of `source_line`, returning
   a DataFrame with `OUTPUT_COLUMNS`.
3. **Output** (`output.py`): `write_csv()` / `read_stage1()` move a DataFrame to
   and from disk; `count_column_matches()` / `format_summary()` build the
   summary report. Output is CSV-only by design — there is no JSON path.

`cli.py` (Click-based) wires these together and supports running only Stage 1
(`--stage1-only`, dump matched lines) or only Stage 2 (`--stage2-only`, parse a
previously saved Stage 1 CSV). `main(argv) -> int` runs the Click command with
`standalone_mode=False` so it stays a plain callable (used directly by tests)
instead of calling `sys.exit`.

### Why everything is vectorized pandas, not Python loops

This codebase went through a deliberate loop-to-vectorized-pandas rewrite; new
code in `scanner.py`/`extractor.py`/`output.py` should follow the same pattern
rather than reintroducing per-line/per-match Python loops:

- **`scanner.py`**: a whole file or block is decoded in one shot (safe because
  `\n` can never appear inside a multi-byte UTF-8 sequence, so a
  newline-aligned boundary is always a valid decode boundary), split into a
  `pandas.Series` of lines, then searched with `Series.str.contains` /
  `str.extract` — one vectorized pass per search pattern, never a per-line
  loop. In `--blocksize` mode, per-file line-number offsets come from a
  vectorized `groupby("file")["line_count"].cumsum()`, not a manual running
  accumulator.
- **`extractor.py`**: each of the four fields (`patterns.FIELD_PATTERNS`) is
  extracted from every matched line with a single `Series.str.findall` call.
  `--one-row-per-match` reshapes wide-to-long via `melt` + `Series.explode`
  rather than building rows one match at a time.
- **`output.py`**: `DataFrame.to_csv` writes the whole result in one call;
  per-column match counts use a single vectorized `Series.str.count("\|")`.

### Regex design (`patterns.py`)

The core domain problem: source lines are delimited inconsistently (comma,
space, `|`, `:`, or a mix, even within one file), so fields are never split on
a delimiter — each line is scanned as a raw blob and every field is found by
shape via regex. Two rules make this delimiter-agnostic:

1. Each field's character class excludes the separator set (whitespace, `,`,
   `|`, `:`), so a match can never swallow a neighboring delimiter (e.g. a
   trailing `:` in `jane@acme.io:8080` is never pulled into the email).
2. Lookahead/lookbehind boundaries stop a match from starting mid-token or
   being truncated by a neighbor (e.g. URLs are anchored on `http(s)://`/`www.`
   so a leading `|` is excluded by construction).

`custom_field_1`/`custom_field_2` share one regex structure
(`letters+digits+optional @`, e.g. `Eagles211@`); the trailing-`@` + lookahead
rule is what distinguishes that token from an email local part
(`Eagles211@acme.io` is rejected as a token since `@` is followed by more
identifier chars, not a delimiter). `patterns.TEST_CASES` holds the
comma/space/pipe/colon/mixed-delimiter examples asserted by
`tests/test_patterns.py` and runnable standalone via
`python -m dump_parser.patterns`.

### Dask block-splitting (verified empirically, don't re-derive from docs)

`--blocksize` mode drives `dask.bytes.read_bytes(delimiter=b"\n")` directly
(not `dask.bag.read_text`, which doesn't expose a block's file/offset needed
for correct line numbers). This was verified experimentally: a 64-byte
blocksize against ~215-byte lines still returns every line intact, in order,
and byte-reassembles exactly — block boundaries never truncate a line.
`blocksize=None` (default) uses one streaming task per file instead.

### Scheduler default mismatch is intentional

The CLI defaults `--scheduler` to `processes` (true CPU parallelism for regex,
requested for PowerGREP-like speed), but the library function
`scanner.scan_paths()` defaults to `threads`. This is not an inconsistency to
"fix" — arbitrary programmatic/notebook callers of `scan_paths()` aren't
guaranteed to have the `if __name__ == "__main__":` guard multiprocessing
needs, while both CLI entry points (`dump-parser`, `python -m dump_parser`) do.

### zip(..., strict=True)

Every `zip()` in this codebase pairs sequences that are constructed in lockstep
(e.g. `files`/`results` from one `dask.compute()` call, or columns of the same
DataFrame) — `strict=True` is required by the ruff config (`B905`) and is also
a correctness check: a length mismatch here always indicates a real bug
upstream, not a legitimate case to silently truncate.
