"""Overview screen: the one-glance dashboard."""
from __future__ import annotations

import threading
import time
import tkinter as tk

from core import cleaner, scanner, startup, system
from core.utils import human_size, is_admin
from ui import dialogs
from ui import theme as t
from ui.widgets import Card, Meter, ScrollFrame, button, muted
from .base import Page


class OverviewPage(Page):
    title = "Overview"
    subtitle = "Disk space, memory and cleanup in one place."

    def build(self) -> None:
        self._scan_time = 0.0
        self._junk_total = 0
        self._junk_count = 0
        self._cancel = threading.Event()
        self._busy = False

        self.scroll = ScrollFrame(self.body, bg=t.BG)
        self.scroll.pack(fill="both", expand=True)
        wrap = self.scroll.body

        self._build_hero(wrap)
        self._build_columns(wrap)
        self._build_shortcuts(wrap)
        self._build_recent(wrap)

    # ------------------------------------------------------------------ #
    def _build_hero(self, parent) -> None:
        card = Card(parent)
        card.pack(fill="x")
        body = card.body

        top = tk.Frame(body, bg=t.SURFACE)
        top.pack(fill="x")

        left = tk.Frame(top, bg=t.SURFACE)
        left.pack(side="left", fill="both", expand=True)

        tk.Label(left, text="FREE SPACE ON SYSTEM DRIVE", font=t.TINY, fg=t.TEXT_DIM,
                 bg=t.SURFACE, anchor="w").pack(anchor="w")

        value_row = tk.Frame(left, bg=t.SURFACE)
        value_row.pack(fill="x", pady=(4, 0))
        self.free_value = tk.Label(value_row, text="--", font=t.DISPLAY, fg=t.TEXT, bg=t.SURFACE)
        self.free_value.pack(side="left")
        self.total_label = tk.Label(value_row, text="", font=t.SMALL, fg=t.TEXT_FAINT, bg=t.SURFACE)
        self.total_label.pack(side="left", padx=(8, 0), pady=(10, 0))

        self.disk_meter = Meter(left, height=10)
        self.disk_meter.pack(fill="x", pady=(10, 6))
        self.disk_line = muted(left, "Reading drive…")
        self.disk_line.pack(anchor="w")

        stats = tk.Frame(top, bg=t.SURFACE)
        stats.pack(side="right", padx=(28, 0), anchor="n")
        self.stat_junk = self._stat(stats, "JUNK FOUND", t.ACCENT)
        self.stat_ram = self._stat(stats, "MEMORY USED", t.TEXT)
        self.stat_startup = self._stat(stats, "STARTUP APPS", t.TEXT)

        foot = tk.Frame(body, bg=t.SURFACE)
        foot.pack(fill="x", pady=(16, 0))
        self.smart_btn = button(foot, "Smart Clean now", self.smart_clean, "primary", padx=22, pady=10)
        self.smart_btn.pack(side="left")
        self.smart_note = muted(foot, "Scans safe locations only. You approve before anything is removed.")
        self.smart_note.pack(side="left", padx=(14, 0))

    def _stat(self, parent, caption: str, color: str) -> tk.Label:
        box = tk.Frame(parent, bg=t.SURFACE)
        box.pack(side="left", padx=(0, 26))
        value = tk.Label(box, text="--", font=t.H1, fg=color, bg=t.SURFACE, anchor="w")
        value.pack(anchor="w")
        tk.Label(box, text=caption, font=t.TINY, fg=t.TEXT_FAINT, bg=t.SURFACE, anchor="w").pack(anchor="w")
        return value

    # ------------------------------------------------------------------ #
    def _build_columns(self, parent) -> None:
        row = tk.Frame(parent, bg=t.BG)
        row.pack(fill="x", pady=(12, 0))
        row.columnconfigure(0, weight=3, uniform="cols")
        row.columnconfigure(1, weight=2, uniform="cols")

        storage = Card(row)
        storage.grid(row=0, column=0, sticky="nsew", padx=(0, t.GAP))
        tk.Label(storage.body, text="Storage", font=t.H2, fg=t.TEXT, bg=t.SURFACE, anchor="w").pack(anchor="w")
        self.drives_box = tk.Frame(storage.body, bg=t.SURFACE)
        self.drives_box.pack(fill="x", pady=(14, 0))

        memory = Card(row)
        memory.grid(row=0, column=1, sticky="nsew")
        tk.Label(memory.body, text="Memory", font=t.H2, fg=t.TEXT, bg=t.SURFACE, anchor="w").pack(anchor="w")
        self.ram_value = tk.Label(memory.body, text="--", font=t.H1, fg=t.TEXT, bg=t.SURFACE, anchor="w")
        self.ram_value.pack(anchor="w", pady=(10, 0))
        self.ram_meter = Meter(memory.body, height=10)
        self.ram_meter.pack(fill="x", pady=(8, 8))
        self.ram_line = muted(memory.body, "")
        self.ram_line.pack(anchor="w")
        self.ram_hint = muted(memory.body, "")
        self.ram_hint.pack(anchor="w", pady=(10, 0))

        # admin notice lives here so it is always visible
        self.admin_line = tk.Label(
            memory.body,
            text="",
            font=t.SMALL,
            fg=t.AMBER if not is_admin() else t.TEXT_FAINT,
            bg=t.SURFACE,
            anchor="w",
            justify="left",
            wraplength=320,
        )
        self.admin_line.pack(anchor="w", pady=(12, 0))

    def _build_shortcuts(self, parent) -> None:
        card = Card(parent)
        card.pack(fill="x", pady=(12, 0))
        head = tk.Frame(card.body, bg=t.SURFACE)
        head.pack(fill="x")
        tk.Label(head, text="Quick tools", font=t.H2, fg=t.TEXT, bg=t.SURFACE, anchor="w").pack(side="left")

        row = tk.Frame(card.body, bg=t.SURFACE)
        row.pack(fill="x", pady=(12, 0))
        specs = [
            ("Empty Recycle Bin", self.empty_bin, "danger"),
            ("Flush DNS cache", self.flush_dns, "ghost"),
            ("Disk Cleanup", lambda: system.open_windows_tool("disk_cleanup"), "ghost"),
            ("Storage settings", lambda: system.open_windows_tool("storage"), "ghost"),
        ]
        for index, (text, command, variant) in enumerate(specs):
            btn = button(row, text, command, variant, padx=14, pady=8)
            btn.grid(row=0, column=index, sticky="w", padx=(0, 10))

    def _build_recent(self, parent) -> None:
        self.recent = muted(parent, "", bg=t.BG)
        self.recent.pack(anchor="w", pady=(12, 0))

    # ------------------------------------------------------------------ #
    def refresh(self) -> None:
        drive = system.system_drive()
        if drive:
            self.free_value.configure(text=human_size(drive.free))
            self.total_label.configure(text=f"free of {human_size(drive.total)}")
            self.disk_meter.set(drive.percent / 100.0)
            self.disk_line.configure(
                text=f"{drive.letter}: {drive.label or 'Local disk'}  ·  {human_size(drive.used)} used  ·  "
                f"{drive.percent:.0f}% full"
            )
        else:
            self.free_value.configure(text="N/A")
            self.disk_line.configure(text="No fixed drive found.")

        self._render_drives()

        memory = system.memory_info()
        self.ram_value.configure(text=f"{memory['percent']:.0f}%")
        self.ram_meter.set(memory["percent"] / 100.0)
        self.ram_line.configure(
            text=f"{human_size(memory['used'])} of {human_size(memory['total'])} in use  ·  "
            f"{human_size(memory['free'])} available"
        )
        if memory["percent"] >= 85:
            self.ram_hint.configure(text="High memory pressure. Check the Performance tab for heavy apps.",
                                    fg=t.RED)
        elif memory["percent"] >= 70:
            self.ram_hint.configure(text="Moderate memory use. Closing unused apps will free more.",
                                    fg=t.AMBER)
        else:
            self.ram_hint.configure(text="Memory looks healthy.", fg=t.TEXT_DIM)

        try:
            count = startup.enabled_count()
        except Exception:
            count = 0
        self.stat_startup.configure(text=str(count))
        self.stat_junk.configure(text=human_size(self._junk_total) if self._junk_total else "—")
        self.stat_ram.configure(text=f"{memory['percent']:.0f}%")

        if is_admin():
            self.admin_line.configure(text="Running as administrator — system locations are included.",
                                      fg=t.TEXT_FAINT)
        else:
            self.admin_line.configure(
                text="Standard mode. Windows system folders are skipped until you restart as administrator.",
                fg=t.AMBER,
            )

        last = cleaner.last_clean()
        if last:
            self.recent.configure(
                text=f"Last clean: {human_size(last.get('freed', 0))} freed · {last.get('deleted', 0)} items · "
                f"{last.get('duration', 0)}s"
            )
        else:
            self.recent.configure(text="No cleanup has run yet.")

    def _render_drives(self) -> None:
        for child in self.drives_box.winfo_children():
            child.destroy()
        drive_list = system.drives(False)
        if not drive_list:
            muted(self.drives_box, "No drives detected.").pack(anchor="w")
            return
        for drive in drive_list:
            block = tk.Frame(self.drives_box, bg=t.SURFACE)
            block.pack(fill="x", pady=(0, 10))
            top = tk.Frame(block, bg=t.SURFACE)
            top.pack(fill="x")
            tk.Label(top, text=f"{drive.letter}:", font=t.H3, fg=t.TEXT, bg=t.SURFACE).pack(side="left")
            if drive.label:
                tk.Label(top, text=f"  {drive.label}", font=t.SMALL, fg=t.TEXT_DIM, bg=t.SURFACE).pack(side="left")
            tk.Label(
                top,
                text=f"{human_size(drive.free)} free of {human_size(drive.total)}",
                font=t.SMALL,
                fg=t.TEXT_DIM,
                bg=t.SURFACE,
            ).pack(side="right")
            meter = Meter(block, height=7)
            meter.pack(fill="x", pady=(6, 0))
            meter.set(drive.percent / 100.0)

    # ------------------------------------------------------------------ #
    def on_show(self) -> None:
        self.refresh()
        if self._scan_time == 0:
            self.scan_quietly()

    def scan_quietly(self) -> None:
        """Background scan so the dashboard can show a junk estimate."""
        if self._busy:
            return
        self._busy = True
        targets = [tg for tg in scanner.TARGETS if tg.default_on and (is_admin() or not tg.needs_admin)]
        cancel = threading.Event()

        def work():
            return scanner.scan(targets, cancel)

        def done(results, error):
            self._busy = False
            if error or results is None:
                return
            self._junk_total = sum(r.total for r in results.values())
            self._junk_count = sum(r.count for r in results.values())
            self._scan_time = time.time()
            self.stat_junk.configure(text=human_size(self._junk_total))
            if self._junk_total:
                self.smart_note.configure(
                    text=f"{human_size(self._junk_total)} of safe junk ready to review."
                )

        self.app.run_bg(work, done)

    # ------------------------------------------------------------------ #
    def smart_clean(self) -> None:
        if self._busy:
            return
        self._busy = True
        self.smart_btn.configure(state="disabled", text="Scanning…")
        self.smart_note.configure(text="Scanning safe locations…")

        targets = [tg for tg in scanner.TARGETS if tg.default_on and (is_admin() or not tg.needs_admin)]
        cancel = threading.Event()
        progress = {"size": 0}

        def on_target(_target, result):
            progress["size"] += result.total
            self.app.post(self._scan_note, progress["size"])

        def work():
            return scanner.scan(targets, cancel, on_target=on_target)

        def done(results, error):
            self._busy = False
            self.smart_btn.configure(state="normal", text="Smart Clean now")
            if error or not results:
                self.smart_note.configure(text="Scan failed. Try again.")
                dialogs.notice(self.app, "Scan failed", str(error or "Unknown error"), kind="warn")
                return
            total = sum(r.total for r in results.values())
            count = sum(r.count for r in results.values())
            self._junk_total = total
            self._junk_count = count
            self.stat_junk.configure(text=human_size(total) if total else "—")
            if total <= 0:
                self.smart_note.configure(text="Nothing to clean. Your PC is already tidy.")
                dialogs.notice(
                    self.app,
                    "Already clean",
                    "No safe junk was found in the default locations.",
                    kind="success",
                )
                return
            self.smart_note.configure(text=f"{human_size(total)} found in {count} items.")
            go = dialogs.confirm(
                self.app,
                "Clean now?",
                f"Found {human_size(total)} of junk in {count} items.",
                ok_text="Clean now",
                detail="Temporary files, caches, error reports and the Recycle Bin are included. "
                       "Files still in use are skipped automatically.",
            )
            if go:
                self._run_clean(list(results.values()))

        self.app.run_bg(work, done)

    def _scan_note(self, size: int) -> None:
        if self._busy:
            self.smart_note.configure(text=f"Scanning… {human_size(size)} found so far")

    def _run_clean(self, results) -> None:
        self._busy = True
        self.smart_btn.configure(state="disabled", text="Cleaning…")

        def work():
            return cleaner.clean_results(results, threading.Event())

        def done(report, error):
            self._busy = False
            self.smart_btn.configure(state="normal", text="Smart Clean now")
            if error or report is None:
                self.smart_note.configure(text="Cleanup failed.")
                dialogs.notice(self.app, "Cleanup failed", str(error or ""), kind="danger")
                return
            self._junk_total = 0
            self._junk_count = 0
            self.stat_junk.configure(text="—")
            self.smart_note.configure(
                text=f"Freed {human_size(report.freed)} · {report.deleted} items removed."
            )
            detail = f"{report.failed} item(s) were in use and skipped." if report.failed else None
            dialogs.notice(
                self.app,
                f"{human_size(report.freed)} freed",
                f"Removed {report.deleted} items in {report.duration:.1f}s.",
                detail=detail,
            )
            self.refresh()

        self.app.run_bg(work, done)

    # ------------------------------------------------------------------ #
    def empty_bin(self) -> None:
        size, count = scanner.recycle_bin_info()
        if size <= 0:
            dialogs.notice(self.app, "Recycle Bin is empty", "There is nothing to remove.", kind="info")
            return
        if not dialogs.confirm(
            self.app,
            "Empty the Recycle Bin?",
            f"{human_size(size)} in {count} items will be permanently deleted.",
            ok_text="Empty it",
            danger=True,
        ):
            return
        ok, message = scanner.empty_recycle_bin()
        if ok:
            self.app.toast(f"Recycle Bin emptied · {human_size(size)} freed")
            self.refresh()
        else:
            dialogs.notice(self.app, "Could not empty", message or "Access denied.", kind="danger")

    def flush_dns(self) -> None:
        ok, _ = system.flush_dns()
        self.app.toast("DNS cache flushed" if ok else "Could not flush DNS", ok)
