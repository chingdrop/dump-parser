#!/usr/bin/env python3
"""Print a concise terminal summary after `make demo` runs the pipeline over
the generated fixtures. Dev-only, kept alongside gen_fixtures.py in tools/,
not part of the installed package.
"""

from __future__ import annotations

import argparse
import json
import os


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--demo-data", default="demo_data")
    parser.add_argument("--demo-output", default="demo_output")
    args = parser.parse_args(argv)

    with open(os.path.join(args.demo_data, "manifest.json"), encoding="utf-8") as fh:
        manifest = json.load(fh)

    regular_files = [f for f in manifest["files"] if f.split("/")[0] == "regular"]
    regular_lines = len(regular_files) * manifest["lines_per_file"]

    results_path = os.path.join(args.demo_output, "results.csv")
    with open(results_path, encoding="utf-8") as fh:
        row_count = sum(1 for _ in fh) - 1  # exclude header

    clusters = manifest["reuse_clusters"]["custom_field_1"]

    print("=" * 55)
    print(f"dump-parser demo  ({args.demo_data}/regular -> {args.demo_output}/)")
    print("=" * 55)
    print(f"  files scanned        : {len(regular_files)}")
    print(f"  lines scanned        : {regular_lines}")
    print(f"  Stage 2 rows written : {row_count}")
    print(f"  distinct emails      : {manifest['distinct_emails']}")
    print(f"  reuse clusters found : {len(clusters)}  (custom_field_1/2; deliberately injected, see docs/demo.md)")
    print("=" * 55)
    print(f"CSV:    {results_path}")
    print(f"Report: {os.path.join(args.demo_output, 'report.md')}")
    return 0


if __name__ == "__main__":  # pragma: no cover - manual entry point
    raise SystemExit(main())
