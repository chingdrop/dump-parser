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
    rc = cli.main([str(tmp_path), "-o", str(base), "--scheduler", "synchronous", "--no-summary", "--no-redact"])
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
            "--no-redact",
        ]
    )
    text = stage1.read_text(encoding="utf-8")
    assert "user1@blueshiftdefense.com" in text
    assert "user2@other.com" not in text


def test_cli_stage1_then_stage2_roundtrip(tmp_path):
    _make_dump(tmp_path)
    stage1 = tmp_path / "hits.csv"
    cli.main(
        [str(tmp_path), "--stage1-only", "-o", str(stage1), "--scheduler", "synchronous", "--no-summary", "--no-redact"]
    )

    parsed = tmp_path / "parsed.csv"
    cli.main([str(stage1), "--stage2-only", "-o", str(parsed), "--no-summary", "--no-redact"])

    text = parsed.read_text(encoding="utf-8")
    assert "Eagles211@" in text
    assert "https://acme.io/p" in text


def test_cli_redaction_is_default(tmp_path):
    _make_dump(tmp_path)
    base = tmp_path / "out" / "results"
    rc = cli.main([str(tmp_path), "-o", str(base), "--scheduler", "synchronous", "--no-summary"])
    assert rc == 0

    csv_text = (tmp_path / "out" / "results.csv").read_text(encoding="utf-8")
    header = csv_text.splitlines()[0]
    assert header == "file,line_number,email,link,custom_field_1,custom_field_2"
    assert "source_line" not in header
    # Emails/links stay visible; plaintext tokens do not appear.
    assert "jane@acme.io" in csv_text
    for token in ("Eagles211@", "Falcons88", "Ravens77", "Tigers12"):
        assert token not in csv_text


def test_cli_no_redact_warns_and_keeps_plaintext(tmp_path, capsys):
    _make_dump(tmp_path)
    base = tmp_path / "out" / "plain"
    rc = cli.main([str(tmp_path), "-o", str(base), "--scheduler", "synchronous", "--no-summary", "--no-redact"])
    assert rc == 0
    err = capsys.readouterr().err
    assert "WARNING: --no-redact outputs plaintext credential-shaped data" in err

    csv_text = (tmp_path / "out" / "plain.csv").read_text(encoding="utf-8")
    assert "Eagles211@" in csv_text
    assert "source_line" in csv_text.splitlines()[0]


def test_cli_report_produces_markdown(tmp_path):
    _make_dump(tmp_path)
    base = tmp_path / "out" / "results"
    report_path = tmp_path / "out" / "report.md"
    rc = cli.main(
        [
            str(tmp_path),
            "-o",
            str(base),
            "--report",
            str(report_path),
            "--scheduler",
            "synchronous",
            "--no-summary",
        ]
    )
    assert rc == 0
    md = report_path.read_text(encoding="utf-8")
    assert "## Exposure Summary" in md
    assert "## Password Reuse" in md
    # No plaintext token leaks into the report either.
    assert "Eagles211@" not in md


def test_cli_report_with_stage1_only_errors(tmp_path):
    _make_dump(tmp_path)
    rc = cli.main(
        [
            str(tmp_path),
            "--stage1-only",
            "--report",
            str(tmp_path / "r.md"),
            "--scheduler",
            "synchronous",
            "--no-summary",
        ]
    )
    assert rc == 2


def test_cli_stage1_only_redaction_is_default(tmp_path):
    _make_dump(tmp_path)
    stage1 = tmp_path / "hits.csv"
    rc = cli.main([str(tmp_path), "--stage1-only", "-o", str(stage1), "--scheduler", "synchronous", "--no-summary"])
    assert rc == 0

    csv_text = stage1.read_text(encoding="utf-8")
    header = csv_text.splitlines()[0]
    assert header == "file,line_number,matched_text,pattern"
    assert "source_line" not in header
    # Emails stay visible as matched_text (an exposure finding); tokens do not.
    assert "jane@acme.io" in csv_text
    for token in ("Eagles211@", "Falcons88", "Ravens77", "Tigers12"):
        assert token not in csv_text


def test_cli_stage1_only_no_redact_keeps_plaintext(tmp_path, capsys):
    _make_dump(tmp_path)
    stage1 = tmp_path / "hits.csv"
    rc = cli.main(
        [str(tmp_path), "--stage1-only", "-o", str(stage1), "--scheduler", "synchronous", "--no-summary", "--no-redact"]
    )
    assert rc == 0
    assert "WARNING: --no-redact outputs plaintext credential-shaped data" in capsys.readouterr().err

    csv_text = stage1.read_text(encoding="utf-8")
    assert "source_line" in csv_text.splitlines()[0]
    assert "Eagles211@" in csv_text


def test_cli_stage2_only_on_redacted_stage1_dump_errors_clearly(tmp_path):
    _make_dump(tmp_path)
    stage1 = tmp_path / "hits.csv"
    cli.main([str(tmp_path), "--stage1-only", "-o", str(stage1), "--scheduler", "synchronous", "--no-summary"])

    rc = cli.main([str(stage1), "--stage2-only", "-o", str(tmp_path / "parsed.csv"), "--no-summary"])
    assert rc == 2


def test_cli_blockwise_equivalent(tmp_path):
    _make_dump(tmp_path)
    base_a = tmp_path / "stream"
    base_b = tmp_path / "block"
    # --no-redact: redacted runs use a fresh salt each, so hashes differ by design.
    common = ["--scheduler", "synchronous", "--no-summary", "--no-redact"]
    cli.main([str(tmp_path), "-o", str(base_a), *common])
    cli.main([str(tmp_path), "-o", str(base_b), "--blocksize", "24", *common])
    assert (tmp_path / "stream.csv").read_text() == (tmp_path / "block.csv").read_text()
