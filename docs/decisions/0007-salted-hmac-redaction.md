# 0007. Salted HMAC for `custom_field_1`/`custom_field_2` redaction

Status: Accepted (2026-09-23)

## Context

`custom_field_1`/`custom_field_2` are password-shaped tokens, and
`source_line` is the raw matched line — both can carry plaintext credential
material end to end through the pipeline. Output needed to be safe to share
by default, while still letting the exposure report count password reuse
(the same value appearing under 2+ distinct accounts).

## Decision

Redact by default (`--redact`, on unless `--no-redact` is passed): drop
`source_line` entirely, and replace each token with
`HMAC-SHA256(salt, token)` truncated to 16 hex characters. The salt
(`generate_salt()`, `os.urandom(32)`) is generated fresh per run, used only
in memory, and never written, logged, or printed. `email`/`link` stay
visible as the exposure findings.

## Alternatives considered

A bare, unsalted hash (plain SHA-256 of the token) was rejected: per the
author, password-shaped tokens are exactly what a precomputed lookup table
can reverse cheaply, defeating the point of redacting them. Salting per run
closes that — the same token hashes differently across runs, so no table
built once can be reused. Not documented in a commit message; stated here
from the author directly, not traced to a diff.

## Consequences

Same token still hashes identically *within* one run (needed for
`report.py`'s reuse-cluster counting), but not *across* runs. A redacted
`--stage1-only` dump can no longer feed `--stage2-only` (Stage 2 needs the
dropped `source_line`) — a known, documented limitation, not silently
papered over.

## Evidence

`src/dump_parser/redact.py` (module docstring, `generate_salt`,
`_hmac_digest`); `tests/test_redact.py`. Commit `77d65cd`.
