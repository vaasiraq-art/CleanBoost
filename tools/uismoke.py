"""Cycle every screen once, then exit. Catches layout/runtime errors."""
from __future__ import annotations

import os
import sys
import traceback

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, root)

from core.utils import enable_dpi_awareness  # noqa: E402

enable_dpi_awareness()

from ui.app import CleanBoostApp  # noqa: E402

failures: list[str] = []


def main() -> int:
    app = CleanBoostApp()

    def step():
        for key in list(app.pages):
            try:
                app.show(key)
                app.update_idletasks()
                app.update()
                print(f"  ok   {key}")
            except Exception:
                traceback.print_exc()
                failures.append(key)
        app.after(300, app.destroy)

    app.after(1200, step)
    app.mainloop()
    if failures:
        print("UI SMOKE FAILED:", failures)
        return 1
    print("UI smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
