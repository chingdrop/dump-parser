"""Stage 1 scanner tests: line numbers, block-splitting equivalence, encoding."""

import os

import pytest

from dump_parser import scanner

# Use the synchronous scheduler in tests so results are deterministic and there
# is no process-spawn overhead.
SYNC = {"scheduler": "synchronous"}


@pytest.fixture
def dump_dir(tmp_path):
    (tmp_path / "a.txt").write_text(
        "jane@acme.io,Eagles211@\n"
        "no fields here\n"
        "pipe|https://acme.io/x|Falcons88\n",
        encoding="utf-8",
    )
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.txt").write_text("bob@corp.net Storm21@\n", encoding="utf-8")
    return tmp_path


def test_discovers_txt_recursively(dump_dir):
    files = scanner.discover_files(str(dump_dir))
    assert len(files) == 2
    assert any(f.endswith(os.path.join("sub", "b.txt")) for f in files)


def test_line_numbers_are_correct(dump_dir):
    df, summary = scanner.scan_paths(str(dump_dir), **SYNC)
    by_line = set(zip(df["file"].apply(os.path.basename), df["line_number"]))
    assert ("a.txt", 1) in by_line
    assert ("a.txt", 3) in by_line  # blank/no-field line 2 is skipped, numbering intact
    assert ("b.txt", 1) in by_line
    assert summary.lines_scanned == 4  # 3 + 1
    assert summary.stage1_matches == 3


def test_blockwise_matches_streaming(dump_dir):
    df_stream, _ = scanner.scan_paths(str(dump_dir), **SYNC)
    # Tiny blocksize forces splits mid-line and mid-file.
    df_block, _ = scanner.scan_paths(str(dump_dir), blocksize=16, **SYNC)
    key = lambda df: sorted(zip(df["file"], df["line_number"], df["source_line"]))
    assert key(df_stream) == key(df_block)


def test_block_never_truncates_long_line(tmp_path):
    # A line far longer than the blocksize must survive intact.
    long_line = "x" * 500 + " jane@acme.io " + "y" * 500
    (tmp_path / "big.txt").write_text(long_line + "\n", encoding="utf-8")
    df, _ = scanner.scan_paths(str(tmp_path), blocksize=32, **SYNC)
    assert len(df) == 1
    assert df.iloc[0]["source_line"] == long_line
    assert df.iloc[0]["line_number"] == 1


def test_non_utf8_falls_back(tmp_path):
    p = tmp_path / "latin.txt"
    p.write_bytes("café@x.io Eagles211@\n".encode("latin-1"))
    df, summary = scanner.scan_paths(str(tmp_path), **SYNC)
    # No crash; file scanned and flagged as fallback.
    assert summary.files_scanned == 1
    assert str(p) in summary.fallback_files
    # The ASCII token is still recovered from the fallback-decoded line.
    assert (df["line_number"] == 1).any()


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses file permissions")
def test_unreadable_file_recorded(tmp_path):
    good = tmp_path / "good.txt"
    good.write_text("x@y.io\n", encoding="utf-8")
    bad = tmp_path / "bad.txt"
    bad.write_text("z@y.io\n", encoding="utf-8")
    os.chmod(bad, 0o000)  # make it unreadable
    try:
        df, summary = scanner.scan_paths(str(tmp_path), **SYNC)
    finally:
        os.chmod(bad, 0o644)  # restore so pytest can clean up
    assert summary.files_scanned == 1  # only good.txt
    assert len(summary.failed_files) == 1
    assert summary.failed_files[0][0] == str(bad)


def test_custom_search_pattern(dump_dir):
    import re

    patterns = [("digits", re.compile(r"\d{4,}"))]
    df, _ = scanner.scan_paths(str(dump_dir), patterns=patterns, **SYNC)
    # Only lines containing 4+ consecutive digits match; none of our lines do.
    assert df.empty
