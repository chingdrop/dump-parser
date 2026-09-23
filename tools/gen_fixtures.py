#!/usr/bin/env python3
"""Deterministic synthetic dump-file generator, for demoing dump-parser
end-to-end without ever touching a real data dump.

Lives outside the installed package (``tools/``, not ``src/``) — this is a
dev-only fixture generator, never shipped or imported by the CLI at runtime.
It reuses the *shapes* defined in ``dump_parser.patterns`` (never invents its
own field regex), so every generated value is asserted to fullmatch the real
pattern before it's written, and deliberately injects password-reuse clusters
so ``dump_parser.report`` has something real, but entirely synthetic, to find.

Determinism: every random decision goes through one seeded ``random.Random``
and one seeded ``Faker`` instance, both derived from ``--seed`` and consumed
in a fixed order (pools first, then files/lines in a fixed sequence), so the
same seed always produces byte-identical output — see
``tests/test_gen_fixtures.py``.

The existing hand-written ``sample_data/`` fixtures (used by the unit tests)
are untouched by this script; this generates a separate, larger dataset for
demonstration purposes only, into a gitignored output directory.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
from dataclasses import dataclass, field

from faker import Faker

from dump_parser.patterns import CUSTOM_FIELD_1_RE, EMAIL_RE, URL_RE

# ---------------------------------------------------------------------------
# Fixed, fictitious domains. RFC 2606 reserved (.example/.test) plus one
# deliberate "your own domain" example matching the README's existing
# `-p '@blueshiftdefense.com'` usage — never a real-looking company domain.
# ---------------------------------------------------------------------------
DOMAINS: tuple[str, ...] = ("acme.example", "corp.example", "mail.example", "shop.test", "news.test")
BLUESHIFT_DOMAIN = "blueshiftdefense.com"
BLUESHIFT_RATE = 0.10

# Accented-but-Latin-1-safe noise phrases: never match any field pattern (no
# '@', no 'http'/'www.', no digits), used to (a) force genuine no-match lines
# and (b) prefix every line of the one deliberately non-UTF-8 file.
NOISE_PHRASES: tuple[str, ...] = (
    "café résumé notes",
    "no fields on this line, just some prose",
    "naïve façade at the café",
    "Zürich büro update",
    "Öland straße memo",
    "à la carte notes",
    "élan vérité, nothing extractable here",
)

# custom_field_1 and custom_field_2 are extracted from source_line by two
# *structurally identical* regexes (patterns.py: "custom_field_1 and
# custom_field_2 share the same structure"), each independently re-scanning
# the whole line. So a line with one token-shaped substring on it always
# yields the same value in both output columns -- there's no way to target
# "custom_field_1" vs "custom_field_2" separately from the source text. This
# generator therefore models a single "custom_field" slot per line and
# mirrors its result into both manifest/report keys; see `generate()`.
DELIMS: tuple[str, ...] = (",", " ", "|", ":")
FIELD_ORDER: tuple[str, ...] = ("email", "link", "custom_field")
INCLUDE_PROB: dict[str, float] = {"email": 0.85, "link": 0.55, "custom_field": 0.65}
MULTI_MATCH_PROB = 0.12
TARGET_CLUSTER_SIZE = 4  # avg distinct emails per injected shared token
TOKEN_MANIFEST_COLUMNS: tuple[str, ...] = ("custom_field_1", "custom_field_2")

_LOCAL_SAFE = re.compile(r"[^A-Za-z0-9._%+-]")
_PATH_SAFE = re.compile(r"[^A-Za-z0-9-]")
_LETTERS_ONLY = re.compile(r"[^A-Za-z]")


def _sanitize(pattern: re.Pattern[str], text: str, fallback: str) -> str:
    cleaned = pattern.sub("", text)
    return cleaned or fallback


def make_email(rng: random.Random, fake: Faker) -> str:
    first = _sanitize(_LOCAL_SAFE, fake.first_name().lower(), "user")
    last = _sanitize(_LOCAL_SAFE, fake.last_name().lower(), "id")
    sep = rng.choice(("", ".", "+"))
    local = f"{first}{sep}{last}{rng.randint(0, 999)}"
    domain = BLUESHIFT_DOMAIN if rng.random() < BLUESHIFT_RATE else rng.choice(DOMAINS)
    email = f"{local}@{domain}"
    assert EMAIL_RE.fullmatch(email), f"generated email failed its own pattern: {email!r}"
    return email


def make_link(rng: random.Random, fake: Faker, domain: str) -> str:
    scheme = rng.choice(("https://", "http://", "www."))
    segments = [_sanitize(_PATH_SAFE, fake.word(), "path") for _ in range(rng.randint(0, 2))]
    path = "/" + "/".join(segments) if segments else ""
    query = f"?id={rng.randint(1, 999)}" if rng.random() < 0.3 else ""
    frag = f"#{_sanitize(_PATH_SAFE, fake.word(), 'frag')}" if rng.random() < 0.2 else ""
    link = f"{scheme}{domain}{path}{query}{frag}"
    assert URL_RE.fullmatch(link), f"generated link failed its own pattern: {link!r}"
    return link


def make_fresh_token(rng: random.Random, fake: Faker) -> str:
    """A letters+digits(+optional '@') token, matching ``CUSTOM_FIELD_1_RE``.

    The digit suffix is drawn from a wide range specifically so that two
    independently-generated ("fresh") tokens practically never collide by
    accident: every reuse cluster that shows up in the output must come from
    the deliberate shared ``pools`` in :func:`generate`, which is what the
    manifest records as ground truth for the tests to check against.
    """

    word = _sanitize(_LETTERS_ONLY, fake.word(), "Token").capitalize()
    token = f"{word}{rng.randint(0, 10**9)}"
    if rng.random() < 0.4:
        token += "@"
    assert CUSTOM_FIELD_1_RE.fullmatch(token), f"generated token failed its own pattern: {token!r}"
    return token


def _join_with_delimiters(rng: random.Random, values: list[str]) -> str:
    """Join field values the same delimiter-agnostic ways patterns.py documents:
    comma, space, pipe, colon, or a per-gap mix — never a fixed schema."""

    if not values:
        return ""
    if len(values) == 1:
        return values[0]
    style = rng.choice(("comma", "space", "pipe", "colon", "mixed"))
    if style == "mixed":
        delims = [rng.choice(DELIMS) for _ in range(len(values) - 1)]
    else:
        fixed = {"comma": ",", "space": " ", "pipe": "|", "colon": ":"}[style]
        delims = [fixed] * (len(values) - 1)
    parts = [values[0]]
    for value, delim in zip(values[1:], delims, strict=True):
        parts.append(delim)
        parts.append(value)
    return "".join(parts)


@dataclass
class LineResult:
    text: str
    email: str | None
    pool_hits: list[str] = field(default_factory=list)  # pool tokens used as "custom_field" on this line


def _generate_line(
    rng: random.Random,
    fake: Faker,
    pool: list[str],
    reuse_rate: float,
    eligible_counts: dict[str, int],
    force_empty: bool = False,
) -> LineResult:
    if force_empty:
        return LineResult(text=rng.choice(NOISE_PHRASES), email=None)

    include = {name: rng.random() < INCLUDE_PROB[name] for name in FIELD_ORDER}
    if not any(include.values()):
        return LineResult(text=rng.choice(NOISE_PHRASES), email=None)

    email = make_email(rng, fake) if include["email"] else None
    domain = email.rsplit("@", 1)[1] if email else rng.choice(DOMAINS)

    slots: list[tuple[str, str]] = []
    pool_hits: list[str] = []

    if email is not None:
        slots.append(("email", email))
    if include["link"]:
        slots.append(("link", make_link(rng, fake, domain)))
    if include["custom_field"]:
        if email is not None:
            eligible_counts["custom_field"] += 1
        use_pool = email is not None and pool and rng.random() < reuse_rate
        if use_pool:
            token = rng.choice(pool)
            pool_hits.append(token)
        else:
            token = make_fresh_token(rng, fake)
        slots.append(("custom_field", token))

    # Occasionally give one already-included non-email field a second match on
    # the same line (exercises pipe-joining / --one-row-per-match), mirroring
    # lines like sample_data's "grace@acme.io, https://.../a, https://.../b,
    # ...". Never duplicates "email": a second email on the same line would
    # make report.py's (file, line_number) join cross-associate an unrelated
    # co-occurring account with a token, muddying the deliberately-injected
    # reuse clusters the manifest tracks as ground truth.
    duplicable = [s for s in slots if s[0] != "email"]
    if duplicable and rng.random() < MULTI_MATCH_PROB:
        field_name, _ = rng.choice(duplicable)
        extra = make_link(rng, fake, domain) if field_name == "link" else make_fresh_token(rng, fake)
        slots.append((field_name, extra))

    rng.shuffle(slots)
    text = _join_with_delimiters(rng, [value for _, value in slots])
    return LineResult(text=text, email=email, pool_hits=pool_hits)


def _pool_size(total_lines: int, reuse_rate: float) -> int:
    if reuse_rate <= 0:
        return 0
    expected_slots = total_lines * INCLUDE_PROB["custom_field"]
    return max(2, round(expected_slots * reuse_rate / TARGET_CLUSTER_SIZE))


@dataclass
class GenConfig:
    seed: int = 1337
    files: int = 8
    lines_per_file: int = 500
    big_file_lines: int = 50_000
    out_dir: str = "demo_data"
    reuse_rate: float = 0.15


# Subdirectory names inside --out-dir. The N regular files (the ones the main
# `make demo` CSV/report run scans) live under REGULAR_DIR; the one big file
# for the --blocksize demo lives under BIG_DIR, on its own, specifically so
# `dump-parser <out-dir>/REGULAR_DIR` can demonstrate redaction+report without
# 50,000 extra lines making the report unreadable, and `make demo-big` can
# point --blocksize at exactly one file.
REGULAR_DIR = "regular"
BIG_DIR = "big"


def _build_file_plan(config: GenConfig) -> list[tuple[str, int, str]]:
    """Return ``[(relative_path, line_count, encoding), ...]`` in write order.

    File 1 lands in a nested subdirectory, file 2 is written non-UTF-8
    (Latin-1, with accented noise on every line), the rest are plain
    top-level UTF-8 files — mirroring the edge cases ``sample_data/`` already
    covers. The big file (if any) is appended last, in its own subdirectory.
    """

    plan: list[tuple[str, int, str]] = []
    for i in range(1, config.files + 1):
        name = f"dump_{i:03d}.txt"
        if i == 1:
            plan.append((os.path.join(REGULAR_DIR, "nested", name), config.lines_per_file, "utf-8"))
        elif i == 2:
            plan.append((os.path.join(REGULAR_DIR, f"dump_{i:03d}_latin1.txt"), config.lines_per_file, "latin-1"))
        else:
            plan.append((os.path.join(REGULAR_DIR, name), config.lines_per_file, "utf-8"))
    if config.big_file_lines > 0:
        plan.append((os.path.join(BIG_DIR, "big_dump.txt"), config.big_file_lines, "utf-8"))
    return plan


def generate(config: GenConfig) -> dict:
    """Generate every fixture file under ``config.out_dir`` and return the
    manifest dict (also written to ``<out_dir>/manifest.json`` by ``main``).

    Note on ``custom_field_1``/``custom_field_2``: since both are extracted
    from the same raw line by structurally identical patterns (see the module
    docstring), there is only *one* shared token pool/event stream here; the
    manifest reports it under both column names (always identical values) so
    it lines up 1:1 with ``report.py``'s per-column sections.
    """

    rng = random.Random(config.seed)
    fake = Faker()
    fake.seed_instance(config.seed)

    regular_lines = config.files * config.lines_per_file
    total_lines = regular_lines + config.big_file_lines
    # Pool size is based on the *regular* line count only, not the (much
    # bigger) --blocksize demo file: reuse clusters are meant to be found in
    # the `make demo` CSV/report run, which only scans the regular files.
    # The pool is drawn first, before any per-line work -- part of the
    # determinism contract (same seed -> same call sequence).
    pool = [make_fresh_token(rng, fake) for _ in range(_pool_size(regular_lines, config.reuse_rate))]

    file_plan = _build_file_plan(config)
    # Manifest ground truth (distinct emails, eligible slots, pool events) is
    # scoped to the REGULAR_DIR files only -- the big file shares the same
    # pool for realism but isn't scanned by `make demo`'s CSV/report run, so
    # counting its draws in here would make the manifest disagree with what
    # that run actually shows.
    all_emails: set[str] = set()
    eligible_slots = 0
    pool_events: list[tuple[str, str]] = []  # (email, pool_token)
    written_files: list[str] = []

    os.makedirs(config.out_dir, exist_ok=True)
    for file_index, (rel_path, line_count, encoding) in enumerate(file_plan):
        is_regular = rel_path.split(os.sep)[0] == REGULAR_DIR
        lines: list[str] = []
        for line_index in range(line_count):
            force_empty = file_index == 0 and line_index == 0
            eligible_counts = {"custom_field": 0}
            result = _generate_line(rng, fake, pool, config.reuse_rate, eligible_counts, force_empty=force_empty)
            text = result.text
            if encoding == "latin-1":
                prefix = rng.choice(NOISE_PHRASES)
                text = f"{prefix},{text}" if text else prefix
            lines.append(text)
            if is_regular:
                eligible_slots += eligible_counts["custom_field"]
                if result.email:
                    all_emails.add(result.email)
                for token in result.pool_hits:
                    assert result.email is not None
                    pool_events.append((result.email, token))

        full_path = os.path.join(config.out_dir, rel_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        content = "\n".join(lines) + "\n"
        if encoding == "latin-1":
            with open(full_path, "wb") as fh:
                fh.write(content.encode("latin-1"))
        else:
            with open(full_path, "w", encoding="utf-8") as fh:
                fh.write(content)
        written_files.append(rel_path.replace(os.sep, "/"))

    by_token: dict[str, set[str]] = {}
    for email, token in pool_events:
        by_token.setdefault(token, set()).add(email)
    cluster_list = [
        {"pool_token": token, "emails": sorted(emails)}
        for token, emails in sorted(by_token.items())
        if len(emails) >= 2
    ]

    return {
        "seed": config.seed,
        "files": sorted(written_files),
        "lines_per_file": config.lines_per_file,
        "big_file_lines": config.big_file_lines,
        "reuse_rate": config.reuse_rate,
        "distinct_emails": len(all_emails),
        "distinct_files": len(written_files),
        "total_lines": total_lines,
        # Mirrored under both keys: custom_field_1/2 always carry identical
        # values in the real output (see the docstring above).
        "eligible_slot_count": dict.fromkeys(TOKEN_MANIFEST_COLUMNS, eligible_slots),
        "pool_size": dict.fromkeys(TOKEN_MANIFEST_COLUMNS, len(pool)),
        "pool_assignment_count": dict.fromkeys(TOKEN_MANIFEST_COLUMNS, len(pool_events)),
        "reuse_clusters": {name: cluster_list for name in TOKEN_MANIFEST_COLUMNS},
    }


def _parse_args(argv: list[str] | None) -> GenConfig:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=GenConfig.seed)
    parser.add_argument("--files", type=int, default=GenConfig.files)
    parser.add_argument("--lines-per-file", type=int, default=GenConfig.lines_per_file)
    parser.add_argument("--out-dir", default=GenConfig.out_dir)
    parser.add_argument("--big-file-lines", type=int, default=GenConfig.big_file_lines)
    parser.add_argument("--reuse-rate", type=float, default=GenConfig.reuse_rate)
    args = parser.parse_args(argv)
    return GenConfig(
        seed=args.seed,
        files=args.files,
        lines_per_file=args.lines_per_file,
        big_file_lines=args.big_file_lines,
        out_dir=args.out_dir,
        reuse_rate=args.reuse_rate,
    )


def main(argv: list[str] | None = None) -> int:
    config = _parse_args(argv)
    manifest = generate(config)

    manifest_path = os.path.join(config.out_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
        fh.write("\n")

    print(
        f"Generated {manifest['distinct_files']} file(s), {manifest['total_lines']} line(s), "
        f"{manifest['distinct_emails']} distinct email(s) -> {config.out_dir}/"
    )
    for field_name, clusters in manifest["reuse_clusters"].items():
        sizes = [len(c["emails"]) for c in clusters]
        print(f"  {field_name}: {len(clusters)} reuse cluster(s) injected (sizes: {sizes})")
    return 0


if __name__ == "__main__":  # pragma: no cover - manual entry point
    raise SystemExit(main())
