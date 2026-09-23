# 0005. Click over argparse for the CLI

Status: Accepted (2026-07-05)

## Context

The CLI was originally built on `argparse` (`build_parser()`,
`argparse.Namespace`, `argparse.ArgumentTypeError` for the custom blocksize
type). `main(argv) -> int` already existed as the programmatic entry point
used directly by tests.

## Decision

Switch the CLI to Click: `@click.command`/`@click.option`, a custom
`click.ParamType` for the human-readable blocksize (`64MB`/`16kb`), and
`click.UsageError` for invalid flag combinations (e.g.
`--stage1-only`/`--stage2-only` together). `main(argv)` was kept, now
running the Click command with `standalone_mode=False` so it returns/raises
instead of calling `sys.exit`, preserving the exact programmatic contract
tests depend on.

## Alternatives considered

<!-- TODO(craig): the commit message states what changed and what was
preserved (main(argv) contract), but not why Click specifically over
argparse — better option/type ergonomics? Preference from another project?
Not recorded here. -->

## Consequences

`_BlockSizeParam` replaces a hand-rolled `argparse` type function.
`click.UsageError` centralizes flag-conflict messages (also used later for
`--report` + `--stage1-only`, and the redacted-Stage-1-into-`--stage2-only`
error). `main()` catches `click.ClickException`/`click.exceptions.Exit`
specifically rather than letting Click call `sys.exit` itself.

## Evidence

`src/dump_parser/cli.py` (`_BlockSizeParam`, `main`); exercised throughout
`tests/test_end_to_end.py` via `cli.main([...])`. Commit `ed13379` ("switch
cli from argparse to click ... keep main(argv) returning an exit code for
programmatic/test callers").
