"""Unit tests for tools/gen_fixtures.py (the synthetic demo-data generator).

Kept fast: every test here uses a small, explicit scale (few files, few
lines, no big file) rather than the ~54k-line default.
"""

from __future__ import annotations

import hashlib
import math
import os
from pathlib import Path

import gen_fixtures  # from tests/conftest.py's sys.path addition
import pytest

from dump_parser.patterns import CUSTOM_FIELD_1_RE, EMAIL_RE

SAMPLE_DATA_DIR = Path(__file__).resolve().parent.parent / "sample_data"


def _small_config(out_dir: Path, **overrides) -> gen_fixtures.GenConfig:
    defaults = dict(seed=7, files=3, lines_per_file=25, big_file_lines=0, reuse_rate=0.15)
    defaults.update(overrides)
    return gen_fixtures.GenConfig(out_dir=str(out_dir), **defaults)


def _hash_dir(path: Path) -> str:
    digest = hashlib.sha256()
    for root, _dirs, files in sorted(os.walk(path)):
        for name in sorted(files):
            full = Path(root, name)
            digest.update(str(full.relative_to(path)).encode())
            digest.update(full.read_bytes())
    return digest.hexdigest()


def test_same_seed_is_byte_identical(tmp_path):
    out_a = tmp_path / "a"
    out_b = tmp_path / "b"
    manifest_a = gen_fixtures.generate(_small_config(out_a))
    manifest_b = gen_fixtures.generate(_small_config(out_b))

    assert _hash_dir(out_a) == _hash_dir(out_b)
    assert manifest_a == manifest_b


def test_different_seed_differs(tmp_path):
    out_a = tmp_path / "a"
    out_b = tmp_path / "b"
    gen_fixtures.generate(_small_config(out_a, seed=7))
    gen_fixtures.generate(_small_config(out_b, seed=8))

    assert _hash_dir(out_a) != _hash_dir(out_b)


def test_generated_values_never_match_sample_data(tmp_path):
    out = tmp_path / "demo"
    gen_fixtures.generate(_small_config(out, files=4, lines_per_file=30))

    generated_text = ""
    for path in sorted(out.rglob("*.txt")):
        generated_text += path.read_bytes().decode("latin-1")

    known_values: set[str] = set()
    for path in SAMPLE_DATA_DIR.rglob("*.txt"):
        text = path.read_bytes().decode("latin-1")
        known_values.update(EMAIL_RE.findall(text))
        known_values.update(CUSTOM_FIELD_1_RE.findall(text))

    assert known_values, "sanity check: sample_data should contain extractable values"
    for value in known_values:
        assert value not in generated_text


def test_reuse_rate_zero_produces_no_clusters(tmp_path):
    out = tmp_path / "demo"
    manifest = gen_fixtures.generate(_small_config(out, files=4, lines_per_file=50, reuse_rate=0.0))

    assert manifest["pool_size"]["custom_field_1"] == 0
    assert manifest["pool_assignment_count"]["custom_field_1"] == 0
    assert manifest["reuse_clusters"]["custom_field_1"] == []
    assert manifest["reuse_clusters"]["custom_field_2"] == []


def test_reuse_rate_produces_expected_approximate_pool_draws(tmp_path):
    out = tmp_path / "demo"
    reuse_rate = 0.2
    manifest = gen_fixtures.generate(_small_config(out, files=6, lines_per_file=120, reuse_rate=reuse_rate))

    eligible = manifest["eligible_slot_count"]["custom_field_1"]
    actual = manifest["pool_assignment_count"]["custom_field_1"]
    expected = eligible * reuse_rate
    # Each eligible slot independently draws from the pool with probability
    # reuse_rate -- a Binomial(eligible, reuse_rate) process -- so allow a
    # generous multiple of its standard deviation rather than pinning an
    # exact count.
    tolerance = 4 * math.sqrt(eligible * reuse_rate * (1 - reuse_rate)) + 2
    assert abs(actual - expected) <= tolerance
    # With this many draws over a small pool, at least one real reuse
    # cluster (2+ distinct emails sharing a value) should have formed.
    assert len(manifest["reuse_clusters"]["custom_field_1"]) >= 1
    assert manifest["reuse_clusters"]["custom_field_1"] == manifest["reuse_clusters"]["custom_field_2"]


def test_manifest_and_files_agree_on_distinct_emails(tmp_path):
    out = tmp_path / "demo"
    manifest = gen_fixtures.generate(_small_config(out, files=3, lines_per_file=40))

    found_emails: set[str] = set()
    for rel_path in manifest["files"]:
        if rel_path.split("/")[0] != "regular":
            continue
        text = (out / rel_path).read_bytes().decode("latin-1")
        found_emails.update(EMAIL_RE.findall(text))

    assert found_emails
    assert len(found_emails) == manifest["distinct_emails"]


def test_edge_cases_present_at_minimal_scale(tmp_path):
    out = tmp_path / "demo"
    manifest = gen_fixtures.generate(_small_config(out, files=2, lines_per_file=5, big_file_lines=0))

    # nested subdirectory
    assert any(f.startswith("regular/nested/") for f in manifest["files"])
    # a non-UTF-8 (Latin-1) file
    latin1_files = [f for f in manifest["files"] if f.endswith("_latin1.txt")]
    assert latin1_files
    raw = (out / latin1_files[0]).read_bytes()
    with pytest.raises(UnicodeDecodeError):
        raw.decode("utf-8")
    raw.decode("latin-1")  # must not raise

    # at least one genuinely empty (no-match) line, forced on the first file
    first_file = out / sorted(f for f in manifest["files"] if f.startswith("regular/nested/"))[0]
    first_line = first_file.read_text(encoding="utf-8").splitlines()[0]
    assert "@" not in first_line and "http" not in first_line and "www." not in first_line


def test_big_file_written_separately_from_regular(tmp_path):
    out = tmp_path / "demo"
    manifest = gen_fixtures.generate(_small_config(out, files=2, lines_per_file=5, big_file_lines=10))

    assert "big/big_dump.txt" in manifest["files"]
    assert (out / "big" / "big_dump.txt").exists()
    assert sum(1 for f in manifest["files"] if f.split("/")[0] == "regular") == 2
