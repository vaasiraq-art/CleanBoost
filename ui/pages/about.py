"""About / safety screen."""
from __future__ import annotations

import os
import tkinter as tk

from core import cleaner, system
from core.utils import APP_NAME, APP_TAGLINE, APP_VERSION, app_dir, human_size, is_admin, open_path
from ui import dialogs
from ui import theme as t
from ui.widgets import Card, ScrollFrame, button, logo, muted
from .base import Page

SAFETY = [
    "Only allow-listed locations are scanned. Your documents, photos and program files are never touched.",
    "Deletion is re-checked against a protected-path list right before each file is removed.",
    "In-use files are skipped instead of forced, so open apps and Windows keep working.",
    "Personal files (large files and duplicates) go to the Recycle Bin, not into the void.",
    "Every cleanup is logged locally so you can see exactly how much was freed and when.",
]


class AboutPage(Page):
    title = "About"
    subtitle = "What this tool does — and what it deliberately will not do."

    def build(self) -> None:
        self.scroll = ScrollFrame(self.body, bg=t.BG)
        self.scroll.pack(fill="both", expand=True)
        wrap = self.scroll.body

        hero = Card(wrap)
        hero.pack(fill="x")
        row = tk.Frame(hero.body, bg=t.SURFACE)
        row.pack(fill="x")
        logo(row, 54, bg=t.SURFACE).pack(side="left", anchor="n")
        text = tk.Frame(row, bg=t.SURFACE)
        text.pack(side="left", padx=(16, 0))
        tk.Label(text, text=f"{APP_NAME} {APP_VERSION}", font=t.H1, fg=t.TEXT, bg=t.SURFACE,
                 anchor="w").pack(anchor="w")
        tk.Label(text, text=APP_TAGLINE, font=t.BODY, fg=t.TEXT_DIM, bg=t.SURFACE,
                 anchor="w").pack(anchor="w", pady=(2, 0))
        tk.Label(
            text,
            text="A small, dependency-free Windows cleaner. It scans known junk locations, "
                 "shows you the numbers first, and only deletes what you approve.",
            font=t.SMALL,
            fg=t.TEXT_FAINT,
            bg=t.SURFACE,
            anchor="w",
            justify="left",
            wraplength=680,
        ).pack(anchor="w", pady=(8, 0))

        # ---- permission ----
        perm = Card(wrap)
        perm.pack(fill="x", pady=(t.GAP, 0))
        head = tk.Frame(perm.body, bg=t.SURFACE)
        head.pack(fill="x")
        tk.Label(head, text="Permissions", font=t.H2, fg=t.TEXT, bg=t.SURFACE, anchor="w").pack(side="left")
        badge_bg = t.GREEN_SOFT if is_admin() else t.SURFACE_ALT
        badge_fg = t.GREEN if is_admin() else t.TEXT_DIM
        tk.Label(head, text=" Administrator " if is_admin() else " Standard user ",
                 font=t.TINY, fg=badge_fg, bg=badge_bg, padx=6, pady=3).pack(side="right")
        muted(
            perm.body,
            "Administrator mode unlocks Windows temp, update caches and upgrade leftovers. "
            "Standard mode is fully functional for your own files.",
            bg=t.SURFACE,
        ).pack(anchor="w", pady=(8, 12))
        if is_admin():
            muted(perm.body, "You are already running elevated. Nothing else needed.", bg=t.SURFACE).pack(anchor="w")
        else:
            button(perm.body, "Restart as administrator", self.app.elevate, "primary").pack(anchor="w")

        # ---- safety ----
        safe = Card(wrap)
        safe.pack(fill="x", pady=(t.GAP, 0))
        tk.Label(safe.body, text="How deletion works", font=t.H2, fg=t.TEXT, bg=t.SURFACE,
                 anchor="w").pack(anchor="w", pady=(0, 10))
        for line in SAFETY:
            row = tk.Frame(safe.body, bg=t.SURFACE)
            row.pack(fill="x", pady=3)
            tk.Label(row, text="✓", font=t.SMALL, fg=t.GREEN, bg=t.SURFACE).pack(side="left", anchor="n")
            tk.Label(row, text=line, font=t.SMALL, fg=t.TEXT_DIM, bg=t.SURFACE, anchor="w",
                     justify="left", wraplength=760).pack(side="left", padx=(8, 0), anchor="w")

        # ---- data ----
        data = Card(wrap)
        data.pack(fill="x", pady=(t.GAP, 0))
        tk.Label(data.body, text="Your data", font=t.H2, fg=t.TEXT, bg=t.SURFACE,
                 anchor="w").pack(anchor="w")
        muted(data.body, f"History and startup backups live in {app_dir()}", bg=t.SURFACE).pack(
            anchor="w", pady=(6, 12)
        )
        actions = tk.Frame(data.body, bg=t.SURFACE)
        actions.pack(fill="x")
        button(actions, "Open data folder", lambda: open_path(str(app_dir())), "ghost").pack(side="left")
        button(actions, "Clear history", self.clear_history, "quiet").pack(side="left", padx=(10, 0))
        button(actions, "Windows storage settings",
               lambda: system.open_windows_tool("storage"), "quiet").pack(side="left", padx=(10, 0))

        self.history_label = muted(data.body, "", bg=t.SURFACE)
        self.history_label.pack(anchor="w", pady=(12, 0))
        self._render_history()

        foot = muted(
            wrap,
            "Made for Windows 10/11 · No telemetry · No background service · No install required",
            bg=t.BG,
        )
        foot.pack(anchor="w", pady=(16, 0))

    def on_show(self) -> None:
        self._render_history()

    def refresh(self) -> None:
        self._render_history()

    def _render_history(self) -> None:
        items = cleaner.history()
        if not items:
            self.history_label.configure(text="No cleanups recorded yet.")
            return
        total = sum(int(item.get("freed", 0)) for item in items)
        self.history_label.configure(
            text=f"{len(items)} recorded cleanups · {human_size(total)} freed in total"
        )

    def clear_history(self) -> None:
        if not dialogs.confirm(self.app, "Clear cleanup history?",
                               "The local log of past cleanups will be removed. Nothing else changes.",
                               ok_text="Clear", danger=True):
            return
        try:
            path = app_dir() / cleaner.HISTORY_FILE
            if path.exists():
                path.unlink()
        except OSError:
            pass
        self._render_history()
        self.app.toast("History cleared")
