"""Shared pytest setup.

``tools/`` (the synthetic fixture generator) is deliberately kept out of the
installed package, so it isn't importable as ``dump_parser.something`` -- put
its directory on ``sys.path`` here, once, for every test that needs
``import gen_fixtures``.
"""

from __future__ import annotations

import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))
