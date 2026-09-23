# 0001. Delimiter-agnostic, shape-based field extraction

Status: Accepted (2026-07-05)

## Context

Source dumps delimit the same field type inconsistently — comma, space,
pipe `|`, colon `:`, or a mix, sometimes within one file. A fixed
`str.split()` schema breaks the moment the delimiter changes mid-file.

## Decision

Never split on a delimiter. Treat each line as a raw blob and locate every
field (email, link, `custom_field_1`/`custom_field_2`) by regex shape,
anywhere on the line. Each field's character class excludes the separator
set (whitespace, `,`, `|`, `:`) so a match can't swallow a neighboring
delimiter, and lookahead/lookbehind boundaries stop a match from starting
mid-token or being truncated by a neighbor (e.g. URLs anchor on
`http(s)://`/`www.`).

## Alternatives considered

A delimiter-splitting approach was tried first, per the author: split each
line on several candidate symbols and check whether the result had the
expected number of elements; a wrong count flagged the line as an unusual
shape needing separate handling. Rejected because the real dumps used
nearly every symbol imaginable as a separator, including characters that
weren't anticipated up front — a fixed split-and-count check kept failing on
shapes it hadn't been written for. Shape-based regex matching sidesteps
this: a field is recognized by what it looks like, not by where it sits
relative to an unenumerable delimiter.

## Consequences

The four field regexes (`patterns.py`) carry all of the delimiter-safety
logic and need their own dedicated test matrix (comma/space/pipe/colon/mixed
per field). This is also what makes the extractor safe to vectorize later
(ADR 0002): each field is one `Series.str.findall` call, independent of how
the line happens to be delimited.

## Evidence

`src/dump_parser/patterns.py`; `tests/test_patterns.py`. Commit `8c09bae`
("add dask-based dump parser cli, delimiter-agnostic regex extraction for
email/link/custom fields, csv/json output, tests and sample data").
