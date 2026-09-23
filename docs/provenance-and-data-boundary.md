# Provenance and data boundary

This page states plainly where this project came from, what data does and
does not live in this repository, and what current behavior means for
handling real data. It's written for anyone evaluating this repo, including
someone with no other context.

## Provenance

This idea originated in past professional security work: a data-parsing tool
used to search large, unstructured text dumps and extract structured fields
(emails, links, password-shaped tokens) from them. No original employer or
client is named here, and none should be added without being already public
knowledge.

What is published in this repository is an independent, from-scratch
rebuild: no code or regex pattern was copied verbatim from the original
tool. The architecture (three-stage pipeline, DataFrame-only boundaries,
vectorized pandas throughout — see [`CLAUDE.md`](../CLAUDE.md)), the regex
design in [`patterns.py`](../src/dump_parser/patterns.py), the CLI surface,
and the tests were all written for this repository.

**Naming note.** The example domain `blueshiftdefense.com`, used throughout
the README and the test suite as a `-p '@blueshiftdefense.com'` search
example, is intentional self-branding for this project — never a placeholder
for, or reference to, a real target.

## Data boundary

**What's in this repository, verified:**

- [`sample_data/`](../sample_data/) — a handful of small, hand-written `.txt`
  fixtures (`dump_mixed.txt`, `dump_latin1.txt`, `nested/dump_pipes.txt`).
  Every email, link, and token in them is fictional: domains like
  `acme.io`, `corp.net`, `mail-server.org`, `sub.example.co.uk`, and
  sports/animal-name-plus-digits tokens (`Eagles211@`, `Falcons88`, ...).
  There is no real breach or credential material in this repository.
- [`tools/gen_fixtures.py`](../tools/gen_fixtures.py) — an optional generator
  that produces a larger, entirely synthetic dataset (via a seeded
  `random.Random` and a seeded `Faker` instance) for the `make demo` /
  `make demo-big` targets described in
  [`docs/demo.md`](demo.md). It writes only to `demo_data/` and
  `demo_output/`, both listed in [`.gitignore`](../.gitignore) — this data is
  never committed and is regenerated fresh on demand.

**What must never be committed to this repository:**

- Any real data dump, export, or scrape — of any size, from any source.
- Anything resembling actual breach material or real credential pairs
  (emails, passwords, tokens, hashes) — even a single real row.
- Real credentials, API keys, tokens, or secrets of any kind, for this
  project or any other system.
- Output produced by running this tool against real data, in any form (CSV,
  the Markdown report, terminal output, screenshots).

## Contribution rule

Any new test fixture or demo data added to this repository must be either
hand-written fiction (like `sample_data/`) or generated (like
`tools/gen_fixtures.py`'s output) — never copied from, derived from, or
fitted to a real data source. If you need a new pattern-matching edge case
covered, write a line that exercises the shape, not one that resembles
something that actually happened to someone.

## Current limitations (stated honestly, not as future work)

As of this writing, `src/dump_parser/redact.py` and
`src/dump_parser/report.py` exist and `--redact` is the CLI default (see
[`cli.py`](../src/dump_parser/cli.py)): default CSV output hashes
`custom_field_1`/`custom_field_2` with a per-run salted HMAC and drops
`source_line`; `--no-redact` restores plaintext and prints a warning. That is
current, working behavior — not aspirational.

Known gaps, stated plainly:

- `--stage1-only` output is redacted the same way, but a redacted Stage 1
  dump can no longer be fed into `--stage2-only` (Stage 2 needs the dropped
  `source_line`); see the README's "Known limitations" section.
- Redaction hashes are salted per run and are not intended to be, and are
  not, cryptographically hardened against a determined offline attack on a
  small, known token space — they are a default-on privacy measure for
  sharing output, not a security control for protecting genuinely sensitive
  values at rest.
- This project has not been audited by anyone other than its author.

## Scope disclaimer

This is a pattern-based text extraction utility: it searches text for
shapes (emails, links, password-shaped tokens) and reformats what it finds.
It is **not** a breach-monitoring service, a threat-intelligence feed, or any
kind of managed or continuously-updated system. Running it against real data
is entirely the operator's responsibility: it requires its own authorization,
its own legal and organizational handling appropriate to that data, and its
own decision about whether `--no-redact` output may ever leave the machine
it was produced on. Nothing in this repository — including this page —
constitutes that authorization.
