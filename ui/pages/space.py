"""Space analyzer: drives, big files and folder sizes."""
from __future__ import annotations

import os
import threading
import tkinter as tk

from core import scanner, system
from core.utils import human_age, human_size, recycle_paths, reveal_path
from ui import dialogs
from ui import theme as t
from ui.widgets import Card, Meter, ScrollFrame, Segmented, Table, button, label, link, muted
from .base import Page


class SpacePage(Page):
    title = "Space Analyzer"
    subtitle = "Find what is actually using your disk."

    def build(self) -> None:
        self._cancel = threading.Event()
        self._min_mb = 250

        self.scroll = ScrollFrame(self.body, bg=t.BG)
        self.scroll.pack(fill="both", expand=True)
        wrap = self.scroll.body

        self._build_drives(wrap)
        self._build_large(wrap)
        self._build_folders(wrap)

    # ------------------------------------------------------------------ #
    def _build_drives(self, parent) -> None:
        card = Card(parent)
        card.pack(fill="x")
        head = tk.Frame(card.body, bg=t.SURFACE)
        head.pack(fill="x")
        tk.Label(head, text="Drives", font=t.H2, fg=t.TEXT, bg=t.SURFACE, anchor="w").pack(side="left")
        link(head, "Storage settings", lambda: system.open_windows_tool("storage")).pack(side="right")
        self.drives_box = tk.Frame(card.body, bg=t.SURFACE)
        self.drives_box.pack(fill="x", pady=(14, 0))

    def _build_large(self, parent) -> None:
        card = Card(parent)
        card.pack(fill="x", pady=(t.GAP, 0))

        head = tk.Frame(card.body, bg=t.SURFACE)
        head.pack(fill="x")
        titles = tk.Frame(head, bg=t.SURFACE)
        titles.pack(side="left", anchor="w")
        tk.Label(titles, text="Large files", font=t.H2, fg=t.TEXT, bg=t.SURFACE, anchor="w").pack(anchor="w")
        muted(titles, "Everything over the size you pick, biggest first.").pack(anchor="w")

        controls = tk.Frame(head, bg=t.SURFACE)
        controls.pack(side="right", anchor="e")
        self.size_pick = Segmented(
            controls,
            [("100 MB", 100), ("250 MB", 250), ("500 MB", 500), ("1 GB", 1024)],
            value=self._min_mb,
            command=self._set_threshold,
        )
        self.size_pick.pack(side="left", padx=(0, 10))
        self.large_btn = button(controls, "Scan", self.scan_large, "primary", padx=16, pady=7)
        self.large_btn.pack(side="left")

        self.large_status = muted(card.body, "Not scanned yet.")
        self.large_status.pack(anchor="w", pady=(12, 8))

        self.large_table = Table(
            card.body,
            [
                ("size", "Size", 90, "e"),
                ("path", "File", 560, "w"),
                ("when", "Modified", 110, "e"),
            ],
            height=7,
        )
        self.large_table.pack(fill="both", expand=True)
        self.large_table.bind_double(lambda _e: self.reveal_large())

        actions = tk.Frame(card.body, bg=t.SURFACE)
        actions.pack(fill="x", pady=(12, 0))
        button(actions, "Show in folder", self.reveal_large, "ghost", padx=14, pady=6).pack(side="left")
        button(actions, "Recycle selected", self.delete_large, "danger", padx=14, pady=6).pack(
            side="left", padx=(10, 0)
        )
        muted(actions, "Deleted files go to the Recycle Bin.").pack(side="left", padx=(12, 0))

    def _build_folders(self, parent) -> None:
        card = Card(parent)
        card.pack(fill="x", pady=(t.GAP, 0))
        head = tk.Frame(card.body, bg=t.SURFACE)
        head.pack(fill="x")
        titles = tk.Frame(head, bg=t.SURFACE)
        titles.pack(side="left", anchor="w")
        tk.Label(titles, text="Folder sizes", font=t.H2, fg=t.TEXT, bg=t.SURFACE, anchor="w").pack(anchor="w")
        muted(titles, "Your user profile, measured folder by folder.").pack(anchor="w")
        self.folder_btn = button(head, "Analyze folders", self.scan_folders, "ghost", padx=16, pady=7)
        self.folder_btn.pack(side="right")

        self.folder_status = muted(card.body, "Not analyzed yet. This can take a moment.")
        self.folder_status.pack(anchor="w", pady=(12, 8))

        self.folder_table = Table(
            card.body,
            [
                ("size", "Size", 90, "e"),
                ("path", "Folder", 560, "w"),
                ("when", "Modified", 110, "e"),
            ],
            height=7,
        )
        self.folder_table.pack(fill="both", expand=True)
        self.folder_table.bind_double(lambda _e: self.reveal_folder())

        actions = tk.Frame(card.body, bg=t.SURFACE)
        actions.pack(fill="x", pady=(12, 0))
        button(actions, "Open folder", self.reveal_folder, "ghost", padx=14, pady=6).pack(side="left")

    # ------------------------------------------------------------------ #
    def on_show(self) -> None:
        self._render_drives()

    def refresh(self) -> None:
        self._render_drives()

    def _render_drives(self) -> None:
        for child in self.drives_box.winfo_children():
            child.destroy()
        for drive in system.drives(False):
            block = tk.Frame(self.drives_box, bg=t.SURFACE)
            block.pack(fill="x", pady=(0, 14))
            top = tk.Frame(block, bg=t.SURFACE)
            top.pack(fill="x")
            tk.Label(top, text=f"{drive.letter}:", font=t.H3, fg=t.TEXT, bg=t.SURFACE).pack(side="left")
            if drive.label:
                tk.Label(top, text=f"  {drive.label}", font=t.SMALL, fg=t.TEXT_DIM,
                         bg=t.SURFACE).pack(side="left")
            tk.Label(
                top,
                text=f"{human_size(drive.free)} free · {human_size(drive.used)} used · {drive.percent:.0f}%",
                font=t.SMALL,
                fg=t.TEXT_DIM,
                bg=t.SURFACE,
            ).pack(side="right")
            meter = Meter(block, height=7)
            meter.pack(fill="x", pady=(6, 0))
            meter.set(drive.percent / 100.0)

    # ------------------------------------------------------------------ #
    def _set_threshold(self, value: int) -> None:
        self._min_mb = int(value)
        self.large_status.configure(text=f"Threshold set to {value} MB. Scan to refresh.")

    def scan_large(self) -> None:
        if str(self.large_btn["state"]) == "disabled":
            return
        self.large_btn.configure(state="disabled", text="Scanning…")
        self.large_table.clear()
        self.large_status.configure(text="Scanning your profile for large files…")
        profile = os.environ.get("USERPROFILE", os.path.expanduser("~"))
        min_bytes = self._min_mb * 1024 * 1024
        cancel = self._cancel

        def work():
            return scanner.find_large_files([profile], min_bytes, cancel)

        def done(rows, error):
            self.large_btn.configure(state="normal", text="Scan")
            if error or rows is None:
                self.large_status.configure(text="Scan failed.")
                return
            self.large_table.clear()
            for entry in rows:
                self.large_table.add((human_size(entry.size), entry.path, human_age(entry.mtime)))
            total = sum(e.size for e in rows)
            self.large_status.configure(
                text=f"{len(rows)} files over {self._min_mb} MB · {human_size(total)} total"
                if rows
                else "No files that large. Nice."
            )

        self.app.run_bg(work, done)

    def scan_folders(self) -> None:
        if str(self.folder_btn["state"]) == "disabled":
            return
        self.folder_btn.configure(state="disabled", text="Analyzing…")
        self.folder_table.clear()
        self.folder_status.configure(text="Measuring folders…")
        profile = os.environ.get("USERPROFILE", os.path.expanduser("~"))
        cancel = self._cancel

        def work():
            return scanner.folder_breakdown([profile], cancel)

        def done(rows, error):
            self.folder_btn.configure(state="normal", text="Analyze folders")
            if error or rows is None:
                self.folder_status.configure(text="Analysis failed.")
                return
            self.folder_table.clear()
            for entry in rows:
                self.folder_table.add((human_size(entry.size), entry.path, human_age(entry.mtime)))
            total = sum(e.size for e in rows)
            self.folder_status.configure(
                text=f"{len(rows)} folders · {human_size(total)} total" if rows else "Nothing to show."
            )

        self.app.run_bg(work, done)

    # ------------------------------------------------------------------ #
    def _selected_path(self, table: Table) -> str | None:
        row = table.selected_first()
        return row[1] if row else None

    def reveal_large(self) -> None:
        path = self._selected_path(self.large_table)
        if path:
            reveal_path(path)

    def reveal_folder(self) -> None:
        path = self._selected_path(self.folder_table)
        if path:
            reveal_path(path)

    def delete_large(self) -> None:
        selection = self.large_table.selected_iids()
        if not selection:
            return
        paths = [self.large_table.tree.item(iid, "values")[1] for iid in selection]
        total = 0
        for path in paths:
            try:
                total += os.path.getsize(path)
            except OSError:
                pass
        if not dialogs.confirm(
            self.app,
            "Move to Recycle Bin?",
            f"{len(paths)} file(s), {human_size(total)}, will leave your profile.",
            ok_text="Move to Recycle Bin",
            detail="You can restore them from the Recycle Bin if you change your mind.",
        ):
            return
        ok, failed = recycle_paths(paths)
        for iid in selection:
            self.large_table.tree.delete(iid)
        self.app.toast(f"{ok} file(s) moved to the Recycle Bin" + (f" · {failed} failed" if failed else ""),
                       ok > 0)
