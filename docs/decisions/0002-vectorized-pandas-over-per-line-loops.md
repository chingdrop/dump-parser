# 0002. Vectorized pandas over per-line Python loops

Status: Accepted (2026-07-05)

## Context

The original Stage 1/2/output code looped in plain Python: per line, per
field pattern, per match, and per block in `_run_blockwise`'s manual
`for block_index in sorted(blocks_map): offset += line_count` reordering
step. A per-row `Stage1Match`/`Stage2Row` dataclass pair carried data
between stages.

## Decision

Rewrite all three stages to pass `pandas.DataFrame`s straight through
instead of per-row dataclasses: `scanner.py` decodes a whole file/block and
searches it with one `Series.str.contains`/`str.extract` pass per pattern;
`extractor.py` pulls each field with one `Series.str.findall` call across
every row; block line-number offsets become a vectorized
`groupby("file")["line_count"].cumsum()` prefix sum. `Stage1Match`/
`Stage2Row` were removed.

## Alternatives considered

Partial vectorization (e.g. rewriting just `extractor.py`) wasn't the plan.
Per the author, all three stages were rewritten together from the start,
aiming for a more vectorized way of handling the data — closer to how data
was manipulated to get it report-ready in the original professional work
this project grew out of.

## Consequences

The commit message records that this rewrite surfaced and fixed an O(n^2)
block-reordering bug in the old per-file `sorted(blocks_map)` offset
accumulation; the diff only shows the final, corrected vectorized version,
so the exact quadratic mechanism isn't reconstructable from git alone. Per
the author, the trigger was practical rather than a targeted bug hunt: these
dumps are huge, so a processing slowdown was immediately noticeable, and the
vectorized rewrite already underway was expected to (and did) resolve it —
this wasn't isolated and fixed as a standalone patch first. Net effect:
`scan_paths()` and `build_stage2_frame()` now return DataFrames directly
(`STAGE1_COLUMNS`/`OUTPUT_COLUMNS`), and every later feature (redaction, the
exposure report) operates on those frames rather than per-row objects.

## Evidence

`src/dump_parser/scanner.py`, `src/dump_parser/extractor.py`,
`src/dump_parser/output.py`; `tests/test_scanner.py`,
`tests/test_extractor.py`. Commit `bd999e0`.
