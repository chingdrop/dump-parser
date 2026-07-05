"""End-to-end Stage 1 -> Stage 2 -> output tests, including the CLI."""

import json
import os

from dump_parser import cli, extractor, output, scanner


def _make_dump(tmp_path):
    p = tmp_path / "dump.txt"
    p.write_text(
        "jane@acme.io,https://acme.io/p,Eagles211@,Falcons88\n"       # comma
        "bob@corp.net https://corp.net/x Ravens77 Hawks909@\n"        # space
        "carol@x.io|www.x.io/y|Bears00@|Lions55\n"                    # pipe
        "dave@x.io:https://x.io/z#a:Tigers12:Panthers34@\n"           # colon/mixed
        "prose with no extractable fields at all\n",
        encoding="utf-8",
    )
    return p


def test_full_pipeline_rows(tmp_path):
    _make_dump(tmp_path)
    matches, summary = scanner.scan_paths(str(tmp_path), scheduler="synchronous")
    rows = extractor.extract_all(matches)
    assert summary.stage1_matches == 4  # prose line excluded

    by_line = {r.line_number: r for r in rows}
    assert by_line[1].email == "jane@acme.io"
    assert by_line[1].link == "https://acme.io/p"
    assert by_line[1].custom_field_1 == "Eagles211@|Falcons88"
    # colon-delimited line: email/link don't bleed across ':'
    assert by_line[4].email == "dave@x.io"
    assert by_line[4].link == "https://x.io/z#a"
    assert by_line[4].custom_field_1 == "Tigers12|Panthers34@"


def test_cli_csv_and_json(tmp_path):
    _make_dump(tmp_path)
    base = tmp_path / "out" / "results"
    rc = cli.main([str(tmp_path), "-o", str(base), "--format", "both", "--no-summary"])
    assert rc == 0

    csv_text = (tmp_path / "out" / "results.csv").read_text(encoding="utf-8")
    assert "jane@acme.io" in csv_text
    assert csv_text.splitlines()[0] == "file,line_number,email,link,custom_field_1,custom_field_2,source_line"

    data = json.loads((tmp_path / "out" / "results.json").read_text(encoding="utf-8"))
    assert any(row["email"] == "jane@acme.io" for row in data)


def test_cli_stage1_then_stage2_roundtrip(tmp_path):
    _make_dump(tmp_path)
    stage1 = tmp_path / "hits.json"
    cli.main([str(tmp_path), "--stage1-only", "-o", str(stage1), "--format", "json", "--no-summary"])

    parsed = tmp_path / "parsed.csv"
    cli.main([str(stage1), "--stage2-only", "-o", str(parsed), "--no-summary"])

    text = parsed.read_text(encoding="utf-8")
    assert "Eagles211@" in text
    assert "https://acme.io/p" in text


def test_cli_blockwise_equivalent(tmp_path):
    _make_dump(tmp_path)
    base_a = tmp_path / "stream"
    base_b = tmp_path / "block"
    cli.main([str(tmp_path), "-o", str(base_a), "--no-summary"])
    cli.main([str(tmp_path), "-o", str(base_b), "--blocksize", "24", "--no-summary"])
    assert (tmp_path / "stream.csv").read_text() == (tmp_path / "block.csv").read_text()
