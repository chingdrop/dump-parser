#!/usr/bin/env python3
"""
One-page results sheet for the README: what `make demo` does to a synthetic,
mixed-delimiter dump, and whether its output matches what the generator
injected.

Every number and example comes from one `make demo` run: the raw lines in
demo_data/regular/, the generator's demo_data/manifest.json (ground truth),
and the pipeline's demo_output/results.csv and report.md. Nothing on the
sheet is typed in by hand.

    make demo
    uv run python tools/results_sheet.py                            # HTML only
    uv run python tools/results_sheet.py --png docs/results-sheet.png

`--png` finds Chrome, Chromium, Edge, or Brave on its own -- including the
Chromium vhs downloads for docs/demo.tape -- or takes `--chrome <path>`, and
also needs ffmpeg. Synthetic data only.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import shutil
import subprocess
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dump_parser.patterns import FIELD_PATTERNS

WIDTH = 1400  # CSS px; the sheet's body width
SCALE = 2  # device pixel ratio of the PNG

FIELDS = ["email", "link", "custom_field_1", "custom_field_2"]
# custom_field_1/2 share one regex, so a raw line highlights it once, as "token".
SPAN_FIELDS = [("email", "email"), ("link", "link"), ("custom_field_1", "token")]
DELIMITERS = {",": "Comma", " ": "Space", "|": "Pipe", ":": "Colon"}
STYLE_ORDER = ["Comma", "Space", "Pipe", "Colon", "Mixed"]
CLUSTER_RE = re.compile(r": (\d+) distinct accounts share a value")


@dataclass
class Span:
    start: int
    end: int
    kind: str


def field_spans(line: str) -> list[Span]:
    """Where each field regex matches `line`, dropping any span that overlaps
    an earlier, longer one (e.g. a token-shaped run inside a URL path)."""
    found = [
        Span(m.start(), m.end(), kind) for field, kind in SPAN_FIELDS for m in FIELD_PATTERNS[field].finditer(line)
    ]
    kept: list[Span] = []
    for span in sorted(found, key=lambda s: (s.start, -(s.end - s.start))):
        if not kept or span.start >= kept[-1].end:
            kept.append(span)
    return kept


def delimiter_style(line: str, spans: list[Span]) -> str | None:
    """The delimiter style of a line: "Comma", "Space", ... when one delimiter separates every field on the
    line, "Mixed" when several do, None when there is nothing between fields."""
    gaps = [line[a.end : b.start] for a, b in zip(spans, spans[1:], strict=False)]
    used = {DELIMITERS[c] for gap in gaps for c in gap if c in DELIMITERS}
    if not used:
        return None
    return used.pop() if len(used) == 1 else "Mixed"


def marked(line: str, spans: list[Span]) -> str:
    out, pos = [], 0
    for span in spans:
        out.append(html.escape(line[pos : span.start]))
        out.append(f"<span class='f-{span.kind}'>{html.escape(line[span.start : span.end])}</span>")
        pos = span.end
    out.append(html.escape(line[pos:]))
    return "".join(out)


def cluster_sizes(report: str, column: str) -> list[int]:
    section = next(s for s in report.split("### ") if s.startswith(column))
    return sorted(int(n) for n in CLUSTER_RE.findall(section))


def load(demo_data: Path, demo_output: Path) -> dict[str, Any]:
    manifest = json.loads((demo_data / "manifest.json").read_text(encoding="utf-8"))
    with open(demo_output / "results.csv", newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        header = list(reader.fieldnames or [])
        rows = list(reader)
    report = (demo_output / "report.md").read_text(encoding="utf-8")
    csv_text = (demo_output / "results.csv").read_text(encoding="utf-8")

    regular = sorted(f for f in manifest["files"] if f.startswith("regular/"))
    raw: dict[str, list[str]] = {}
    for rel in regular:
        data = (demo_data / rel).read_bytes()
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("latin-1")
        raw[rel] = text.splitlines()
    return {
        "manifest": manifest,
        "header": header,
        "rows": rows,
        "report": report,
        "csv_text": csv_text,
        "raw": raw,
        "demo_data": demo_data,
    }


def build(d: dict[str, Any]) -> str:
    manifest, rows, report, raw = d["manifest"], d["rows"], d["report"], d["raw"]
    lines_scanned = sum(len(v) for v in raw.values())
    prefix = f"{d['demo_data'].name}/"
    by_key = {(r["file"].split(prefix, 1)[-1], int(r["line_number"])): r for r in rows}

    # -- checks against the manifest ---------------------------------------------
    emails = {r["email"] for r in rows if r["email"]}
    injected = sorted(len(c["emails"]) for c in manifest["reuse_clusters"]["custom_field_1"])
    found = {col: cluster_sizes(report, col) for col in ("custom_field_1", "custom_field_2")}
    tokens = {
        m.group() for lines in raw.values() for ln in lines for m in FIELD_PATTERNS["custom_field_1"].finditer(ln)
    }
    leaked = sum(1 for t in tokens if t in d["csv_text"])
    files_with_rows = {f for f, _ in by_key}
    report_emails = re.search(r"Distinct email addresses: (\d+)", report)
    n_inj = len(injected)
    n1, n2 = len(found["custom_field_1"]), len(found["custom_field_2"])
    checks = [
        (f"Distinct emails in the CSV match the manifest ({len(emails)} of {manifest['distinct_emails']})",
         len(emails) == manifest["distinct_emails"]),
        ("The report's distinct-email count matches the manifest",
         report_emails is not None and int(report_emails.group(1)) == manifest["distinct_emails"]),
        (f"custom_field_1: every injected reuse cluster found, same sizes ({n1} of {n_inj})",
         found["custom_field_1"] == injected),
        (f"custom_field_2: every injected reuse cluster found, same sizes ({n2} of {n_inj})",
         found["custom_field_2"] == injected),
        (f"No plaintext token from the input appears in the CSV ({leaked} of {len(tokens)})", leaked == 0),
        ("No source_line column in the redacted CSV", "source_line" not in d["header"]),
        (f"Every input file contributes rows, including the Latin-1 one ({len(files_with_rows)} of {len(raw)})",
         files_with_rows == set(raw)),
    ]  # fmt: skip
    passed = sum(ok for _, ok in checks)
    check_rows = "".join(
        f"<div class='check'><span class='mark {'ok' if ok else 'bad'}'>{'&#10003;' if ok else '&#10007;'}</span>"
        f"<span>{html.escape(label)}</span></div>"
        for label, ok in checks
    )

    # -- before and after: the first line of each delimiter style --------------------
    examples: dict[str, tuple[str, int, str, list[Span]]] = {}
    style_counts: Counter[str] = Counter()
    for rel, lines in raw.items():
        for n, line in enumerate(lines, start=1):
            spans = field_spans(line)
            style = delimiter_style(line, spans)
            if style is None:
                continue
            style_counts[style] += 1
            kinds = {s.kind for s in spans}
            if style not in examples and {"email", "link", "token"} <= kinds and (rel, n) in by_key:
                examples[style] = (rel, n, line, spans)
    example_html = []
    for style in STYLE_ORDER:
        if style not in examples:
            continue
        rel, n, line, spans = examples[style]
        row = by_key[(rel, n)]
        cells = "".join(
            f"<div class='cell'><div class='k'>{f}</div><div class='v f-{dict(SPAN_FIELDS).get(f, 'token')}'>"
            f"{html.escape(row[f]) or '&mdash;'}</div></div>"
            for f in FIELDS
        )
        example_html.append(f"""
      <div class="example">
        <div class="lbl">{style}<br><span class="muted">{html.escape(rel.split("/")[-1])}:{n}</span></div>
        <div class="raw mono">{marked(line, spans)}</div>
        <div></div>
        <div class="cells">{cells}</div>
      </div>""")

    # -- extracted fields and delimiter styles -------------------------------------------
    def bar(label: str, n: int, total: int) -> str:
        pct = 100 * n / total if total else 0
        return f"""
      <div class="bar-row"><div>{html.escape(label)}</div>
        <div class="bar"><div class="fill" style="width:{pct:.1f}%"></div></div>
        <div class="n">{n:,}</div></div>"""

    field_bars = "".join(bar(f, sum(1 for r in rows if r[f]), len(rows)) for f in FIELDS)
    style_total = sum(style_counts.values())
    style_bars = "".join(bar(s, style_counts[s], style_total) for s in STYLE_ORDER)

    # -- reuse cluster sizes ------------------------------------------------------------
    inj, fnd = Counter(injected), Counter(found["custom_field_1"])
    top = max([*inj.values(), *fnd.values(), 1])
    size_rows = "".join(
        f"""
      <div class="size-row"><div class="n">{size}</div>
        <div class="pair">
          <div class="bar"><div class="fill inj" style="width:{100 * inj[size] / top:.1f}%"></div></div>
          <div class="bar"><div class="fill" style="width:{100 * fnd[size] / top:.1f}%"></div></div>
        </div>
        <div class="counts">{inj[size]} / {fnd[size]}</div></div>"""
        for size in sorted(set(inj) | set(fnd))
    )

    return TEMPLATE.format(
        seed=manifest["seed"],
        files=len(raw),
        lines=f"{lines_scanned:,}",
        rows=f"{len(rows):,}",
        emails=f"{len(emails):,}",
        clusters_found=len(found["custom_field_1"]),
        clusters_injected=len(injected),
        passed=passed,
        checks_total=len(checks),
        examples="".join(example_html),
        field_bars=field_bars,
        style_bars=style_bars,
        size_rows=size_rows,
        checks=check_rows,
    )


TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>dump-parser demo results</title>
<style>
  :root {{
    --surface: #fcfcfb; --card: #ffffff; --line: #e6e4df;
    --ink: #0b0b0b; --ink-2: #52514e; --ink-3: #8a8984;
    --email: #2a78d6; --email-bg: #e3eefb; --link: #7b4fc9; --link-bg: #efe7fb;
    --token: #c77700; --token-bg: #fdefd6; --inj: #b9b7b0;
    --good: #0ca30c; --bad: #d03b3b;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--surface); color: var(--ink); width: 1400px; min-height: 100vh;
         font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", sans-serif;
         padding: 44px 48px 36px; }}
  .muted {{ color: var(--ink-3); }}
  header {{ display: flex; justify-content: space-between; align-items: flex-end;
           border-bottom: 1px solid var(--line); padding-bottom: 20px; }}
  .eyebrow {{ font-size: 12px; letter-spacing: .08em; text-transform: uppercase;
             color: var(--ink-2); font-weight: 600; }}
  h1 {{ font-size: 30px; font-weight: 700; letter-spacing: -.01em; margin-top: 4px; }}
  .meta {{ text-align: right; color: var(--ink-2); font-size: 13px; line-height: 1.6; }}
  .meta b {{ color: var(--ink); font-weight: 600; }}
  .badge {{ display: inline-block; background: #f0efec; color: var(--ink-2);
           border-radius: 4px; padding: 1px 7px; font-size: 12px; font-weight: 600; }}

  .stats {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin: 24px 0; }}
  .stat {{ background: var(--card); border: 1px solid var(--line); border-radius: 10px;
          padding: 16px 18px; }}
  .stat .v {{ font-size: 30px; font-weight: 700; letter-spacing: -.01em;
             font-variant-numeric: tabular-nums; }}
  .stat .v small {{ font-size: 16px; color: var(--ink-2); font-weight: 600; }}
  .stat .l {{ color: var(--ink-2); font-size: 13px; margin-top: 2px; }}

  h2 {{ font-size: 13px; letter-spacing: .08em; text-transform: uppercase;
       color: var(--ink-2); font-weight: 700; margin-bottom: 12px; }}
  section {{ background: var(--card); border: 1px solid var(--line); border-radius: 10px;
            padding: 20px 22px; margin-bottom: 16px; }}
  .legend {{ display: flex; gap: 18px; font-size: 12.5px; color: var(--ink-2); margin: -4px 0 12px; }}
  .legend i {{ display: inline-block; width: 10px; height: 10px; border-radius: 2px;
              margin-right: 6px; vertical-align: -1px; }}

  .example {{ display: grid; grid-template-columns: 130px 1fr; gap: 6px 14px; padding: 12px 0;
             border-bottom: 1px solid #f0efec; }}
  .example:last-child {{ border-bottom: 0; }}
  .lbl {{ font-size: 13px; font-weight: 600; padding-top: 1px; line-height: 1.5; }}
  .lbl .muted {{ font-weight: 400; font-size: 12px; }}
  .mono {{ font-family: ui-monospace, Menlo, monospace; font-size: 13.5px; }}
  .raw {{ white-space: pre-wrap; word-break: break-all; }}
  .f-email {{ background: var(--email-bg); border-bottom: 2px solid var(--email); border-radius: 2px; }}
  .f-link {{ background: var(--link-bg); border-bottom: 2px solid var(--link); border-radius: 2px; }}
  .f-token {{ background: var(--token-bg); border-bottom: 2px solid var(--token); border-radius: 2px; }}
  .cells {{ display: grid; grid-template-columns: 1.3fr 1.5fr 1fr 1fr; gap: 10px; }}
  .cell .k {{ font-size: 11px; color: var(--ink-3); }}
  .cell .v {{ font-family: ui-monospace, Menlo, monospace; font-size: 12.5px; display: inline-block;
             word-break: break-all; }}

  .three {{ display: grid; grid-template-columns: 1fr 1fr 1.2fr; gap: 16px; margin-bottom: 16px; }}
  .three section {{ margin-bottom: 0; }}
  .bar-row {{ display: grid; grid-template-columns: 110px 1fr 56px; gap: 10px; align-items: center;
             font-size: 13px; padding: 4px 0; }}
  .bar {{ height: 9px; background: #f0efec; border-radius: 3px; overflow: hidden; }}
  .fill {{ height: 100%; background: var(--good); }}
  .fill.inj {{ background: var(--inj); }}
  .n {{ text-align: right; font-variant-numeric: tabular-nums; font-weight: 600; }}
  .counts {{ text-align: right; color: var(--ink-3); font-size: 12px; font-variant-numeric: tabular-nums; }}
  .size-row {{ display: grid; grid-template-columns: 24px 1fr 56px; gap: 10px; align-items: center;
              font-size: 13px; padding: 2px 0; }}
  .pair {{ display: grid; gap: 3px; }}
  .note {{ font-size: 12px; color: var(--ink-3); margin-top: 10px; }}

  .check {{ display: grid; grid-template-columns: 22px 1fr; font-size: 13.5px; padding: 5px 0;
           border-bottom: 1px solid #f0efec; }}
  .check:last-child {{ border-bottom: 0; }}
  .mark {{ font-weight: 700; }}
  .mark.ok {{ color: var(--good); }}
  .mark.bad {{ color: var(--bad); }}

  footer {{ display: flex; justify-content: space-between; color: var(--ink-3);
           font-size: 12px; margin-top: 18px; }}
</style></head>
<body>
  <header>
    <div>
      <div class="eyebrow">Delimiter-agnostic field extraction &middot; Dask + pandas</div>
      <h1>make demo on synthetic dumps</h1>
    </div>
    <div class="meta">
      <span class="badge">Synthetic data only</span> &nbsp;seed <b>{seed}</b><br>
      <b>{files}</b> files, <b>{lines}</b> lines, mixed delimiters and encodings
    </div>
  </header>

  <div class="stats">
    <div class="stat"><div class="v">{rows}<small> / {lines}</small></div>
      <div class="l">lines with a field, extracted to CSV rows</div></div>
    <div class="stat"><div class="v">{emails}</div>
      <div class="l">distinct email addresses</div></div>
    <div class="stat"><div class="v">{clusters_found}<small> / {clusters_injected}</small></div>
      <div class="l">injected password-reuse clusters found</div></div>
    <div class="stat"><div class="v">{passed}<small> / {checks_total}</small></div>
      <div class="l">checks against the generator's manifest</div></div>
  </div>

  <section>
    <h2>Raw line in, redacted row out</h2>
    <div class="legend">
      <span><i style="background:var(--email)"></i>email</span>
      <span><i style="background:var(--link)"></i>link</span>
      <span><i style="background:var(--token)"></i>custom_field_1/2 token (salted HMAC in the output)</span>
    </div>
    {examples}
  </section>

  <div class="three">
    <section>
      <h2>Rows with each field</h2>
      {field_bars}
      <div class="note">custom_field_1 and _2 share one regex, so they always match together.</div>
    </section>
    <section>
      <h2>Delimiter between fields</h2>
      {style_bars}
      <div class="note">Lines with 2+ fields. No line is ever split on a delimiter.</div>
    </section>
    <section>
      <h2>Reuse cluster sizes</h2>
      <div class="legend">
        <span><i style="background:var(--inj)"></i>injected</span>
        <span><i style="background:var(--good)"></i>found in report.md</span>
      </div>
      {size_rows}
      <div class="note">Accounts per cluster (custom_field_1); custom_field_2 is identical.</div>
    </section>
  </div>

  <section>
    <h2>Checks</h2>
    {checks}
  </section>

  <footer>
    <span>Built by tools/results_sheet.py from one make demo run: demo_data/manifest.json,
      demo_output/results.csv and report.md.</span>
    <span>Synthetic data only; see docs/provenance-and-data-boundary.md.</span>
  </footer>
</body></html>
"""


