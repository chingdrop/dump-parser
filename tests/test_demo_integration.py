"""End-to-end test: generator -> CLI pipeline -> compare against the
generator's own manifest (the source of truth for what was injected).

No slow/integration marker exists elsewhere in this suite, so this is kept
fast (a handful of files/lines, no big file) rather than gated behind one.
"""

from __future__ import annotations

import csv
import re

import gen_fixtures  # from tests/conftest.py's sys.path addition

from dump_parser import cli


def _cluster_sizes_in_section(report_text: str, column: str) -> list[int]:
    section = next(s for s in report_text.split("### ") if s.startswith(column))
    return sorted(int(n) for n in re.findall(r": (\d+) distinct accounts share a value", section))


def test_generator_pipeline_matches_manifest(tmp_path):
    demo_data = tmp_path / "demo_data"
    manifest = gen_fixtures.generate(
        gen_fixtures.GenConfig(
            out_dir=str(demo_data),
            seed=99,
            files=5,
            lines_per_file=80,
            big_file_lines=0,
            reuse_rate=0.2,
        )
    )

    out_base = tmp_path / "out" / "results"
    report_path = tmp_path / "out" / "report.md"
    rc = cli.main(
        [
            str(demo_data / "regular"),
            "-o",
            str(out_base),
            "--report",
            str(report_path),
            "--scheduler",
            "synchronous",
            "--no-summary",
        ]
    )
    assert rc == 0

    with open(tmp_path / "out" / "results.csv", newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert list(rows[0].keys()) == ["file", "line_number", "email", "link", "custom_field_1", "custom_field_2"]

    # Distinct emails: the CSV column, redacted or not, still carries plain
    # emails (they're an exposure finding, never hashed) -- count them the
    # same way the manifest does.
    csv_emails = {row["email"] for row in rows if row["email"]}
    assert len(csv_emails) == manifest["distinct_emails"]

    report_text = report_path.read_text(encoding="utf-8")
    assert f"Distinct email addresses: {manifest['distinct_emails']}" in report_text

    manifest_clusters = manifest["reuse_clusters"]["custom_field_1"]
    expected_sizes = sorted(len(c["emails"]) for c in manifest_clusters)
    for column in ("custom_field_1", "custom_field_2"):
        if manifest_clusters:
            assert _cluster_sizes_in_section(report_text, column) == expected_sizes
        else:
            section = next(s for s in report_text.split("### ") if s.startswith(column))
            assert "No reuse clusters found" in section


def test_generator_pipeline_no_redact_preserves_plaintext(tmp_path):
    demo_data = tmp_path / "demo_data"
    gen_fixtures.generate(
        gen_fixtures.GenConfig(
            out_dir=str(demo_data), seed=3, files=2, lines_per_file=15, big_file_lines=0, reuse_rate=0.15
        )
    )

    out_base = tmp_path / "out" / "plain"
    rc = cli.main(
        [
            str(demo_data / "regular"),
            "-o",
            str(out_base),
            "--scheduler",
            "synchronous",
            "--no-summary",
            "--no-redact",
        ]
    )
    assert rc == 0

    csv_text = (tmp_path / "out" / "plain.csv").read_text(encoding="utf-8")
    assert "source_line" in csv_text.splitlines()[0]


def test_generator_pipeline_stage1_only_redacted_by_default(tmp_path):
    demo_data = tmp_path / "demo_data"
    gen_fixtures.generate(
        gen_fixtures.GenConfig(
            out_dir=str(demo_data), seed=4, files=2, lines_per_file=15, big_file_lines=0, reuse_rate=0.15
        )
    )

    stage1_out = tmp_path / "out" / "hits"
    rc = cli.main(
        [
            str(demo_data / "regular"),
            "--stage1-only",
            "-o",
            str(stage1_out),
            "--scheduler",
            "synchronous",
            "--no-summary",
        ]
    )
    assert rc == 0

    header = (tmp_path / "out" / "hits.csv").read_text(encoding="utf-8").splitlines()[0]
    assert header == "file,line_number,matched_text,pattern"
