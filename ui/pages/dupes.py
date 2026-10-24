"""Duplicate finder screen."""
from __future__ import annotations

import os
import threading
import tkinter as tk

from core import dupes
from core.utils import human_age, human_size, recycle_paths, reveal_path
from ui import dialogs
from ui import theme as t
from ui.widgets import Card, CheckBox, ScrollFrame, Segmented, Table, button, label, muted
from .base import Page

FOLDERS = [
    ("Downloads", "Downloads"),
    ("Documents", "Documents"),
    ("Pictures", "Pictures"),
    ("Videos", "Videos"),
    ("Music", "Music"),
    ("Desktop", "Desktop"),
]


class DupesPage(Page):
    title = "Duplicate Files"
    subtitle = "Byte-identical copies wasting space, verified by hash."

    def build(self) -> None:
        self._groups: list[dupes.DupGroup] = []
        self._min_mb = 1
        self._cancel = threading.Event()
        self._scanning = False

        self.scroll = ScrollFrame(self.body, bg=t.BG)
        self.scroll.pack(fill="both", expand=True)
        wrap = self.scroll.body

        # ---- options ----
        card = Card(wrap)
        card.pack(fill="x")
        head = tk.Frame(card.body, bg=t.SURFACE)
        head.pack(fill="x")
        tk.Label(head, text="Where to look", font=t.H2, fg=t.TEXT, bg=t.SURFACE, anchor="w").pack(side="left")
        self.scan_btn = button(head, "Find duplicates", self.start_scan, "primary", padx=18, pady=7)
        self.scan_btn.pack(side="right")

        chips = tk.Frame(card.body, bg=t.SURFACE)
        chips.pack(fill="x", pady=(14, 0))
        self.folder_vars: dict[str, tk.BooleanVar] = {}
        profile = os.environ.get("USERPROFILE", os.path.expanduser("~"))
        for label_text, folder in FOLDERS:
            var = tk.BooleanVar(value=folder in {"Downloads", "Documents", "Pictures"})
            self.folder_vars[os.path.join(profile, folder)] = var
            chip = tk.Frame(chips, bg=t.SURFACE)
            chip.pack(side="left", padx=(0, 18))
            CheckBox(chip, var, bg=t.SURFACE).pack(side="left")
            name = tk.Label(chip, text=f"  {label_text}", font=t.SMALL, fg=t.TEXT, bg=t.SURFACE, cursor="hand2")
            name.pack(side="left")
            name.bind("<Button-1>", lambda _e, v=var: v.set(not v.get()))

        bottom = tk.Frame(card.body, bg=t.SURFACE)
        bottom.pack(fill="x", pady=(16, 0))
        tk.Label(bottom, text="Ignore files smaller than", font=t.SMALL, fg=t.TEXT_DIM,
                 bg=t.SURFACE).pack(side="left")
        Segmented(
            bottom,
            [("1 MB", 1), ("10 MB", 10), ("50 MB", 50), ("200 MB", 200)],
            value=self._min_mb,
            command=lambda v: setattr(self, "_min_mb", int(v)),
        ).pack(side="left", padx=(12, 0))

        self.status = muted(card.body, "Pick folders and run a scan.")
        self.status.pack(anchor="w", pady=(14, 0))

        # ---- results ----
        results = Card(wrap)
        results.pack(fill="x", pady=(12, 0))
        head2 = tk.Frame(results.body, bg=t.SURFACE)
        head2.pack(fill="x")
        tk.Label(head2, text="Duplicate groups", font=t.H2, fg=t.TEXT, bg=t.SURFACE, anchor="w").pack(side="left")
        self.wasted_label = tk.Label(head2, text="", font=t.SMALL, fg=t.TEXT_DIM, bg=t.SURFACE)
        self.wasted_label.pack(side="right")

        self.group_table = Table(
            results.body,
            [
                ("copies", "Copies", 70, "center"),
                ("each", "Size each", 100, "e"),
                ("wasted", "Wasted", 100, "e"),
                ("name", "File name", 520, "w"),
            ],
            height=4,
        )
        self.group_table.pack(fill="both", expand=True, pady=(12, 0))
        self.group_table.tree.bind("<<TreeviewSelect>>", self._show_copies)
        self.group_table.bind_double(lambda _e: self._reveal_first())

        self.copies_label = muted(results.body, "Select a group to see every copy.")
        self.copies_label.pack(anchor="w", pady=(14, 6))

        self.copy_table = Table(
            results.body,
            [
                ("size", "Size", 90, "e"),
                ("path", "Path", 560, "w"),
                ("when", "Modified", 110, "e"),
            ],
            height=3,
        )
        self.copy_table.pack(fill="both", expand=True)

        actions = tk.Frame(results.body, bg=t.SURFACE)
        actions.pack(fill="x", pady=(12, 0))
        button(actions, "Show in folder", self._reveal_selected, "ghost", padx=14, pady=6).pack(side="left")
        button(actions, "Recycle selected copies", self.delete_selected, "danger", padx=14, pady=6).pack(
            side="left", padx=(10, 0)
        )
        self.auto_btn = button(actions, "Keep oldest, recycle the rest", self.auto_clean, "ghost",
                               padx=14, pady=6, state="disabled")
        self.auto_btn.pack(side="right")

        muted(
            wrap,
            "Duplicates are confirmed by comparing full file contents — same name alone is never enough.",
            bg=t.BG,
        ).pack(anchor="w", pady=(12, 0))

    def refresh(self) -> None:
        self.start_scan()

    # ------------------------------------------------------------------ #
    def start_scan(self) -> None:
        if self._scanning:
            return
        roots = [path for path, var in self.folder_vars.items() if var.get()]
        if not roots:
            dialogs.notice(self.app, "No folders selected", "Pick at least one folder to scan.", kind="warn")
            return
        self._scanning = True
        self.scan_btn.configure(state="disabled", text="Scanning…")
        self.group_table.clear()
        self.copy_table.clear()
        self.auto_btn.configure(state="disabled")
        self.status.configure(text="Walking folders…")
        cancel = self._cancel

        def on_progress(count: int) -> None:
            self.app.post(self._progress, count)

        def work():
            return dupes.find_duplicates(roots, self._min_mb * 1024 * 1024, cancel, on_progress)

        def done(groups, error):
            self._scanning = False
            self.scan_btn.configure(state="normal", text="Find duplicates")
            if error or groups is None:
                self.status.configure(text="Scan failed.")
                return
            self._groups = groups
            self.group_table.clear()
            for index, group in enumerate(groups):
                self.group_table.add(
                    (str(len(group.paths)), human_size(group.size), human_size(group.wasted),
                     os.path.basename(group.paths[0])),
                    iid=str(index),
                )
            wasted = dupes.total_wasted(groups)
            if groups:
                self.wasted_label.configure(text=f"{human_size(wasted)} wasted")
            else:
                self.wasted_label.configure(text="")
            self.status.configure(
                text=f"{len(groups)} duplicate groups · {human_size(wasted)} recoverable"
                if groups
                else "No duplicates found. Your folders are tidy."
            )
            self.auto_btn.configure(state="normal" if groups else "disabled")
            if groups:
                self.group_table.tree.selection_set("0")
                self._show_copies()

        self.app.run_bg(work, done)

    def _progress(self, count: int) -> None:
        if self._scanning:
            self.status.configure(text=f"Reading files… {count} candidates")

    # ------------------------------------------------------------------ #
    def _current_group(self) -> dupes.DupGroup | None:
        selection = self.group_table.tree.selection()
        if not selection:
            return None
        try:
            return self._groups[int(selection[0])]
        except (ValueError, IndexError):
            return None

    def _show_copies(self, _event=None) -> None:
        group = self._current_group()
        self.copy_table.clear()
        if not group:
            return
        self.copies_label.configure(
            text=f"{len(group.paths)} identical copies · {human_size(group.size)} each"
        )
        extras = set(group.paths) - {min(group.paths, key=lambda p: self._mtime(p))}
        for path in group.paths:
            iid = self.copy_table.add((human_size(group.size), path, human_age(self._mtime(path))))
            if path in extras:
                self.copy_table.tree.selection_add(iid)

    @staticmethod
    def _mtime(path: str) -> float:
        try:
            return os.path.getmtime(path)
        except OSError:
            return 0.0

    def _reveal_first(self) -> None:
        group = self._current_group()
        if group and group.paths:
            reveal_path(group.paths[0])

    def _reveal_selected(self) -> None:
        selection = self.copy_table.tree.selection()
        if selection:
            value = self.copy_table.tree.item(selection[0], "values")[1]
            reveal_path(value)

    # ------------------------------------------------------------------ #
    def delete_selected(self) -> None:
        selection = self.copy_table.tree.selection()
        if not selection:
            dialogs.notice(self.app, "Nothing selected", "Select the copies you want to remove.", kind="info")
            return
        group = self._current_group()
        group_iid = self.group_table.tree.selection()[0] if self.group_table.tree.selection() else None
        if not group:
            return
        paths = [self.copy_table.tree.item(iid, "values")[1] for iid in selection]
        if len(paths) >= len(group.paths):
            dialogs.notice(
                self.app,
                "Keep one copy",
                "You selected every copy in this group. Uncheck one so the file is not lost.",
                kind="warn",
            )
            return
        size = group.size * len(paths)
        if not dialogs.confirm(
            self.app,
            "Recycle these copies?",
            f"{len(paths)} copies ({human_size(size)}) will be moved to the Recycle Bin.",
            ok_text="Recycle",
            detail="One copy is kept. You can restore files from the Recycle Bin.",
        ):
            return
        ok, failed = recycle_paths(paths)
        self.app.toast(f"{ok} copies recycled" + (f" · {failed} failed" if failed else ""), ok > 0)
        group.paths = [p for p in group.paths if p not in set(paths)]
        if len(group.paths) < 2:
            self._groups.remove(group)
            if group_iid:
                self.group_table.tree.delete(group_iid)
            self.copy_table.clear()
            self.copies_label.configure(text="Select a group to see every copy.")
        else:
            self._refresh_group_row(group)
            self._show_copies()

    def _refresh_group_row(self, group: dupes.DupGroup) -> None:
        try:
            index = self._groups.index(group)
        except ValueError:
            return
        self.group_table.tree.item(
            str(index),
            values=(str(len(group.paths)), human_size(group.size), human_size(group.wasted),
                    os.path.basename(group.paths[0])),
        )

    def auto_clean(self) -> None:
        if not self._groups:
            return
        wasted = dupes.total_wasted(self._groups)
        count = sum(len(g.paths) - 1 for g in self._groups)
        if not dialogs.confirm(
            self.app,
            "Remove duplicate copies?",
            f"{count} extra copies will be moved to the Recycle Bin, freeing {human_size(wasted)}.",
            ok_text="Recycle extras",
            danger=True,
            detail="The oldest copy of each file is kept. Everything stays recoverable in the Recycle Bin.",
        ):
            return
        paths = dupes.extras(self._groups, keep="oldest")
        ok, failed = recycle_paths(paths)
        self.app.toast(f"{human_size(wasted)} recovered" + (f" · {failed} failed" if failed else ""),
                       ok > 0)
        self._groups.clear()
        self.group_table.clear()
        self.copy_table.clear()
        self.wasted_label.configure(text="")
        self.status.configure(text="Duplicates removed. Run a new scan to check again.")
        self.auto_btn.configure(state="disabled")
