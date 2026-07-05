"""Stage 2 extraction tests: joining, exploding, dedup, delimiter-agnostic input."""

from dump_parser.extractor import extract_all, extract_fields, to_rows
from dump_parser.models import Stage1Match


def _match(source_line):
    return Stage1Match("f.txt", 1, "", "any-field", source_line)


def test_extract_fields_mixed_delimiters():
    line = "jane@acme.io,https://acme.io/p|Eagles211@ Falcons88"
    fields = extract_fields(line)
    assert fields["email"] == ["jane@acme.io"]
    assert fields["link"] == ["https://acme.io/p"]
    assert fields["custom_field_1"] == ["Eagles211@", "Falcons88"]


def test_joined_row_pipe_delimits_multiple():
    rows = to_rows(_match("a@x.io b@y.io Eagles211@ Falcons88"))
    assert len(rows) == 1
    assert rows[0].email == "a@x.io|b@y.io"
    assert rows[0].custom_field_1 == "Eagles211@|Falcons88"


def test_dedup_within_cell():
    rows = to_rows(_match("a@x.io, a@x.io, Colts03@, Colts03@"))
    assert rows[0].email == "a@x.io"
    assert rows[0].custom_field_1 == "Colts03@"


def test_one_row_per_match_explodes():
    rows = to_rows(_match("a@x.io https://x.io/p Eagles211@"), one_row_per_match=True)
    # one email + one link + (custom token counted for both cf1 and cf2)
    values = [(r.email, r.link, r.custom_field_1, r.custom_field_2) for r in rows]
    assert ("a@x.io", "", "", "") in values
    assert ("", "https://x.io/p", "", "") in values
    assert ("", "", "Eagles211@", "") in values


def test_matched_line_without_fields_still_yields_row():
    rows = to_rows(_match("nothing extractable here"), one_row_per_match=True)
    assert len(rows) == 1
    assert rows[0].source_line == "nothing extractable here"


def test_extract_all_preserves_order():
    matches = [_match("a@x.io"), _match("b@y.io")]
    rows = extract_all(matches)
    assert [r.email for r in rows] == ["a@x.io", "b@y.io"]
