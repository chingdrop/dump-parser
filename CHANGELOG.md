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

### Known limitations

- `--stage1-only` output (and the Stage 1 CSV read by `--stage2-only`) is
  unaffected by `--redact` and still contains the raw `source_line`.
