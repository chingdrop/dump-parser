"""Default-on redaction of credential-shaped Stage 1/Stage 2 output.

**Stage 2**: ``custom_field_1``/``custom_field_2`` hold password-shaped tokens
and ``source_line`` is the raw matched line, so both can carry plaintext
credential material. :func:`redact_frame` replaces every token with a salted,
truncated HMAC-SHA256 and drops ``source_line`` entirely; ``email`` and
``link`` (the exposure findings) pass through unchanged.

**Stage 1**: ``matched_text`` is whatever the search pattern matched — with the
default any-field pattern that's exactly one of the four field values above,
but with a custom ``-p`` regex it can be anything. :func:`redact_stage1_frame`
drops ``source_line`` (for the same reason as Stage 2) and hashes
``matched_text`` unless it is itself an email or link, mirroring which two
fields Stage 2 keeps visible. Because ``source_line`` is what Stage 2
extraction reads from, a Stage 1 CSV written this way can no longer be fed
into ``--stage2-only`` — :func:`dump_parser.output.read_stage1` raises a clear
error pointing at ``--no-redact`` rather than silently returning empty fields.

The salt is per run (:func:`generate_salt`): the same value hashes to the same
digest within one run, which is what reuse counting in
:mod:`dump_parser.report` needs, but digests can't be correlated across runs.
The salt is never written, logged, or printed.
"""

from __future__ import annotations

import hashlib
import hmac
import os

import pandas as pd

from .extractor import MULTI_JOIN
from .patterns import EMAIL_RE, URL_RE

# Credential-shaped Stage 2 columns whose tokens are replaced with salted hashes.
TOKEN_COLUMNS: tuple[str, ...] = ("custom_field_1", "custom_field_2")

# Hex characters of the HMAC digest kept per token (64 bits).
HASH_LENGTH = 16


def generate_salt() -> bytes:
    """Return a fresh random 32-byte salt for one run."""

    return os.urandom(32)


def _hmac_digest(value: str, salt: bytes) -> str:
    return hmac.new(salt, value.encode(), hashlib.sha256).hexdigest()[:HASH_LENGTH]


def _hash_column(cells: pd.Series, salt: bytes) -> pd.Series:
    """Replace each pipe-joined token in ``cells`` with its salted HMAC.

    Vectorized: cells are split and exploded to one token per row, each
    *distinct* token is hashed once and mapped back with ``Series.map``, then
    the hashes are re-joined per original cell with a ``groupby`` on the index.
    Empty cells stay empty.
    """

    # Work on a positional index so the groupby below is safe even if the
    # caller's index has duplicates.
    positional = cells.reset_index(drop=True)
    non_empty = positional[positional != ""]
    if non_empty.empty:
        return cells.copy()

    tokens = non_empty.str.split(MULTI_JOIN, regex=False).explode()
    digests = {token: _hmac_digest(token, salt) for token in tokens.unique()}
    hashed = tokens.map(digests).groupby(level=0, sort=False).agg(MULTI_JOIN.join)

    result = positional.copy()
    result.loc[hashed.index] = hashed
    result.index = cells.index
    return result


def _hash_values(values: pd.Series, salt: bytes) -> pd.Series:
    """Replace each non-empty *scalar* value in ``values`` with its salted HMAC.

    Like :func:`_hash_column` but for a column with one value per cell (no
    pipe-joining) — used for Stage 1's ``matched_text``. Vectorized via a
    unique-value digest map applied with ``Series.map``.
    """

    non_empty = values[values != ""]
    if non_empty.empty:
        return values.copy()

    digests = {value: _hmac_digest(value, salt) for value in non_empty.unique()}
    result = values.copy()
    result.loc[non_empty.index] = non_empty.map(digests)
    return result


def redact_frame(df: pd.DataFrame, salt: bytes) -> pd.DataFrame:
    """Return a redacted copy of a Stage 2 frame.

    Token columns are hashed per token with ``HMAC-SHA256(salt, token)``
    (truncated to :data:`HASH_LENGTH` hex chars), ``source_line`` is removed,
    and every other column is returned unchanged.
    """

    redacted = df.drop(columns=["source_line"], errors="ignore").copy()
    for name in TOKEN_COLUMNS:
        if name in redacted.columns:
            redacted[name] = _hash_column(redacted[name].fillna("").astype(str), salt)
    return redacted


def redact_stage1_frame(df: pd.DataFrame, salt: bytes) -> pd.DataFrame:
    """Return a redacted copy of a Stage 1 (search) frame.

    ``source_line`` is dropped (the raw line can carry credential material
    beyond what ``matched_text`` alone isolates). ``matched_text`` is hashed
    with a salted HMAC unless it is itself an email or link — the same two
    exposure findings Stage 2 keeps visible — since anything else a search
    pattern can capture (a custom token, or whatever an arbitrary ``-p``
    regex matched) is treated as credential-shaped by default.
    """

    redacted = df.drop(columns=["source_line"], errors="ignore").copy()
    if "matched_text" not in redacted.columns:
        return redacted

    values = redacted["matched_text"].fillna("").astype(str)
    is_exposure = values.str.fullmatch(EMAIL_RE).fillna(False) | values.str.fullmatch(URL_RE).fillna(False)
    hashed = _hash_values(values.mask(is_exposure, ""), salt)
    redacted["matched_text"] = values.where(is_exposure, hashed)
    return redacted
