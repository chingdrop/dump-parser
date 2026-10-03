# 0008. Adopt the shared Python tooling standard

Status: Accepted (2026-10-03)

## Context

The maintainer applies one tooling standard across four repos:
agent-parity, medicare-rebuild, medtext-redact and dump-parser. The repo does
not record why each individual setting was chosen. It records only that
these four repos should match.

## Decision

- **Python 3.12 floor** (`requires-python`, `.python-version`, ruff target,
  CI). 3.10 and 3.11 are no longer supported or tested.
- **ruff `S`** (flake8-bandit), and ruff now lints `tools/` as well as
  `src`/`tests`.
- **mypy** adds `strict_equality` and `check_untyped_defs`. Both were
  clean, so neither was left out. mypy now also checks `tools/` in CI.
- **Coverage gate**: the measured baseline was 84.49% branch coverage, so
  `fail_under = 82` (baseline minus 2, rounded down). Tests use
  `--scheduler synchronous`, so code that runs only in Dask worker processes
  isn't measured. No `parallel`/`concurrency` settings were added to hide this.
- **pre-commit** adds gitleaks, `detect-private-key` and
  `check-added-large-files`.
- **CI hardening**: `persist-credentials: false`, a newer pinned CodeQL release,
  and pip-audit split into a locked export plus a pinned `pip-audit@2.10.1`.

## Alternatives considered

Not recorded. The standard was adopted as one package, not chosen
setting by setting in this repo.

## Consequences

This is a breaking change for 3.10/3.11 users. The tested stack moved from
pandas 2.3.3 to 3.0.3. `__main__.py` and the flat `tests/` layout are
unchanged ([ADR 0004](0004-csv-only-output-and-processes-scheduler-default.md)).

## Evidence

`pyproject.toml`, `.python-version`, `.pre-commit-config.yaml`,
`.github/workflows/ci.yml`, `.github/workflows/codeql.yml`,
`CONTRIBUTING.md`. Branch `chore/python-standard`.
