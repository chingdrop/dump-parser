"""Stage 1 — search a file or directory tree for lines matching a pattern.

The pipeline is built on Dask so it runs out-of-core and in parallel.

Two read strategies, both producing *correct 1-based line numbers*:

* ``blocksize=None`` (default): one streaming task per file. Memory is O(1) per
  file (lines are read one at a time from a binary handle), and files run in
  parallel across Dask workers. Best for "many files".

* ``blocksize=<bytes>``: each file is split by :func:`dask.bytes.read_bytes`
  into newline-aligned blocks (verified: ``read_text`` itself calls
  ``read_bytes(delimiter=b"\\n")`` under the hood, so blocks never truncate a
  line). Blocks are wrapped into a ``dask.bag`` via ``db.from_delayed`` and
  processed in parallel *within* a single large file. Global line numbers are
  recovered with a cheap per-file prefix-sum of each block's line count — this
  is why we drive ``read_bytes`` directly rather than ``read_text`` (the latter
  does not expose a block's file/offset).

Encoding: files are read as bytes and decoded per line as UTF-8, falling back to
a caller-chosen encoding (default ``latin-1``, which never raises) on any
invalid byte. Files that cannot be opened at all are skipped and recorded in the
summary's ``failed_files``.
"""

from __future__ import annotations

import os
import time
from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Pattern, Sequence, Tuple

import dask
import dask.bag as db
from dask.bytes import read_bytes

from .models import ScanSummary, Stage1Match
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


def _search_line(
    line: str, patterns: Sequence[Tuple[str, Pattern[str]]]
) -> Optional[Tuple[str, str]]:
    """Return ``(pattern_name, matched_text)`` for the first pattern that hits."""

    for name, pattern in patterns:
        m = pattern.search(line)
        if m:
            return name, m.group(0)
    return None


def _decode(raw: bytes, fallback: str) -> Tuple[str, bool]:
    """Decode a raw line: UTF-8 first, then ``fallback``. Returns (text, used_fallback)."""

    try:
        return raw.decode("utf-8"), False
    except UnicodeDecodeError:
        return raw.decode(fallback, errors="replace"), True


class _FileResult:
    """Per-file scan result carried back from a worker for aggregation."""

    __slots__ = ("matches", "lines", "failed", "reason", "used_fallback")

    def __init__(self) -> None:
        self.matches: List[Stage1Match] = []
        self.lines: int = 0
        self.failed: bool = False
        self.reason: str = ""
        self.used_fallback: bool = False


def _scan_file_streaming(
    path: str,
    patterns: Sequence[Tuple[str, Pattern[str]]],
    fallback: str,
) -> _FileResult:
    """Scan one file line-by-line (O(1) memory). Used when ``blocksize`` is None."""

    result = _FileResult()
    try:
        handle = open(path, "rb")
    except OSError as exc:
        result.failed = True
        result.reason = str(exc)
        return result

    with handle:
        for lineno, raw in enumerate(handle, start=1):
            result.lines += 1
            text, used_fallback = _decode(raw.rstrip(b"\r\n"), fallback)
            result.used_fallback = result.used_fallback or used_fallback
            hit = _search_line(text, patterns)
            if hit is not None:
                name, matched = hit
                result.matches.append(
                    Stage1Match(path, lineno, matched, name, text)
                )
    return result


