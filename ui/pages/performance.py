"""Performance screen: memory pressure, processes and maintenance actions."""
from __future__ import annotations

import tkinter as tk

from core import cleaner, scanner, system
from core.utils import human_size
from ui import dialogs
from ui import theme as t
from ui.widgets import Card, Meter, ScrollFrame, Table, button, label, muted
from .base import Page

TIPS = [
    "Keep startup apps to a minimum — every one costs boot time and memory.",
    "Let Storage Sense empty your Recycle Bin and temp folders automatically.",
    "Keep at least 10–15% of C: free so Windows has room for updates and swap.",
    "Restart instead of shutting down now and then; Fast Startup can hide memory leaks.",
]


class PerformancePage(Page):
    title = "Performance"
    subtitle = "Memory pressure, heavy processes and one-click maintenance."

    def build(self) -> None:
        self._tick_id = None
        self._processes: dict[str, system.ProcessInfo] = {}

        self.scroll = ScrollFrame(self.body, bg=t.BG)
        self.scroll.pack(fill="both", expand=True)
        wrap = self.scroll.body

        # ---- memory ----
        card = Card(wrap)
        card.pack(fill="x")
        top = tk.Frame(card.body, bg=t.SURFACE)
        top.pack(fill="x")

        left = tk.Frame(top, bg=t.SURFACE)
        left.pack(side="left", anchor="w")
        tk.Label(left, text="MEMORY IN USE", font=t.TINY, fg=t.TEXT_FAINT, bg=t.SURFACE,
                 anchor="w").pack(anchor="w")
        self.ram_value = tk.Label(left, text="--", font=t.DISPLAY, fg=t.TEXT, bg=t.SURFACE, anchor="w")
        self.ram_value.pack(anchor="w", pady=(2, 0))
        self.ram_line = muted(left, "")
        self.ram_line.pack(anchor="w")

        self.refresh_btn = button(top, "Refresh", self.refresh, "ghost", padx=16, pady=7)
        self.refresh_btn.pack(side="right", anchor="n")

        self.ram_meter = Meter(card.body, height=10)
        self.ram_meter.pack(fill="x", pady=(16, 0))

        self.proc_label = muted(card.body, "Top memory users")
        self.proc_label.pack(anchor="w", pady=(16, 6))

        self.proc_table = Table(
            card.body,
            [
                ("name", "Process", 320, "w"),
                ("pid", "PID", 90, "e"),
                ("mem", "Memory", 120, "e"),
            ],
            height=9,
        )
        self.proc_table.pack(fill="both", expand=True)

        proc_actions = tk.Frame(card.body, bg=t.SURFACE)
        proc_actions.pack(fill="x", pady=(10, 0))
        button(proc_actions, "End selected task", self.end_task, "danger", padx=14, pady=6).pack(side="left")
        muted(proc_actions, "Ending a task can lose unsaved work. Prefer closing the app normally.").pack(
            side="left", padx=(12, 0)
        )

        # ---- tools ----
        tools = Card(wrap)
        tools.pack(fill="x", pady=(t.GAP, 0))
        tk.Label(tools.body, text="Maintenance tools", font=t.H2, fg=t.TEXT,
                 bg=t.SURFACE, anchor="w").pack(anchor="w")
        muted(tools.body, "Safe, reversible actions that often help more than any optimizer.").pack(
            anchor="w", pady=(2, 14)
        )

        grid = tk.Frame(tools.body, bg=t.SURFACE)
        grid.pack(fill="x")
        self._tool(grid, 0, 0, "Flush DNS cache", "Fix stale website lookups", self.flush_dns)
        self._tool(grid, 0, 1, "Empty Recycle Bin", "Reclaim deleted file space", self.empty_bin, "danger")
        self.hibernate_btn = self._tool(grid, 1, 0, "Hibernate file", "Free gigabytes if you never hibernate",
                                        self.toggle_hibernate)
        self._tool(grid, 1, 1, "Disk Cleanup (Windows)", "The built-in deep cleaner", self.disk_cleanup)
        self._tool(grid, 2, 0, "High performance plan", "Full clock speed when plugged in",
                   lambda: self.set_plan("High performance"))
        self._tool(grid, 2, 1, "Balanced plan", "Best default for laptops", lambda: self.set_plan("Balanced"))
        for column in (0, 1):
            grid.columnconfigure(column, weight=1, uniform="tools")

        # ---- tips ----
        tips = Card(wrap)
        tips.pack(fill="x", pady=(t.GAP, 0))
        tk.Label(tips.body, text="What actually makes Windows faster", font=t.H2, fg=t.TEXT,
                 bg=t.SURFACE, anchor="w").pack(anchor="w", pady=(0, 10))
        for tip in TIPS:
            row = tk.Frame(tips.body, bg=t.SURFACE)
            row.pack(fill="x", pady=3)
            tk.Label(row, text="•", font=t.BODY, fg=t.ACCENT, bg=t.SURFACE).pack(side="left", anchor="n")
            tk.Label(row, text=tip, font=t.SMALL, fg=t.TEXT_DIM, bg=t.SURFACE, anchor="w",
                     justify="left", wraplength=780).pack(side="left", padx=(8, 0), anchor="w")

    def _tool(self, parent, row: int, column: int, title: str, subtitle: str, command, variant="ghost"):
        block = tk.Frame(parent, bg=t.SURFACE)
        block.grid(row=row, column=column, sticky="ew", padx=(0, 12), pady=(0, 12))
        btn = button(block, title, command, variant, padx=14, pady=7)
        btn.pack(anchor="w")
        muted(block, subtitle).pack(anchor="w", pady=(6, 0))
        return btn

    # ------------------------------------------------------------------ #
    def on_show(self) -> None:
        self.refresh()
        self._schedule()

    def on_hide(self) -> None:
        if self._tick_id:
            try:
                self.after_cancel(self._tick_id)
            except Exception:
                pass
            self._tick_id = None

    def _schedule(self) -> None:
        self._tick_id = self.after(5000, self._tick)

    def _tick(self) -> None:
        if not self.winfo_ismapped():
            self._tick_id = None
            return
        self.refresh(quiet=True)
        self._schedule()

    # ------------------------------------------------------------------ #
    def refresh(self, quiet: bool = False) -> None:
        memory = system.memory_info()
        self.ram_value.configure(text=f"{memory['percent']:.0f}%")
        self.ram_meter.set(memory["percent"] / 100.0)
        self.ram_line.configure(
            text=f"{human_size(memory['used'])} used of {human_size(memory['total'])}  ·  "
            f"{human_size(memory['free'])} available"
        )

        processes = system.top_processes(16)
        self.proc_table.clear()
        self._processes.clear()
        for proc in processes:
            iid = self.proc_table.add((proc.name, str(proc.pid), human_size(proc.memory)))
            self._processes[iid] = proc
        self.proc_label.configure(
            text=f"Top memory users · {len(processes)} shown · click Refresh for a new snapshot"
        )

        if not quiet:
            self._update_hibernate_label()

    def _update_hibernate_label(self) -> None:
        size = system.hibernation_size()
        if size > 0:
            self.hibernate_btn.configure(text=f"Disable hibernation · {human_size(size)}")
        else:
            self.hibernate_btn.configure(text="Enable hibernation")

    # ------------------------------------------------------------------ #
    def end_task(self) -> None:
        row = self.proc_table.selected_first()
        if not row:
            dialogs.notice(self.app, "No task selected", "Pick a process from the list first.", kind="info")
            return
        name, pid_text = row[0], row[1]
        pid = int(pid_text)
        if not dialogs.confirm(
            self.app,
            f"End {name}?",
            f"Process {pid} will be terminated immediately.",
            ok_text="End task",
            danger=True,
            detail="Unsaved work in that app will be lost.",
        ):
            return
        if system.kill_process(pid):
            self.app.toast(f"{name} ended")
            self.refresh()
        else:
            dialogs.notice(self.app, "Could not end task", "Access denied or the process already exited.",
                           kind="danger")

    def flush_dns(self) -> None:
        ok, _ = system.flush_dns()
        self.app.toast("DNS cache flushed" if ok else "Could not flush DNS", ok)

    def empty_bin(self) -> None:
        size, count = scanner.recycle_bin_info()
        if size <= 0:
            dialogs.notice(self.app, "Recycle Bin is empty", "Nothing to remove.", kind="info")
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
            self.app.toast(f"{human_size(size)} freed")
        else:
            dialogs.notice(self.app, "Could not empty", message or "Access denied.", kind="danger")

    def disk_cleanup(self) -> None:
        system.open_windows_tool("disk_cleanup")
        self.app.toast("Windows Disk Cleanup opened")

    def set_plan(self, name: str) -> None:
        ok, message = system.set_power_plan(name)
        if ok:
            self.app.toast(f"Power plan: {name}")
        else:
            dialogs.notice(self.app, "Could not change the power plan",
                           message or "This plan may be hidden on your PC.", kind="warn")

    def toggle_hibernate(self) -> None:
        size = system.hibernation_size()
        if size > 0:
            if not dialogs.confirm(
                self.app,
                "Disable hibernation?",
                f"Windows will delete hiberfil.sys and free {human_size(size)} immediately.",
                ok_text="Disable and free space",
                detail="Fast Startup will be turned off too. You can re-enable hibernation here later.",
            ):
                return
            ok, message = system.disable_hibernation()
            if ok:
                self.app.toast(f"Hibernation off · {human_size(size)} freed")
                self._update_hibernate_label()
            else:
                dialogs.notice(self.app, "Could not disable hibernation", message or "Run as administrator.",
                               kind="danger")
        else:
            ok, message = system.enable_hibernation()
            if ok:
                self.app.toast("Hibernation enabled")
                self._update_hibernate_label()
            else:
                dialogs.notice(self.app, "Could not enable hibernation", message or "Run as administrator.",
                               kind="danger")
