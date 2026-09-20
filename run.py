#!/usr/bin/env python3
"""Arranque sin instalar el paquete: `./run.py [proveedor]`."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from monitor_consumos.__main__ import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