# Browser lookup and the screenshot crop are adapted from medtext-redact's
# tools/results_sheet.py (itself adapted from medicare-rebuild's audit_sheet.py).
BROWSERS = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
]


def find_browser() -> str | None:
    """A Chromium-based browser that can screenshot headlessly: a known install, one
    on PATH, or the Chromium vhs (via go-rod) downloads for recording demo.tape."""
    for candidate in BROWSERS:
        found = shutil.which(candidate) or (candidate if Path(candidate).is_file() else None)
        if found:
            return found
    for root in sorted(Path.home().glob(".cache/rod/browser/chromium-*"), reverse=True):
        for exe in (root / "Chromium.app/Contents/MacOS/Chromium", root / "chrome"):
            if exe.is_file():
                return str(exe)
    return None


def render_png(page: Path, png: Path, chrome: str, margin: int = 32) -> None:
    """Screenshot `page` in a deliberately tall headless window, crop to the last row
    that differs from the background plus `margin` CSS px, and reduce the result to a
    256-color palette: the sheet is flat colors and text, and this keeps it small."""
    with tempfile.TemporaryDirectory() as tmp:
        shot = Path(tmp) / "tall.png"
        subprocess.run(
            [
                chrome,
                "--headless=new",
                "--hide-scrollbars",
                f"--force-device-scale-factor={SCALE}",
                f"--window-size={WIDTH},2400",
                f"--screenshot={shot}",
                page.resolve().as_uri(),
            ],
            check=True,
            capture_output=True,
        )
        gray = subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-i", str(shot), "-f", "rawvideo", "-pix_fmt", "gray", "-"],
            check=True,
            capture_output=True,
        ).stdout
        w = WIDTH * SCALE
        background = gray[0]
        last = max(
            y for y in range(len(gray) // w) if any(abs(b - background) > 6 for b in gray[y * w : (y + 1) * w : 2])
        )
        crop = f"crop=iw:{last + 1 + margin * SCALE}:0:0"
        png.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-y", "-i", str(shot), "-vf",
             f"{crop},split[a][b];[a]palettegen=max_colors=256[p];[b][p]paletteuse=dither=none", str(png)],
            check=True,
        )  # fmt: skip


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--demo-data", type=Path, default=Path("demo_data"), help="make demo's generated input")
    ap.add_argument("--demo-output", type=Path, default=Path("demo_output"), help="make demo's CSV and report")
    ap.add_argument("--out", type=Path, default=Path("demo_output/results-sheet.html"), help="HTML output path")
    ap.add_argument("--png", type=Path, help="Also render a PNG here")
    ap.add_argument("--chrome", help="Chrome/Chromium binary (default: look for one)")
    a = ap.parse_args()

    needed = [a.demo_data / "manifest.json", a.demo_output / "results.csv", a.demo_output / "report.md"]
    missing = [str(p) for p in needed if not p.is_file()]
    if missing:
        raise SystemExit(f"missing {', '.join(missing)}: run `make demo` first")

    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(build(load(a.demo_data, a.demo_output)), encoding="utf-8")
    print(f"Wrote {a.out}")
    if a.png:
        chrome = a.chrome or find_browser()
        if not chrome or not (shutil.which(chrome) or Path(chrome).is_file()):
            raise SystemExit(
                f"no browser found{f' at {chrome}' if chrome else ''}: install Chrome "
                "or Chromium, or pass --chrome <path> to one"
            )
        if not shutil.which("ffmpeg"):
            raise SystemExit("--png needs ffmpeg on PATH")
        render_png(a.out, a.png, chrome)
        print(f"Wrote {a.png} (rendered with {chrome})")


if __name__ == "__main__":
    main()
