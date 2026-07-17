"""End-to-end Stage 1 -> Stage 2 -> output tests, including the CLI."""

from dump_parser import cli, extractor, scanner


def _make_dump(tmp_path):
    p = tmp_path / "dump.txt"
    p.write_text(
        "jane@acme.io,https://acme.io/p,Eagles211@,Falcons88\n"  # comma
        "bob@corp.net https://corp.net/x Ravens77 Hawks909@\n"  # space
        "carol@x.io|www.x.io/y|Bears00@|Lions55\n"  # pipe
        "dave@x.io:https://x.io/z#a:Tigers12:Panthers34@\n"  # colon/mixed
        "prose with no extractable fields at all\n",
        encoding="utf-8",
    )
    return p


def test_full_pipeline_rows(tmp_path):
    _make_dump(tmp_path)
    matches, summary = scanner.scan_paths(str(tmp_path), scheduler="synchronous")
    rows = extractor.build_stage2_frame(matches)
    assert summary.stage1_matches == 4  # prose line excluded

    by_line = rows.set_index("line_number")
    assert by_line.loc[1, "email"] == "jane@acme.io"
    assert by_line.loc[1, "link"] == "https://acme.io/p"
    assert by_line.loc[1, "custom_field_1"] == "Eagles211@|Falcons88"
    # colon-delimited line: email/link don't bleed across ':'
    assert by_line.loc[4, "email"] == "dave@x.io"
    assert by_line.loc[4, "link"] == "https://x.io/z#a"
    assert by_line.loc[4, "custom_field_1"] == "Tigers12|Panthers34@"


def test_cli_writes_csv(tmp_path):
    _make_dump(tmp_path)
    base = tmp_path / "out" / "results"
    rc = cli.main([str(tmp_path), "-o", str(base), "--scheduler", "synchronous", "--no-summary"])
    assert rc == 0

    csv_text = (tmp_path / "out" / "results.csv").read_text(encoding="utf-8")
    assert "jane@acme.io" in csv_text
    assert csv_text.splitlines()[0] == "file,line_number,email,link,custom_field_1,custom_field_2,source_line"


def test_cli_domain_search_pattern(tmp_path):
    p = tmp_path / "leak.txt"
    p.write_text(
        "user1@blueshiftdefense.com,https://x.io/a,Eagles211@,Falcons88\n"
        "user2@other.com,https://x.io/b,Hawks909@,Ravens77\n",
        encoding="utf-8",
    )
    stage1 = tmp_path / "hits.csv"
    cli.main(
        [
            str(tmp_path),
            "-p",
            "@blueshiftdefense.com",
            "--stage1-only",
            "-o",
            str(stage1),
            "--scheduler",
            "synchronous",
            "--no-summary",
        ]
    )
    text = stage1.read_text(encoding="utf-8")
    assert "user1@blueshiftdefense.com" in text
    assert "user2@other.com" not in text


def test_cli_stage1_then_stage2_roundtrip(tmp_path):
    _make_dump(tmp_path)
    stage1 = tmp_path / "hits.csv"
    cli.main([str(tmp_path), "--stage1-only", "-o", str(stage1), "--scheduler", "synchronous", "--no-summary"])

    parsed = tmp_path / "parsed.csv"
    cli.main([str(stage1), "--stage2-only", "-o", str(parsed), "--no-summary"])

    text = parsed.read_text(encoding="utf-8")
    assert "Eagles211@" in text
    assert "https://acme.io/p" in text


def test_cli_blockwise_equivalent(tmp_path):
    _make_dump(tmp_path)
    base_a = tmp_path / "stream"
    base_b = tmp_path / "block"
    cli.main([str(tmp_path), "-o", str(base_a), "--scheduler", "synchronous", "--no-summary"])
    cli.main([str(tmp_path), "-o", str(base_b), "--blocksize", "24", "--scheduler", "synchronous", "--no-summary"])
    assert (tmp_path / "stream.csv").read_text() == (tmp_path / "block.csv").read_text()
