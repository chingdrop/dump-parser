# Contributing

## Prerequisites

- **Python 3.12**, pinned in `.python-version`. It is also the
  `requires-python` floor and the only version CI runs.
- **[uv](https://docs.astral.sh/uv/)** for dependency management and running
  everything below.

## Setup

```bash
git clone https://github.com/chingdrop/dump-parser.git
cd dump-parser
uv sync                          # runtime + dev dependencies, from uv.lock
uv run pre-commit install        # run the hooks on every commit
```

## Project layout

```text
src/dump_parser/
  __init__.py
  __main__.py       # `python -m dump_parser` entry point (see below)
  cli.py            # Click CLI wiring Stage 1 -> Stage 2 -> output
  scanner.py        # Stage 1: find .txt files, search lines (Dask)
  extractor.py      # Stage 2: pull the four fields out of matched lines
  patterns.py       # field regexes + TEST_CASES self-test
  models.py         # shared column schemas and summary types
  output.py         # CSV read/write, summary formatting
  redact.py         # default-on salted-HMAC redaction
  report.py         # Markdown exposure / reuse report
tests/              # flat pytest modules + conftest.py
tools/
  gen_fixtures.py   # synthetic dataset generator for the demo and tests
  demo_summary.py   # prints the `make demo` summary
sample_data/        # small committed sample dumps (fake data)
docs/               # threat model, roadmap, demo notes, ADRs (docs/decisions/)
Makefile            # `make demo`, `make demo-big`, `make demo-clean`
```

**`__main__.py` is required.** The CLI's default `--scheduler processes`
re-imports the entry module in Dask worker processes, so both
`dump-parser` and `python -m dump_parser` must keep working, and any new
entry point must stay behind an `if __name__ == "__main__":` guard (see
`CLAUDE.md` and [ADR 0004](docs/decisions/0004-csv-only-output-and-processes-scheduler-default.md)).

## Running tests

```bash
uv run pytest -q
uv run pytest tests/test_patterns.py -q    # one module
```

Tests stay flat under `tests/` while there are 10 or fewer test modules;
once there are more, `tests/` should mirror `src/dump_parser/`.
`tests/conftest.py` puts `tools/` on `sys.path`, which is how the fixture
generator tests import `gen_fixtures`, since `tools/` is not part of the
installed package.

## Code quality

These are the exact commands CI's `lint` job runs:

```bash
uv run ruff check src tests tools
uv run ruff format --check src tests tools
uv run mypy src/dump_parser tools/
```

Ruff's rule set includes `S` (flake8-bandit). Don't add a `# noqa` or
`# type: ignore` without a reason on the same line.

## Before opening a PR

Run what CI runs:

```bash
uv sync --locked
uv run ruff check src tests tools
uv run ruff format --check src tests tools
uv run mypy src/dump_parser tools/
uv run pytest --cov
uv build
uv run pre-commit run --all-files
```

## Coverage

`uv run pytest --cov` enforces a branch-coverage floor set in
`pyproject.toml` under `[tool.coverage.report]` (`fail_under`). The floor is
the measured baseline minus 2, rounded down. When the measured baseline climbs
more than 4 points above the floor, raise the floor in the same PR.

Tests run Dask with `--scheduler synchronous`, so code that only runs inside
worker processes isn't measured. The floor reflects that as-is.

## Design decisions

Real design pivots are recorded as short ADRs in
[docs/decisions/](docs/decisions/README.md). A new decision gets a new
numbered file. Never edit an old one; if a later decision reverses an earlier
one, say so in the new record.

## Changelog

Add user-visible changes to the `[Unreleased]` section of
[CHANGELOG.md](CHANGELOG.md) under Added / Changed / Removed / Fixed. Don't
edit existing entries.

## Open work

Planned features, known bugs and open author questions live in
[TODO.md](TODO.md), not in inline `TODO`/`FIXME` comments.

## Commit style

Short, lowercase subject lines, with multiple changes joined by commas,
for example `add TODO.md, move TODO(craig) items into it, point docs at it`.
Use the body to explain why when the subject alone doesn't.
