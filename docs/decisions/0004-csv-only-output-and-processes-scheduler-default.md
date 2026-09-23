# 0004. CSV-only output; default scheduler `processes`

Status: Accepted (2026-07-05)

## Context

The CLI originally supported `--format {csv,json,both}` and defaulted
`--scheduler` to `threads` (matching the library default). The tool is
explicitly positioned as PowerGREP-style (per the README's opening line),
where the expectation is CPU-bound throughput, not multi-format output.

## Decision

Drop `--format`/JSON support — output is CSV-only. Default the CLI's
`--scheduler` to `processes` instead of `threads`, documented as: "'processes'
gives true CPU parallelism for regex (the default, for PowerGREP-like
speed); 'threads' mainly overlaps I/O" — because Python's `re` holds the GIL.

## Alternatives considered

Keep JSON output (rejected: per the author, the project always used CSV for
debugging in practice, so JSON support was unused complexity, not a format
anyone relied on). `threads` as the CLI default (rejected: GIL means threads
mostly overlap I/O, not CPU-bound regex work).

## Consequences

`output.write_json` was removed; `output.py` is CSV-only by design (per
`CLAUDE.md`). The scheduler default now differs between the CLI (`processes`)
and the library function `scanner.scan_paths()` (`threads`) — intentional,
not a bug: multiprocessing needs an `if __name__ == "__main__":` guard that
both CLI entry points provide but arbitrary programmatic/notebook callers of
`scan_paths()` aren't guaranteed to have.

## Evidence

`src/dump_parser/cli.py` (`--scheduler` option), `src/dump_parser/output.py`;
`tests/test_end_to_end.py` (CSV-only assertions). Commit `c39283c` ("make
output csv-only, drop --format/json support, default scheduler to processes
for powergrep-like speed").
