# Known limitations and possible next steps

## Known limitations

Each of these is verified against the current code, not aspirational or
historical — if a limitation here stops being true, this page should be
updated in the same change that fixes it.

- **CSV output only.** There is no JSON (or any other structured) output
  path. `write_csv()` is the only writer in
  [`output.py`](../src/dump_parser/output.py), and `_write_outputs()` in
  [`cli.py`](../src/dump_parser/cli.py) always calls it. In practice: if a
  downstream tool needs JSON, it has to convert the CSV itself.

- **The four field patterns are fixed shapes.** `email`, `link`,
  `custom_field_1`, and `custom_field_2` are hardcoded regexes in
  [`patterns.py`](../src/dump_parser/patterns.py)'s `FIELD_PATTERNS`
  registry. There is no CLI flag to add, remove, or reshape an extracted
  field — only `-p`/`--pattern` exists, and that only controls which
  *lines* Stage 1 selects, not what Stage 2 extracts from them. In practice:
  extracting a fifth field type (say, a phone number) means editing
  `patterns.py` and redeploying, not passing a flag.

- **A redacted `--stage1-only` dump can't feed `--stage2-only`.** Stage 2
  extraction reads every field from `source_line`, which `--redact` (the
  default) drops from `--stage1-only` output. `--stage2-only` detects a
  missing `source_line` column and fails with a clear error pointing at
  `--no-redact`, in
  [`output.py`](../src/dump_parser/output.py)'s `read_stage1()`, rather than
  silently returning empty fields. In practice: the Stage 1 → Stage 2
  roundtrip workflow only works with `--stage1-only --no-redact`.

- **Single-machine Dask; no distributed cluster support.** The `--scheduler`
  choices (`threads`/`processes`/`synchronous`, in
  [`cli.py`](../src/dump_parser/cli.py)) are all local Dask schedulers —
  there's no `dask.distributed` `Client` anywhere in the code, and the
  `dask[bag]` dependency in `pyproject.toml` doesn't pull in the
  `distributed` extra. In practice: scaling beyond one machine's cores isn't
  currently possible; `--blocksize`/`--scheduler processes` is the ceiling.

## Possible next steps

These are directions, not commitments, pulled only from open markers
actually left in this repo — not the author's or anyone else's new ideas.

As of this writing, there are no open `TODO`/`FIXME` comments anywhere in
`src/` or `tools/`, and a repo-wide search for `TODO(craig)` markers (the
convention used in `docs/decisions/` and
`docs/provenance-and-data-boundary.md` for facts only the author can
confirm) turns up none outstanding — every one raised in earlier work has
been resolved. So there is currently nothing to list here. When a real
`TODO`/`FIXME` or `TODO(craig)` marker exists in the repo, it belongs in
this section.
