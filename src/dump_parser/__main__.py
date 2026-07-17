"""Enable ``python -m dump_parser``.

The ``__main__`` guard here matters: the ``processes`` scheduler spawns worker
processes that re-import this module, so the entry point must be import-safe.
"""

from __future__ import annotations

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