def _scan_block(
    block: bytes,
    patterns: Sequence[Tuple[str, Pattern[str]]],
    fallback: str,
) -> Tuple[int, bool, List[Tuple[int, str, str, str]]]:
    """Scan one newline-aligned byte block.

    Returns ``(line_count, used_fallback, hits)`` where each hit is
    ``(local_line_number, matched_text, pattern_name, source_line)`` and
    ``local_line_number`` is 1-based *within this block*. The driver adds the
    block's line offset afterwards.
    """

    # read_bytes guarantees the block ends on a delimiter (or EOF), so splitting
    # on b"\n" yields only complete lines. A trailing empty element appears when
    # the block ends in a newline; it is dropped so it is not counted as a line.
    raw_lines = block.split(b"\n")
    if raw_lines and raw_lines[-1] == b"":
        raw_lines.pop()

    used_fallback = False
    hits: List[Tuple[int, str, str, str]] = []
    for local_no, raw in enumerate(raw_lines, start=1):
        text, uf = _decode(raw.rstrip(b"\r"), fallback)
        used_fallback = used_fallback or uf
        hit = _search_line(text, patterns)
        if hit is not None:
            name, matched = hit
            hits.append((local_no, matched, name, text))
    return len(raw_lines), used_fallback, hits


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
) -> Tuple[List[Stage1Match], ScanSummary]:
    """Run Stage 1 over ``path``.

    Args:
        path: A ``.txt`` file or a directory searched recursively.
        patterns: Sequence of ``(name, compiled_regex)`` search patterns. When
            omitted, a single "any-field" pattern (OR of all four field regexes)
            is used, so any line containing an extractable field is captured.
        blocksize: If set, split large files into newline-aligned blocks of this
            many bytes for intra-file parallelism. If None, stream one file per
            task.
        fallback_encoding: Encoding used when a line is not valid UTF-8.
        scheduler: Dask scheduler — ``"threads"`` (default, safe everywhere),
            ``"processes"`` (true CPU parallelism for regex; the CLI runs under a
            ``__main__`` guard so process spawning works), or ``"synchronous"``.

    Returns:
        ``(matches, summary)`` where ``matches`` is ordered by (file, line).
    """

    started = time.perf_counter()
    compiled = _compile_patterns(patterns)
    files = discover_files(path)
    summary = ScanSummary()

    if blocksize is None:
        results = _run_streaming(files, compiled, fallback_encoding, scheduler)
        matches = _collect_streaming(results, files, summary)
    else:
        matches = _run_blockwise(
            files, compiled, blocksize, fallback_encoding, scheduler, summary
        )

    matches.sort(key=lambda m: (m.file, m.line_number))
    summary.stage1_matches = len(matches)
    summary.elapsed_seconds = time.perf_counter() - started
    return matches, summary


def _run_streaming(
    files: Sequence[str],
    compiled: Sequence[Tuple[str, Pattern[str]]],
    fallback: str,
    scheduler: str,
) -> List[_FileResult]:
    tasks = [
        dask.delayed(_scan_file_streaming)(f, compiled, fallback) for f in files
    ]
    if not tasks:
        return []
    return list(dask.compute(*tasks, scheduler=scheduler))


def _collect_streaming(
    results: Sequence[_FileResult],
    files: Sequence[str],
    summary: ScanSummary,
) -> List[Stage1Match]:
    matches: List[Stage1Match] = []
    for path, res in zip(files, results):
        if res.failed:
            summary.failed_files.append((path, res.reason))
            continue
        summary.files_scanned += 1
        summary.lines_scanned += res.lines
        if res.used_fallback:
            summary.fallback_files.append(path)
        matches.extend(res.matches)
    return matches


def _run_blockwise(
    files: Sequence[str],
    compiled: Sequence[Tuple[str, Pattern[str]]],
    blocksize: int,
    fallback: str,
    scheduler: str,
    summary: ScanSummary,
) -> List[Stage1Match]:
    # Build one dask.bag whose items are (file, block_index, line_count,
    # used_fallback, hits). Each file contributes an ordered list of blocks.
    delayeds = []
    index: List[Tuple[str, int]] = []  # parallel metadata: (file, block_index)
    readable_files: List[str] = []

    for path in files:
        # Pre-flight the file so an unreadable one is skipped with a warning
        # rather than blowing up the lazy graph at compute time.
        try:
            with open(path, "rb"):
                pass
        except OSError as exc:
            summary.failed_files.append((path, str(exc)))
            continue
        readable_files.append(path)
        _sample, blocks = read_bytes(path, delimiter=b"\n", blocksize=blocksize)
        for block_index, block in enumerate(blocks[0]):
            delayeds.append(
                dask.delayed(_scan_block)(block, compiled, fallback)
            )
            index.append((path, block_index))

    if not delayeds:
        summary.files_scanned += len(readable_files)
        return []

    bag = db.from_delayed([dask.delayed(lambda x: [x])(d) for d in delayeds])
    computed = bag.compute(scheduler=scheduler)  # list aligned with `index`

    # Group blocks per file, order by block_index, prefix-sum line counts to get
    # each block's starting line number, then lift local -> global line numbers.
    per_file: Dict[str, Dict[int, Tuple[int, bool, list]]] = defaultdict(dict)
    for (path, block_index), (line_count, used_fallback, hits) in zip(index, computed):
        per_file[path][block_index] = (line_count, used_fallback, hits)

    matches: List[Stage1Match] = []
    for path in readable_files:
        summary.files_scanned += 1
        blocks_map = per_file.get(path, {})
        offset = 0
        file_used_fallback = False
        for block_index in sorted(blocks_map):
            line_count, used_fallback, hits = blocks_map[block_index]
            file_used_fallback = file_used_fallback or used_fallback
            for local_no, matched, name, text in hits:
                matches.append(
                    Stage1Match(path, offset + local_no, matched, name, text)
                )
            offset += line_count
        summary.lines_scanned += offset
        if file_used_fallback:
            summary.fallback_files.append(path)
    return matches
