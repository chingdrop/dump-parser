"""Regex definitions for the four extractable fields.

Design goal: the source dumps are *inconsistently* delimited — a field may be
separated from its neighbours by a comma, a space, a pipe ``|``, a colon ``:`` or
any combination. We therefore never split on a delimiter. Instead each line is
treated as a raw blob and every field is located by *shape* with
``re.finditer``, anywhere on the line.

Two rules keep the patterns delimiter-agnostic without bleeding into the
surrounding separators:

1. Every field's own character class *excludes* the separator characters
   (whitespace, ``,``, ``|``, ``:``). Because the match can't contain a
   separator, it can't accidentally swallow one. This is why a ``:`` sitting
   immediately after an email is never pulled into the email match.

2. Lookbehind / lookahead boundaries stop a match from *starting* in the middle
   of a larger token or from being truncated by a neighbour. Because we anchor
   URLs on their scheme (``http``/``www.``) a ``|`` sitting immediately *before*
   a URL can never be part of it.

The separator set is intentionally: whitespace, ``,``, ``|``, ``:``.
"""

from __future__ import annotations

import re
from typing import Dict, List, Pattern, Tuple

# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------
# Local part and domain use standard email character classes. Neither class
# contains ``:`` ``|`` ``,`` or whitespace, so a trailing delimiter such as the
# ``:`` in ``jane@acme.io:8080`` is left outside the match. The right boundary
# forbids a following alnum/hyphen so we don't stop halfway through a domain,
# but *allows* a following ``.`` (a sentence-ending dot is simply not consumed
# by the ``\.[A-Za-z]{2,}`` tail).
EMAIL_RE: Pattern[str] = re.compile(
    r"(?<![A-Za-z0-9._%+\-@])"          # left boundary: not mid-token
    r"[A-Za-z0-9._%+\-]+"               # local part
    r"@"
    r"[A-Za-z0-9.\-]+"                  # domain labels
    r"\.[A-Za-z]{2,}"                   # top-level domain
    r"(?![A-Za-z0-9\-])"                # right boundary: not more domain chars
)

# ---------------------------------------------------------------------------
# Link (HTTP/HTTPS URL or bare www.)
# ---------------------------------------------------------------------------
# Anchored on the scheme so anything *before* it (e.g. a leading ``|``) is
# excluded by construction. The host class excludes ``:`` so a colon used as a
# field delimiter (``site.com:Eagles211``) terminates the host; a genuine port
# is picked up only by the explicit ``:\d+`` group. The path/query/fragment
# group stops at whitespace, ``,`` and ``|``. Any trailing punctuation left on
# the end is removed by :func:`strip_url`.
URL_RE: Pattern[str] = re.compile(
    r"(?<![\w@.\-])"                    # left boundary: not mid-token
    r"(?:https?://|www\.)"              # scheme or bare www.
    r"[A-Za-z0-9\-._~%]+"               # host (no ':' -> stops at a delimiter colon)
    r"(?::\d+)?"                        # optional :port (digits only)
    r"(?:[/?#][^\s,|:<>\"']*)?"         # optional path/query/fragment (stops at
                                        # a delimiter ':'; a real port is caught
                                        # by the :\d+ group above)
)

# Trailing characters stripped from a URL match. Covers sentence punctuation and
# a delimiter (``|`` ``:`` ``,``) that abutted the URL, plus closing brackets.
_URL_TRAILING = ".,;:!?|)]}>\"'"


def strip_url(match: str) -> str:
    """Strip trailing punctuation/delimiters from a raw URL match.

    ``"https://acme.io/path?q=1)."`` -> ``"https://acme.io/path?q=1"``. Balanced
    trailing brackets are removed only when unbalanced within the match so we do
    not truncate a URL that legitimately ends in ``)``.
    """

    result = match.rstrip(_URL_TRAILING)
    # Restore a single closing bracket if it is balanced inside the URL, e.g.
    # a Wikipedia-style ``.../Foo_(bar)`` should keep its ``)``.
    if match[len(result):].startswith(")") and result.count("(") > result.count(")"):
        result += ")"
    return result


# ---------------------------------------------------------------------------
# Custom word fields
# ---------------------------------------------------------------------------
# Shape: one or more letters, then one or more digits, then an OPTIONAL trailing
# ``@`` used as a marker (e.g. ``Eagles211@``). The right boundary
# ``(?![A-Za-z0-9@])`` is what distinguishes this marker token from an email
# local part: in ``Eagles211@acme.io`` the ``@`` is followed by ``a`` so the
# token is rejected, whereas ``Eagles211@|`` (``@`` followed by a delimiter) is
# accepted. The left boundary forbids a preceding alnum/email char so the token
# is standalone regardless of whether a space, comma, pipe or colon precedes it.
_CUSTOM_TOKEN = (
    r"(?<![A-Za-z0-9@._%+\-])"          # left boundary
    r"[A-Za-z]+\d+"                     # letters then digits, e.g. Eagles211
    r"@?"                               # optional trailing @ marker
    r"(?![A-Za-z0-9@])"                 # right boundary: not an email local part
)

