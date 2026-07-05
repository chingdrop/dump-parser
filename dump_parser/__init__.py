"""dump_parser — PowerGREP-style search + delimiter-agnostic field extraction
over large unstructured .txt dumps, powered by Dask.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["scanner", "extractor", "output", "patterns", "models", "cli"]
