"""Per-field regex tests covering every delimiter variant.

Driven by the ``TEST_CASES`` table in ``dump_parser.patterns`` plus a handful of
targeted delimiter-bleed regression checks.
"""

import pytest

from dump_parser.patterns import (
    FIELD_PATTERNS,
    TEST_CASES,
    strip_url,
)


def _extract(field_name, line):
    pattern = FIELD_PATTERNS[field_name]
    if field_name == "link":
        return [strip_url(m.group(0)) for m in pattern.finditer(line)]
    return [m.group(0) for m in pattern.finditer(line)]


@pytest.mark.parametrize(
    "field_name,line,expected",
    [(fn, line, expected) for fn, cases in TEST_CASES.items() for line, expected in cases],
)
def test_table_cases(field_name, line, expected):
    assert _extract(field_name, line) == expected


# --- Delimiter-bleed regressions -----------------------------------------


@pytest.mark.parametrize("delim", [",", " ", "|", ":"])
def test_email_all_delimiters(delim):
    line = f"a{delim}jane@acme.io{delim}b"
    assert _extract("email", line) == ["jane@acme.io"]


def test_email_trailing_colon_not_consumed():
    assert _extract("email", "jane@acme.io:8080") == ["jane@acme.io"]


def test_url_leading_pipe_not_consumed():
    assert _extract("link", "|https://acme.io/x") == ["https://acme.io/x"]


def test_url_colon_delimiter_vs_port():
    # colon-as-delimiter stops the host; real digit port is kept
    assert _extract("link", "www.acme.io:Eagles211") == ["www.acme.io"]
    assert _extract("link", "https://acme.io:8443/p") == ["https://acme.io:8443/p"]


@pytest.mark.parametrize("delim", [",", " ", "|", ":"])
def test_custom_all_delimiters(delim):
    line = f"x{delim}Eagles211@{delim}y"
    assert _extract("custom_field_1", line) == ["Eagles211@"]


def test_custom_not_email_localpart():
    assert _extract("custom_field_1", "Eagles211@acme.io") == []


def test_custom_field_2_same_as_1():
    line = "a,Eagles211@,b"
    assert _extract("custom_field_1", line) == _extract("custom_field_2", line)


def test_strip_url_keeps_balanced_bracket():
    raw = "https://en.wikipedia.org/wiki/Foo_(bar)"
    assert strip_url(raw + ").") == raw
