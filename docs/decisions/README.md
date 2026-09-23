# Architecture Decision Records

Lightweight [MADR](https://adr.github.io/madr/)-style records of the real
design pivots in this repo's history, drafted from the actual code, tests,
and `git log` — not reconstructed from memory. Each one is under ~250 words:
Context, Decision, Alternatives considered, Consequences, and an Evidence
line pinning it to the file(s) and commit hash(es) that back it up. Where the
repo doesn't record *why* a choice was made, the record says so with a
`<!-- TODO(craig): ... -->` comment rather than guessing.

New decisions get a new numbered file (`NNNN-short-title.md`), not an edit to
an old one — if a later decision reverses or narrows an earlier one, the
earlier record stays as written and the new one says so in its own Context.

| # | Title | Status |
|---|---|---|
| [0001](0001-delimiter-agnostic-shape-based-extraction.md) | Delimiter-agnostic, shape-based field extraction | Accepted |
| [0002](0002-vectorized-pandas-over-per-line-loops.md) | Vectorized pandas over per-line Python loops | Accepted |
| [0003](0003-drive-read-bytes-directly.md) | Drive `dask.bytes.read_bytes` directly, not `dask.bag.read_text` | Accepted |
| [0004](0004-csv-only-output-and-processes-scheduler-default.md) | CSV-only output; default scheduler `processes` | Accepted |
| [0005](0005-click-over-argparse.md) | Click over argparse for the CLI | Accepted |
| [0006](0006-src-layout-restructure.md) | Restructure to `src/` layout | Accepted |
| [0007](0007-salted-hmac-redaction.md) | Salted HMAC for `custom_field_1`/`custom_field_2` redaction | Accepted |
