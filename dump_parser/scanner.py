"""Stage 1 — search a file or directory tree for lines matching a pattern.

The pipeline is built on Dask so it runs out-of-core and in parallel, and on
pandas so each file/block's lines are searched with vectorized ``Series.str``
operations rather than a Python-level loop over every line.

Two read strategies, both producing *correct 1-based line numbers*:

* ``blocksize=None`` (default): one streaming task per file. Each file is read
  and decoded once, then every line is searched in a single vectorized pass.
  Best for "many files".

* ``blocksize=<bytes>``: each file is split by :func:`dask.bytes.read_bytes`
  into newline-aligned blocks (verified: ``dask.bag.read_text`` itself calls
  ``read_bytes(delimiter=b"\\n")`` under the hood, so blocks never truncate a
  line). Blocks are searched independently and in parallel *within* a single
  large file; global line numbers are recovered with a vectorized
  ``groupby().cumsum()`` prefix-sum over each block's line count. We drive
  ``read_bytes`` directly rather than ``read_text`` because the latter does
  not expose a block's file/offset.

Encoding: each file/block is decoded as a whole (UTF-8 first). This is safe
because ``\\n`` (0x0A) can never appear as a continuation byte of a multi-byte
UTF-8 character, so a newline-aligned block boundary is always also a
character boundary. If the whole-block decode fails, the block falls back to
a caller-chosen encoding (default ``latin-1``, which never raises). Files that
cannot be opened at all are skipped and recorded in the summary's
``failed_files``.
"""

from __future__ import annotations

import os
import re
import time
from typing import Dict, List, Optional, Pattern, Sequence, Tuple

import dask
import numpy as np
import pandas as pd
from dask.bytes import read_bytes

from .models import STAGE1_COLUMNS, ScanSummary
from .patterns import default_search_pattern


def discover_files(path: str) -> List[str]:
    """Return a sorted list of ``.txt`` files under ``path``.

    ``path`` may be a single ``.txt`` file or a directory that is searched
    recursively.
    """

    if os.path.isfile(path):
        return [path]
    if os.path.isdir(path):
        found: List[str] = []
        for root, _dirs, files in os.walk(path):
            for name in files:
                if name.lower().endswith(".txt"):
                    found.append(os.path.join(root, name))
        return sorted(found)
    raise FileNotFoundError(f"No such file or directory: {path!r}")


def _decode_whole(data: bytes, fallback: str) -> Tuple[str, bool]:
    """Decode a full file/block: UTF-8 first, then ``fallback``.

    Returns ``(text, used_fallback)``. Safe to do in one shot because a
    newline-aligned chunk boundary is always a character boundary too (``\\n``
    cannot occur inside a multi-byte UTF-8 sequence).
    """

    try:
        return data.decode("utf-8"), False
    except UnicodeDecodeError:
        return data.decode(fallback, errors="replace"), True


def _split_lines(text: str) -> pd.Series:
    """Split decoded text into a Series of lines with any ``\\r`` stripped.

    ``str.split`` and ``Series.str.rstrip`` are both vectorized/C-level; no
    Python loop runs over individual lines here.
    """

    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return pd.Series(lines, dtype="object").str.rstrip("\r")


def _vectorized_search(
    lines: pd.Series, patterns: Sequence[Tuple[str, Pattern[str]]]
) -> Tuple[pd.Series, pd.Series]:
    """Find the first matching search pattern per line, vectorized.

    Loops only over ``patterns`` (typically one, occasionally a handful of
    ``-p`` flags) — never over lines. For each pattern, ``str.contains`` gives
    a vectorized boolean hit mask and ``str.extract`` (against the pattern
    wrapped in one outer capturing group, so it works regardless of any
    capturing groups the caller's own regex may contain) gives the matched
    text, both restricted to lines not already claimed by an earlier, higher
    priority pattern.

    Returns ``(matched_pattern, matched_text)``, two object-dtype Series
    aligned with ``lines`` (``pd.NA`` where nothing matched).
    """

    matched_pattern = pd.Series(pd.NA, index=lines.index, dtype="object")
    matched_text = pd.Series(pd.NA, index=lines.index, dtype="object")

    for name, pattern in patterns:
        unset = matched_pattern.isna()
        if not unset.any():
            break
        candidates = lines[unset]
        hit_mask = candidates.str.contains(pattern, regex=True, na=False)
        hit_idx = hit_mask[hit_mask].index
        if len(hit_idx) == 0:
            continue
        wrapped = re.compile(f"({pattern.pattern})", pattern.flags)
        matched_pattern.loc[hit_idx] = name
        matched_text.loc[hit_idx] = candidates.loc[hit_idx].str.extract(wrapped, expand=False)

    return matched_pattern, matched_text