# custom_field_1 and custom_field_2 share the same structure by default (per the
# spec they are "the same general shape ... reusing the same regex structure").
# They are separate compiled objects so either can be swapped for a distinct
# pattern without touching the other.
CUSTOM_FIELD_1_RE: Pattern[str] = re.compile(_CUSTOM_TOKEN)
CUSTOM_FIELD_2_RE: Pattern[str] = re.compile(_CUSTOM_TOKEN)


# Registry consumed by the extractor. Order defines column order.
FIELD_PATTERNS: Dict[str, Pattern[str]] = {
    "email": EMAIL_RE,
    "link": URL_RE,
    "custom_field_1": CUSTOM_FIELD_1_RE,
    "custom_field_2": CUSTOM_FIELD_2_RE,
}


def default_search_pattern() -> Pattern[str]:
    """Return an OR of every field pattern.

    Used by Stage 1 when the caller supplies no explicit ``--pattern``: a line is
    "interesting" if it contains at least one extractable field.
    """

    return re.compile(
        "|".join(f"(?:{p.pattern})" for p in FIELD_PATTERNS.values())
    )


# ---------------------------------------------------------------------------
# Test cases — proof the patterns are delimiter-agnostic.
# ---------------------------------------------------------------------------
# Each entry: (input_line, expected_matches). The same field type is presented
# separated by commas, spaces, pipes, colons and mixtures. These are asserted in
# tests/test_patterns.py and can be run directly (see __main__ below).
TEST_CASES: Dict[str, List[Tuple[str, List[str]]]] = {
    "email": [
        ("comma,jane@acme.io,end", ["jane@acme.io"]),
        ("space jane@acme.io end", ["jane@acme.io"]),
        ("pipe|jane@acme.io|end", ["jane@acme.io"]),
        ("colon:jane@acme.io:end", ["jane@acme.io"]),          # trailing : excluded
        ("jane@acme.io:8080|bob@sub.example.co.uk", ["jane@acme.io", "bob@sub.example.co.uk"]),
        ("mix ,|:a.b+tag@mail-server.com:|,", ["a.b+tag@mail-server.com"]),
        ("no email here 12345", []),
    ],
    "link": [
        ("comma,https://acme.io/path,end", ["https://acme.io/path"]),
        ("space http://acme.io/a?b=1 end", ["http://acme.io/a?b=1"]),
        ("pipe|https://acme.io/x|end", ["https://acme.io/x"]),   # leading | excluded
        ("colon www.acme.io:Eagles211", ["www.acme.io"]),        # colon-delimiter, not port
        ("port https://acme.io:8443/p#frag next", ["https://acme.io:8443/p#frag"]),
        ("frag:delim https://docs.acme.io/g#intro:Tigers12:next", ["https://docs.acme.io/g#intro"]),
        ("trail (https://en.wikipedia.org/wiki/Foo_(bar)).", ["https://en.wikipedia.org/wiki/Foo_(bar)"]),
        ("mixed |https://acme.io/q?x=1&y=2|,", ["https://acme.io/q?x=1&y=2"]),
    ],
    "custom_field_1": [
        ("comma,Eagles211@,end", ["Eagles211@"]),
        ("space Eagles211 end", ["Eagles211"]),
        ("pipe|Falcons88@|end", ["Falcons88@"]),
        ("colon:Bears00:end", ["Bears00"]),
        ("email-not-token Eagles211@acme.io", []),               # @ + domain -> email, not token
        ("mix ,|Eagles211@:| Falcons88 ", ["Eagles211@", "Falcons88"]),
        ("noDigits Word here", []),
    ],
}
# custom_field_2 shares the structure of custom_field_1.
TEST_CASES["custom_field_2"] = TEST_CASES["custom_field_1"]


def _run_selftest() -> int:
    """Run TEST_CASES and print a pass/fail line per field. Returns exit code."""

    failures = 0
    for field_name, cases in TEST_CASES.items():
        pattern = FIELD_PATTERNS[field_name]
        for line, expected in cases:
            if field_name == "link":
                got = [strip_url(m.group(0)) for m in pattern.finditer(line)]
            else:
                got = [m.group(0) for m in pattern.finditer(line)]
            status = "ok" if got == expected else "FAIL"
            if got != expected:
                failures += 1
            print(f"[{status}] {field_name}: {line!r} -> {got}  (expected {expected})")
    print(f"\n{failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":  # pragma: no cover - manual demonstration entry point
    raise SystemExit(_run_selftest())
