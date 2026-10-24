"""CleanBoost - a small, honest Windows cleaner.

Run with:  python main.py
"""
from __future__ import annotations

import os
import sys
import traceback

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.utils import enable_dpi_awareness  # noqa: E402


def main() -> int:
    enable_dpi_awareness()
    try:
        from ui.app import CleanBoostApp
    except Exception:
        traceback.print_exc()
        return 1

    try:
        app = CleanBoostApp()
    except Exception:
        traceback.print_exc()
        return 1

    try:
        app.mainloop()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