def _hits_frame(
    lines: pd.Series,
    matched_pattern: pd.Series,
    matched_text: pd.Series,
    extra_columns: Dict[str, object],
) -> pd.DataFrame:
    """Assemble a hits DataFrame from vectorized search results via boolean
    indexing (no per-line Python loop)."""

    hit_mask = matched_pattern.notna().to_numpy()
    idx = np.flatnonzero(hit_mask)
    return pd.DataFrame(
        {
            **extra_columns,
            "line_number": idx + 1,
            "matched_text": matched_text.to_numpy()[idx],
            "pattern": matched_pattern.to_numpy()[idx],
            "source_line": lines.to_numpy()[idx],
        }
    )


def _scan_file_streaming(
    path: str,
    patterns: Sequence[Tuple[str, Pattern[str]]],
    fallback: str,
) -> dict:
    """Read, decode and search one whole file in a single vectorized pass."""

    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError as exc:
        return {"failed": True, "reason": str(exc)}

    text, used_fallback = _decode_whole(raw, fallback)
    lines = _split_lines(text)
    matched_pattern, matched_text = _vectorized_search(lines, patterns)
    df = _hits_frame(lines, matched_pattern, matched_text, {"file": path})

    return {
        "failed": False,
        "used_fallback": used_fallback,
        "line_count": len(lines),
        "df": df,
    }


def _scan_block(
    block: bytes,
    patterns: Sequence[Tuple[str, Pattern[str]]],
    fallback: str,
) -> Tuple[int, bool, pd.DataFrame]:
    """Decode and search one newline-aligned byte block.

    Returns ``(line_count, used_fallback, hits)`` where ``hits`` has columns
    ``line_number`` (1-based *within this block*), ``matched_text``,
    ``pattern``, ``source_line``. The driver adds the block's global line
    offset (and the file column) afterwards.
    """

    text, used_fallback = _decode_whole(block, fallback)
    lines = _split_lines(text)
    matched_pattern, matched_text = _vectorized_search(lines, patterns)
    hits = _hits_frame(lines, matched_pattern, matched_text, {})
    return len(lines), used_fallback, hits


def _compile_patterns(
    patterns: Optional[Sequence[Tuple[str, Pattern[str]]]],
) -> List[Tuple[str, Pattern[str]]]:
    if patterns:
        return list(patterns)
    return [("any-field", default_search_pattern())]


def scan_paths(
    path: str,
    patterns: Optional[Sequence[Tuple[str, Pattern[str]]]] = None,
    blocksize: Optional[int] = None,
    fallback_encoding: str = "latin-1",
    scheduler: str = "threads",
) -> Tuple[pd.DataFrame, ScanSummary]:
    """Run Stage 1 over ``path``.

    Args:
        path: A ``.txt`` file or a directory searched recursively.
        patterns: Sequence of ``(name, compiled_regex)`` search patterns. When
            omitted, a single "any-field" pattern (OR of all four field regexes)
            is used, so any line containing an extractable field is captured.
        blocksize: If set, split large files into newline-aligned blocks of this
            many bytes for intra-file parallelism. If None, one task per file.
        fallback_encoding: Encoding used when a file/block is not valid UTF-8.
        scheduler: Dask scheduler — ``"threads"`` (default, safe everywhere),
            ``"processes"`` (true CPU parallelism for regex; the CLI runs under a
            ``__main__`` guard so process spawning works), or ``"synchronous"``.

    Returns:
        ``(stage1_df, summary)``. ``stage1_df`` has columns
        :data:`dump_parser.models.STAGE1_COLUMNS`, sorted by (file, line).
    """

    started = time.perf_counter()
    compiled = _compile_patterns(patterns)
    files = discover_files(path)
    summary = ScanSummary()

    if blocksize is None:
        stage1_df = _run_streaming(files, compiled, fallback_encoding, scheduler, summary)
    else:
        stage1_df = _run_blockwise(files, compiled, blocksize, fallback_encoding, scheduler, summary)

    if not stage1_df.empty:
        stage1_df = stage1_df.sort_values(["file", "line_number"], kind="stable").reset_index(drop=True)
    summary.stage1_matches = len(stage1_df)
    summary.elapsed_seconds = time.perf_counter() - started
    return stage1_df, summary


