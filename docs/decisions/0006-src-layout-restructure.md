# 0006. Restructure to `src/` layout

Status: Accepted (2026-07-17)

## Context

The package originally lived at the repo root as `dump_parser/`, importable
without installation. This is a common early-stage layout but diverges from
a src-layout convention used elsewhere.

## Decision

Move the package to `src/dump_parser/`, matching sibling repos: **vega-tools,
medicare-rebuild, and agent-parity** (named verbatim in the commit message).
`pyproject.toml`'s `[tool.hatch.build.targets.wheel]` was updated to
`packages = ["src/dump_parser"]`. Every file moved was a pure rename (the
commit diff shows zero content changes, just path renames).

## Alternatives considered

Keep the flat root-level layout (rejected: explicitly for cross-repo
consistency with the sibling repos named above, not for a reason specific to
this repo's own code).

## Consequences

Tests, imports, and the console script (`dump-parser = "dump_parser.cli:main"`)
were unaffected since they already referenced the package by name, not path.
The immediate follow-up commit (`c17923d`, same day) added ruff/mypy tooling
"matching sibling repos" too, and mypy is scoped specifically to `src/`
(`.pre-commit-config.yaml`'s mypy hook: `files: ^src/`) — the layout and the
tooling scoping are directly linked.

## Evidence

Directory move `dump_parser/` → `src/dump_parser/`; `pyproject.toml`
(`[tool.hatch.build.targets.wheel]`); `CLAUDE.md` ("Dependencies are managed
with `uv`. The package lives under `src/dump_parser` (src layout)"). Commit
`657febc` ("restructure to src/ layout, matching sibling repos (vega-tools,
medicare-rebuild, agent-parity)"), documented in `297c0c2`.
