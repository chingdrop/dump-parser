# Security Policy

## Supported versions

This project has no tagged release yet — everything ships from `main`. Until
a first release is tagged, `main` is the only supported line; security fixes
land there directly. Once tags exist, this section will name which of them
are still supported.

## Reporting a vulnerability

Please report suspected vulnerabilities privately, using GitHub's private
vulnerability reporting: on this repository, go to the **Security** tab →
**Report a vulnerability**. This opens a private advisory visible only to
the maintainer and you, rather than a public issue.

Please do not open a public GitHub issue for a suspected vulnerability.

<!-- TODO(craig): backup contact email, if wanted -->

**Response window:** expect an initial response within 5 business days. This
is a portfolio/personal project maintained by one person, not a funded
security team with an SLA — that response time is a best-effort target, not
a contractual guarantee.

## Scope

This is a pattern-based text extraction CLI (see
[README.md](README.md)) — it is not a service, has no network-facing
component, and processes only files a user explicitly points it at on their
own machine.

**Current output-safety behavior**, verified against the code as of this
writing: `src/dump_parser/redact.py` exists and `--redact` is the CLI
default. Default output hashes `custom_field_1`/`custom_field_2` with a
per-run salted HMAC and drops `source_line`; `--no-redact` restores
plaintext and prints a warning. See
[docs/threat-model.md](docs/threat-model.md) for the full detail and
[docs/decisions/0007-salted-hmac-redaction.md](docs/decisions/0007-salted-hmac-redaction.md)
for why it's built this way.

Vulnerability reports about this tool's own code (e.g., a way redaction
fails to redact what it claims to, a way the CLI could be made to read or
write outside the paths a user gave it) are in scope. Reports about
vulnerabilities in third-party dependencies (Dask, pandas, Click) belong
upstream, not here — though a report noting one affects this project is
still welcome context.
