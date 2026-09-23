# Threat model

Derived only from what the code does, as of this writing. If any of these
facts stop being true, this page should be updated in the same change.

## What this tool processes

`dump-parser` reads whatever `.txt` file(s) or directory a user points it at
on the command line (`scanner.discover_files`) — nothing else. It holds no
credentials or API keys of its own: there is no `.env`/dotenv handling, no
config-file reading, and no secret/API-key variable anywhere in
`src/dump_parser/`. Every `open()` call in the package is either on a
user-supplied input path or on an output path the user chose (`-o`,
`--report`) — never a credentials file.

## The redaction boundary

`src/dump_parser/redact.py` exists, and `--redact` is the CLI default (see
[`cli.py`](../src/dump_parser/cli.py)). Default output replaces
`custom_field_1`/`custom_field_2` with `HMAC-SHA256(salt, token)` (16 hex
chars) and drops `source_line` from both Stage 2 and `--stage1-only`
output; `email`/`link` stay visible as the exposure findings. The salt
(`generate_salt()`, `os.urandom(32)`) is generated fresh per run, used only
in memory, and never written, logged, or printed — the same token hashes
identically *within* one run (so the exposure report can count reuse) but
not *across* runs, so a hash from one run can't be looked up against a
precomputed table built from another. See
[`docs/decisions/0007-salted-hmac-redaction.md`](decisions/0007-salted-hmac-redaction.md)
for why this design was chosen over a bare hash. `--no-redact` restores full
plaintext and prints a warning — it exists for live, authorized use, not for
anything meant to be shared.

Known gap: a redacted `--stage1-only` dump can't feed `--stage2-only` (Stage
2 needs the `source_line` that redaction drops); see the README's "Known
limitations". This is a functional boundary, not a security hole — it fails
loudly with an error, not silently.

## Data at rest and in transit

Output (CSV, and the Markdown report if `--report` is used) is written only
to the path the user specifies, or to stdout. Nothing in
`src/dump_parser/` makes a network call: there is no `requests`, `httpx`,
`urllib`, `socket`, or similar import anywhere in the package — confirmed by
inspection, not assumed. Whatever this tool produces stays exactly where the
user told it to write it.

## Residual risk

Redaction reduces what's in the output, but running this tool against real
data at all is a decision with consequences beyond this repo's control.
Whoever does that is responsible for handling the output — plaintext or
redacted — according to whatever authorization and data-handling rules
apply to that data; nothing here grants or implies that authorization. The
only path in this repository safe to run and share publicly is the
synthetic demo (`tools/gen_fixtures.py`, `make demo`; see
[`docs/demo.md`](demo.md) and
[`docs/provenance-and-data-boundary.md`](provenance-and-data-boundary.md)) —
generated, fictional data, never real dumps.
