# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `--report PATH` writes a Markdown exposure/reuse report alongside the CSV,
  built from the redacted Stage 2 frame. It reports aggregate counts only
  (exposure summary and password-reuse clusters) — no email, token, or hash
  value is printed. Implies Stage 2 output; errors if combined with
  `--stage1-only`.
- `--redact` / `--no-redact` flag.

### Changed

- **Stage 2 output is now redacted by default** (behavior change from prior
  versions). `custom_field_1`/`custom_field_2` tokens are replaced with a
  per-run salted `HMAC-SHA256` (truncated to 16 hex chars), and the raw
  `source_line` column is dropped. `email` and `link` stay visible. Pass
  `--no-redact` to restore the previous full plaintext output (including
  `source_line`); it prints a warning to stderr and is intended only for live,
  authorized engagements.
- **`--stage1-only` output is now redacted by default too** (behavior
  change). `matched_text` is hashed the same way as Stage 2's tokens unless
  it's itself an email or link, and `source_line` is dropped. As a
  consequence, a default (`--redact`) `--stage1-only` dump can no longer be
  fed into `--stage2-only` — Stage 2 extraction needs `source_line`, and
  `--stage2-only` now fails with a clear error telling you to re-run
  `--stage1-only --no-redact` if you need that roundtrip, rather than
  silently producing empty fields.
