"""Default-on redaction of credential-shaped Stage 2 output.

``custom_field_1``/``custom_field_2`` hold password-shaped tokens and
``source_line`` is the raw matched line, so both can carry plaintext credential
material. :func:`redact_frame` replaces every token with a salted, truncated
HMAC-SHA256 and drops ``source_line`` entirely; ``email`` and ``link`` (the
exposure findings) pass through unchanged.

The salt is per run (:func:`generate_salt`): the same token hashes to the same
value within one run, which is what reuse counting in :mod:`dump_parser.report`
needs, but hashes can't be correlated across runs. The salt is never written,
logged, or printed.
"""

from __future__ import annotations

import hashlib
import hmac
import os

import pandas as pd

from .extractor import MULTI_JOIN

# Credential-shaped columns whose tokens are replaced with salted hashes.
TOKEN_COLUMNS: tuple[str, ...] = ("custom_field_1", "custom_field_2")

# Hex characters of the HMAC digest kept per token (64 bits).
HASH_LENGTH = 16


def generate_salt() -> bytes:
    """Return a fresh random 32-byte salt for one run."""

    return os.urandom(32)


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
    digests = {
        token: hmac.new(salt, token.encode(), hashlib.sha256).hexdigest()[:HASH_LENGTH] for token in tokens.unique()
    }
    hashed = tokens.map(digests).groupby(level=0, sort=False).agg(MULTI_JOIN.join)

    result = positional.copy()
    result.loc[hashed.index] = hashed
    result.index = cells.index
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
