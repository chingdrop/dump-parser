# 0001. Delimiter-agnostic, shape-based field extraction

Status: Accepted (2026-07-05)

## Context

Source dumps delimit the same field type inconsistently — comma, space,
pipe `|`, colon `:`, or a mix, sometimes within one file. A fixed
`str.split()` schema breaks the moment the delimiter changes mid-file.

## Decision

Never split on a delimiter. Treat each line as a raw blob and locate every
field (email, link, `custom_field_1`/`custom_field_2`) by regex shape,
anywhere on the line. Two rules keep this safe: each field's character
class excludes the separator set (whitespace, `,`, `|`, `:`), so a match
can't swallow a neighboring delimiter; and lookahead/lookbehind boundaries
stop a match from starting mid-token or being truncated by a neighbor (e.g.
URLs anchor on `http(s)://`/`www.`).

## Alternatives considered

<!-- TODO(craig): the repo doesn't record what was tried before this —
was a delimiter-splitting or sniffing approach attempted and rejected, or
was shape-based matching the design from the first commit? -->

## Consequences

The four field regexes (`patterns.py`) carry all of the delimiter-safety
logic, so they're intricate and need their own dedicated test matrix
(comma/space/pipe/colon/mixed per field) rather than being a thin wrapper
around `str.split`. This is also what makes the extractor safe to vectorize
later (ADR 0002): each field is one `Series.str.findall` call, independent
of how the line happens to be delimited.

## Evidence

`src/dump_parser/patterns.py`; `tests/test_patterns.py`. Commit `8c09bae`
("add dask-based dump parser cli, delimiter-agnostic regex extraction for
email/link/custom fields, csv/json output, tests and sample data").
