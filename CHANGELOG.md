# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

This changelog is retroactive: the project predates having one, so the
`[Unreleased]` section below covers the full history to date, from the first
commit through now, rather than a single past release.

## [Unreleased]

### Added

- The core pipeline: Stage 1 search (`scanner.py`, Dask-based, recursive
  `.txt` discovery) and Stage 2 extraction (`extractor.py`), pulling four
  fields — `email`, `link`, `custom_field_1`, `custom_field_2` — from each
  matched line by regex shape rather than by splitting on a delimiter.
- The Click-based CLI (`cli.py`), with full-pipeline, `--stage1-only`, and
  `--stage2-only` modes, and a programmatic `main(argv) -> int` entry point.
- `--blocksize`: newline-aligned block-splitting of large files (via
  `dask.bytes.read_bytes`) for intra-file parallelism, alongside the default
  one-task-per-file streaming mode.
- Encoding fallback: UTF-8 first, falling back to a configurable encoding
  (default `latin-1`) for non-UTF-8 files.
- `--one-row-per-match`, custom `-p`/`--pattern` search regexes (repeatable),
  and a per-run summary report (files/lines scanned, matches per column,
  encoding fallbacks, unreadable files).
- The test suite: per-field regex tests across every delimiter style,
  scanner and extractor tests, and an end-to-end CLI test.
- Tooling: `uv` for dependency management (`pyproject.toml` + `uv.lock`) and
  the `dump-parser` console script; ruff + mypy with pre-commit hooks; GitHub
  Actions CI (`lint`, `test`, `build`); the GPLv3 license; `CLAUDE.md` as
  project guidance for AI-assisted development.
- Default-on redaction (`src/dump_parser/redact.py`): `custom_field_1`/
  `custom_field_2` tokens are replaced with a per-run salted `HMAC-SHA256`
  (16 hex chars), and `source_line` is dropped from both Stage 2 and
  `--stage1-only` output. `--redact`/`--no-redact` flag; `--no-redact` prints
  a warning and restores plaintext.
- The exposure/reuse report (`src/dump_parser/report.py`, `--report PATH`):
  a Markdown report built from the redacted frame — an exposure summary and
  password-reuse clusters (counts only, no token or hash values printed).
- A deterministic synthetic demo-data generator (`tools/gen_fixtures.py`,
  seeded, Faker-based) and `make demo` / `make demo-big` / `make demo-clean`
  targets, so the pipeline can be demonstrated end-to-end without real data
  (`docs/demo.md`).
- Architecture Decision Records (`docs/decisions/`, 7 records) for the
  project's real design pivots, each with an evidence line pinning it to a
  file and commit hash.
- A provenance and data-boundary statement
  (`docs/provenance-and-data-boundary.md`) and a README "About this project"
  section, covering origin, what's synthetic vs. what must never be
  committed, and current output-safety behavior.

### Changed

- Rewrote Stage 1/2/output from per-line, per-match Python loops to
  vectorized `pandas` `Series` operations end to end; the per-row
  `Stage1Match`/`Stage2Row` dataclasses were removed in favor of
  `DataFrame`s flowing straight through the pipeline.
- Restructured the package from a root-level `dump_parser/` to
  `src/dump_parser/`, matching sibling repos.
- Output is CSV-only (see Removed); the CLI's default `--scheduler` changed
  from `threads` to `processes` for CPU-bound regex work, while the library
  function `scan_paths()` keeps `threads` as its own default.
- Switched the CLI from `argparse` to Click, preserving the `main(argv)`
  programmatic contract used by tests.
- Stage 2 output, and separately `--stage1-only` output, are now redacted by
  default (see Added) — a behavior change from the plaintext output every
  prior version produced.

### Removed

- JSON output support (`--format`/`write_json`) — output is CSV-only.
- `requirements.txt`, replaced by `pyproject.toml` + `uv.lock`.

### Fixed

- An O(n²) bug in Stage 1's block-line-numbering (`--blocksize` mode),
  found and fixed during the vectorization rewrite above; the fix replaced a
  manual per-file offset accumulation with a vectorized
  `groupby("file")["line_count"].cumsum()` prefix sum.
