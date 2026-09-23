# 0003. Drive `dask.bytes.read_bytes` directly, not `dask.bag.read_text`

Status: Accepted (2026-07-05)

## Context

`--blocksize` mode needs a correct **file + line number** per match even
when a large file is split into blocks and processed in parallel. Two facts,
verified and documented since the first commit, drove the choice:

1. `dask.bag.read_text(blocksize=...)` never truncates a line — it calls
   `dask.bytes.read_bytes(delimiter=b"\n", blocksize=...)` under the hood,
   which advances each block boundary forward to the next newline. Verified
   empirically: 50 lines (~215 bytes each) read at a 64-byte blocksize came
   back intact, in order, and reassembled byte-for-byte.
2. `read_text` doesn't expose a block's file/offset, so per-file line
   numbers can't be recovered from it alone.

## Decision

Call `dask.bytes.read_bytes(delimiter=b"\n")` directly instead of
`dask.bag.read_text`, keeping the same newline-safe block-splitting
guarantee while retaining each block's file and index so global line numbers
can be recovered afterward.

## Alternatives considered

`dask.bag.read_text` (rejected: fact 2 above — no block file/offset).

## Consequences

Global line numbers are computed as a vectorized per-file prefix sum of each
block's line count (`groupby("file")["line_count"].cumsum()`, ADR 0002)
rather than read off `read_text` for free. `blocksize=None` (default) still
uses one streaming task per file; `blocksize=<bytes>` is for one large file.
Both paths are tested for equivalence.

## Evidence

`src/dump_parser/scanner.py` (`_run_blockwise`, module docstring);
`tests/test_scanner.py::test_blockwise_matches_streaming`,
`test_block_never_truncates_long_line`. Commits `8c09bae` (facts
documented), `bd999e0` (vectorized offset calculation).
