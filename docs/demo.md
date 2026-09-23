# Demo: end-to-end on synthetic data

`make demo` runs dump-parser's full pipeline — search, extract, **redact**,
report — against a dataset that is entirely synthetic, generated fresh on
your machine, with no real data dump ever involved. It exists to let you (or
someone evaluating this tool) see real output without needing, or risking,
an actual breach dump.

`redact.py` and `report.py` both exist in this repo, so the demo uses them as
they ship: `--redact` is the CLI default (hashed tokens, no `source_line`),
and `--report` is passed explicitly to also produce the Markdown exposure
report.

## What it proves

- The three-stage pipeline (search → extract → redact) runs correctly over a
  messy, mixed-delimiter, mixed-encoding dataset shaped like the real thing.
- Redaction is genuinely on by default: the CSV below has no plaintext
  token-shaped values and no `source_line` column.
- The exposure/reuse report finds real (but entirely fabricated) password
  reuse, because the generator deliberately seeds some.
- `--blocksize` genuinely splits one large file into parallel, newline-aligned
  chunks (`make demo-big`), which the many-small-files `make demo` run above
  doesn't exercise.

## Commands

```bash
make demo         # generate fixtures, run the full pipeline, print a summary
make demo-big     # exercise --blocksize against one large generated file
make demo-clean   # remove demo_data/ and demo_output/ (both gitignored)
```

`make demo` and `make demo-big` both (re)run `tools/gen_fixtures.py` with its
fixed default seed first, so either can be run standalone and both see the
same dataset.

## `make demo`: real output

```
$ make demo
uv run python tools/gen_fixtures.py --out-dir demo_data
Generated 9 file(s), 54000 line(s), 3393 distinct email(s) -> demo_data/
  custom_field_1: 84 reuse cluster(s) injected (sizes: [5, 2, 4, 4, 3, ...])
  custom_field_2: 84 reuse cluster(s) injected (sizes: [5, 2, 4, 4, 3, ...])
uv run dump-parser demo_data/regular \
    -o demo_output/results \
    --report demo_output/report.md \
    --scheduler synchronous \
    --no-summary
=======================================================
dump-parser demo  (demo_data/regular -> demo_output/)
=======================================================
  files scanned        : 8
  lines scanned        : 4000
  Stage 2 rows written : 3909
  distinct emails      : 3393
  reuse clusters found : 84  (custom_field_1/2; deliberately injected, see docs/demo.md)
=======================================================
CSV:    demo_output/results.csv
Report: demo_output/report.md
```

`demo_output/results.csv` (first two data rows — redacted by default, so
`custom_field_1`/`custom_field_2` are salted-HMAC hashes and there is no
`source_line` column):

```
file,line_number,email,link,custom_field_1,custom_field_2
demo_data/regular/dump_002_latin1.txt,1,angela+lowe11@corp.example,,b8c2442f7dd6af80,b8c2442f7dd6af80
demo_data/regular/dump_002_latin1.txt,2,jessicaramirez998@mail.example,,138e8f877e9e359c,138e8f877e9e359c
```

`demo_output/report.md` (excerpt — the full file lists all 84 clusters per
column):

```
# Exposure Report

## Exposure Summary

- Files scanned: 8
- Lines scanned: 4000
- Files contributing at least one row: 8
- Distinct email addresses: 3393
- Distinct email addresses with an associated token: 2203

## Password Reuse

### custom_field_1

- Cluster 1: 8 distinct accounts share a value
- Cluster 2: 8 distinct accounts share a value
- Cluster 3: 8 distinct accounts share a value
- Cluster 4: 7 distinct accounts share a value
- Cluster 5: 7 distinct accounts share a value
- Cluster 6: 7 distinct accounts share a value
...

**316 of 2203 accounts with any token (14.3%) participate in a reuse cluster.**
```

No token value or hash is ever printed in the report, on either the CSV or
the Markdown side — only counts, exactly as `dump_parser/report.py` is
designed to do.

## `make demo-big`: real output

```
$ make demo-big
uv run dump-parser demo_data/big \
    --blocksize 512KB \
    -o demo_output/big_results \
    --scheduler processes
====================================================
  Dump Parser — Summary Report
====================================================
  Files scanned      : 1
  Lines scanned      : 50000
  Stage 1 matches    : 48832
  Matches per column :
      email           : 42424
      link            : 29765
      custom_field_1  : 35397
      custom_field_2  : 35397
  Elapsed            : 0.251s
====================================================
```

One ~2.7 MB, 50,000-line file, split into 512 KB newline-aligned blocks and
processed in parallel (`--scheduler processes`) — the `--blocksize` machinery
the README describes at length, now with something runnable to show it.

## `--reuse-rate`, and why the clusters exist

Real password-reuse detection needs *some* accounts sharing *some* value to
find — but there is no real breach data anywhere in this repo, on purpose.
`tools/gen_fixtures.py --reuse-rate` (default `0.15`) controls the fraction of
generated token-shaped values that are drawn from a small shared pool instead
of being freshly random. Every account assigned a pool value is recorded in
`demo_data/manifest.json`, which is the *ground truth* for what was
deliberately injected — the exposure report is expected to reproduce it
exactly (in cluster counts and sizes; the actual hash values differ every run
because redaction uses a fresh random salt per run). `tests/test_gen_fixtures.py`
and `tests/test_demo_integration.py` check exactly that.

Set `--reuse-rate 0` to generate a dataset with no injected reuse at all (the
report will then say so explicitly, in its "no reuse clusters found" line),
or run `uv run python tools/gen_fixtures.py --help` for every flag
(`--seed`, `--files`, `--lines-per-file`, `--big-file-lines`, `--out-dir`).

## Known gap this demo surfaces

`--stage1-only` output is also redacted by default (`matched_text` hashed
unless it's an email/link, `source_line` dropped) — see the README's
"Stage 1 redaction" section. This demo doesn't specifically exercise
`--stage1-only`, but `tests/test_demo_integration.py` does, against the same
generated dataset.