def _run_streaming(
    files: Sequence[str],
    compiled: Sequence[Tuple[str, Pattern[str]]],
    fallback: str,
    scheduler: str,
    summary: ScanSummary,
) -> pd.DataFrame:
    if not files:
        return pd.DataFrame(columns=list(STAGE1_COLUMNS))

    tasks = [dask.delayed(_scan_file_streaming)(f, compiled, fallback) for f in files]
    results = list(dask.compute(*tasks, scheduler=scheduler))

    frames = []
    for path, res in zip(files, results):
        if res["failed"]:
            summary.failed_files.append((path, res["reason"]))
            continue
        summary.files_scanned += 1
        summary.lines_scanned += res["line_count"]
        if res["used_fallback"]:
            summary.fallback_files.append(path)
        frames.append(res["df"])

    if not frames:
        return pd.DataFrame(columns=list(STAGE1_COLUMNS))
    return pd.concat(frames, ignore_index=True)


def _run_blockwise(
    files: Sequence[str],
    compiled: Sequence[Tuple[str, Pattern[str]]],
    blocksize: int,
    fallback: str,
    scheduler: str,
    summary: ScanSummary,
) -> pd.DataFrame:
    delayeds = []
    meta_records: List[Tuple[str, int]] = []  # (file, block_index), aligned with delayeds
    readable_files: List[str] = []

    for path in files:
        try:
            with open(path, "rb"):
                pass
        except OSError as exc:
            summary.failed_files.append((path, str(exc)))
            continue
        readable_files.append(path)
        _sample, blocks = read_bytes(path, delimiter=b"\n", blocksize=blocksize)
        for block_index, block in enumerate(blocks[0]):
            delayeds.append(dask.delayed(_scan_block)(block, compiled, fallback))
            meta_records.append((path, block_index))

    summary.files_scanned = len(readable_files)
    if not delayeds:
        return pd.DataFrame(columns=list(STAGE1_COLUMNS))

    computed = dask.compute(*delayeds, scheduler=scheduler)

    # Carry each block's hits DataFrame along as a column value so it stays
    # attached to its (file, block_index) row across the sort below.
    block_meta = pd.DataFrame(meta_records, columns=["file", "block_index"])
    block_meta["line_count"] = [c[0] for c in computed]
    block_meta["used_fallback"] = [c[1] for c in computed]
    block_meta["hits_df"] = [c[2] for c in computed]
    block_meta = block_meta.sort_values(["file", "block_index"], kind="stable")
    # Vectorized prefix sum of line counts per file, replacing a manual
    # per-block running-offset accumulator.
    block_meta["offset"] = (
        block_meta.groupby("file")["line_count"].cumsum() - block_meta["line_count"]
    )

    summary.lines_scanned = int(block_meta["line_count"].sum())
    fallback_by_file = block_meta.groupby("file")["used_fallback"].any()
    summary.fallback_files = list(fallback_by_file[fallback_by_file].index)

    hit_frames = []
    for row in block_meta.itertuples(index=False):
        hits = row.hits_df
        if hits.empty:
            continue
        hits = hits.copy()
        hits["file"] = row.file
        hits["line_number"] = hits["line_number"] + row.offset
        hit_frames.append(hits)

    if not hit_frames:
        return pd.DataFrame(columns=list(STAGE1_COLUMNS))
    return pd.concat(hit_frames, ignore_index=True)
