"""Junk cleaner screen with streaming scan results."""
from __future__ import annotations

import threading
import time
import tkinter as tk

from core import cleaner, scanner
from core.utils import human_size, is_admin
from ui import dialogs
from ui import theme as t
from ui.widgets import Badge, Card, CheckBox, ScrollFrame, button, divider, label, link, muted
from .base import Page


class CleanerPage(Page):
    title = "Junk Cleaner"
    subtitle = "Review what will be removed, then clean."

    def build(self) -> None:
        self._cancel = threading.Event()
        self._results: dict[str, scanner.TargetResult] = {}
        self._rows: dict[str, dict] = {}
        self._scanning = False
        self._cleaning = False

        self.scan_btn = button(self.actions, "Scan now", self.start_scan, "primary", padx=18)
        self.scan_btn.pack(side="right")

        if not is_admin():
            notice = tk.Frame(self.body, bg=t.AMBER_SOFT)
            notice.pack(fill="x", pady=(0, 12))
            tk.Label(
                notice,
                text="  Standard mode — Windows system folders need administrator rights.",
                font=t.SMALL,
                fg=t.AMBER,
                bg=t.AMBER_SOFT,
                anchor="w",
            ).pack(side="left", pady=8)
            link(notice, "Restart as administrator", self.app.elevate, bg=t.AMBER_SOFT).pack(
                side="right", padx=12
            )

        bar = tk.Frame(self.body, bg=t.BG)
        bar.pack(fill="x", pady=(0, 12))
        self.summary = tk.Label(bar, text="Nothing scanned yet", font=t.SMALL, fg=t.TEXT_DIM, bg=t.BG)
        self.summary.pack(side="left")
        link(bar, "Select safe items", self.select_safe, bg=t.BG).pack(side="right")
        tk.Label(bar, text="·", font=t.SMALL, fg=t.TEXT_FAINT, bg=t.BG).pack(side="right", padx=8)
        link(bar, "Clear selection", self.select_none, bg=t.BG, fg=t.TEXT_DIM).pack(side="right")

        self.scroll = ScrollFrame(self.body, bg=t.BG)
        self.scroll.pack(fill="both", expand=True)
        self._build_sections()

        foot = tk.Frame(self.body, bg=t.BG)
        foot.pack(fill="x", pady=(14, 0))
        self.foot_label = tk.Label(foot, text="0 B selected", font=t.H3, fg=t.TEXT, bg=t.BG)
        self.foot_label.pack(side="left")
        self.clean_btn = button(foot, "Clean selected", self.clean, "primary", padx=20, pady=9, state="disabled")
        self.clean_btn.pack(side="right")
        self.empty_hint = muted(foot, "", bg=t.BG)
        self.empty_hint.pack(side="left", padx=(14, 0))

    # ------------------------------------------------------------------ #
    def _build_sections(self) -> None:
        for category in scanner.CATEGORY_ORDER:
            targets = [tg for tg in scanner.TARGETS if tg.category == category]
            if not targets:
                continue
            tk.Label(
                self.scroll.body,
                text=category.upper(),
                font=t.TINY,
                fg=t.TEXT_FAINT,
                bg=t.BG,
                anchor="w",
            ).pack(anchor="w", pady=(4, 8))

            card = Card(self.scroll.body, padding=0)
            card.pack(fill="x", pady=(0, 18))
            for index, target in enumerate(targets):
                if index:
                    divider(card.body, bg=t.SURFACE).pack(fill="x", padx=16)
                self._build_row(card.body, target)

    def _build_row(self, parent, target: scanner.Target) -> None:
        outer = tk.Frame(parent, bg=t.SURFACE, cursor="hand2")
        outer.pack(fill="x")
        inner = tk.Frame(outer, bg=t.SURFACE)
        inner.pack(fill="x", padx=16, pady=11)

        variable = tk.BooleanVar(value=False)
        check = CheckBox(inner, variable, bg=t.SURFACE, command=self._selection_changed)
        check.pack(side="left", pady=(2, 0))

        texts = tk.Frame(inner, bg=t.SURFACE)
        texts.pack(side="left", fill="x", expand=True, padx=(12, 10))

        title_row = tk.Frame(texts, bg=t.SURFACE)
        title_row.pack(anchor="w", fill="x")
        title = tk.Label(title_row, text=target.title, font=t.H3, fg=t.TEXT, bg=t.SURFACE, anchor="w")
        title.pack(side="left")
        badge = Badge(title_row)
        badge.set_risk(target.risk)
        badge.pack(side="left", padx=(8, 0))
        if target.needs_admin and not is_admin():
            Badge(title_row, text="ADMIN", fg=t.TEXT_FAINT, bg=t.SURFACE_ALT).pack(side="left", padx=(6, 0))

        subtitle_text = target.subtitle
        subtitle = tk.Label(
            texts,
            text=subtitle_text,
            font=t.TINY,
            fg=t.TEXT_FAINT,
            bg=t.SURFACE,
            anchor="w",
            justify="left",
            wraplength=560,
        )
        subtitle.pack(anchor="w", pady=(2, 0))

        right = tk.Frame(inner, bg=t.SURFACE)
        right.pack(side="right", anchor="e")
        size_label = tk.Label(right, text="—", font=t.H3, fg=t.TEXT_DIM, bg=t.SURFACE, anchor="e")
        size_label.pack(anchor="e")
        count_label = tk.Label(right, text="", font=t.TINY, fg=t.TEXT_FAINT, bg=t.SURFACE, anchor="e")
        count_label.pack(anchor="e")

        self._rows[target.key] = {
            "var": variable,
            "check": check,
            "size": size_label,
            "count": count_label,
            "frame": outer,
        }

        def toggle(_event=None):
            if self._cleaning:
                return
            variable.set(not variable.get())

        for widget in (outer, inner, texts, title_row, title, subtitle, right, size_label, count_label):
            widget.bind("<Button-1>", toggle)

    def refresh(self) -> None:
        self.start_scan()

    # ------------------------------------------------------------------ #
    def on_show(self) -> None:
        if not self._results and not self._scanning:
            self.start_scan()

    def start_scan(self) -> None:
        if self._scanning or self._cleaning:
            return
        self._cancel.set()
        self._cancel = threading.Event()
        self._scanning = True
        self._results.clear()
        self.scan_btn.configure(state="disabled", text="Scanning…")
        self.clean_btn.configure(state="disabled")
        self.summary.configure(text="Scanning…")

        for key, row in self._rows.items():
            row["var"].set(False)
            row["size"].configure(text="…", fg=t.TEXT_FAINT)
            row["count"].configure(text="")
            row["check"].configure(state="normal")

        cancel = self._cancel

        def work():
            results: dict[str, scanner.TargetResult] = {}
            for target in scanner.TARGETS:
                if cancel.is_set():
                    break
                result = scanner.collect(target, cancel)
                results[target.key] = result
                self.app.post(self._apply, target, result)
            return results

        def done(results, error):
            self._scanning = False
            self.scan_btn.configure(state="normal", text="Scan again")
            if error:
                self.summary.configure(text="Scan interrupted")
                dialogs.notice(self.app, "Scan failed", str(error), kind="warn")
                return
            if results:
                self._results = results
                total = sum(r.total for r in results.values())
                if total <= 0:
                    self.summary.configure(text="Nothing found — your PC is tidy")
                    self.empty_hint.configure(text="Nothing to remove right now.")
                else:
                    self.summary.configure(text=f"Found {human_size(total)} of junk")
                    self.empty_hint.configure(text="")
            self._selection_changed()

        self.app.run_bg(work, done)

    def _apply(self, target: scanner.Target, result: scanner.TargetResult) -> None:
        row = self._rows.get(target.key)
        if not row:
            return
        self._results[target.key] = result
        total = result.total
        row["size"].configure(text=human_size(total) if total else "—",
                              fg=t.TEXT if total else t.TEXT_FAINT)
        row["count"].configure(text=f"{result.count} items" if result.count else "")
        if total > 0 and target.default_on:
            row["var"].set(True)

    def _selection_changed(self) -> None:
        total = 0
        count = 0
        for key, row in self._rows.items():
            if not row["var"].get():
                continue
            result = self._results.get(key)
            if result:
                total += result.total
                count += result.count
        self.foot_label.configure(text=f"{human_size(total)} selected · {count} items")
        if total > 0 and not self._scanning and not self._cleaning:
            self.clean_btn.configure(state="normal")
        else:
            self.clean_btn.configure(state="disabled")
        if self._results and total == 0:
            self.summary.configure(text="Nothing selected")
        elif self._results and not self._scanning and total > 0:
            self.summary.configure(text=f"Ready to free {human_size(total)}")

    def select_safe(self) -> None:
        for key, row in self._rows.items():
            result = self._results.get(key)
            if result and result.total > 0 and result.target.risk == "safe":
                row["var"].set(True)
        self._selection_changed()

    def select_none(self) -> None:
        for row in self._rows.values():
            row["var"].set(False)
        self._selection_changed()

    # ------------------------------------------------------------------ #
    def clean(self) -> None:
        if self._cleaning or self._scanning:
            return
        chosen = [
            self._results[key]
            for key, row in self._rows.items()
            if row["var"].get() and key in self._results and self._results[key].total > 0
        ]
        if not chosen:
            return
        total = sum(r.total for r in chosen)
        count = sum(r.count for r in chosen)
        needs_admin = [r.target.title for r in chosen if r.target.needs_admin and not is_admin()]
        detail = None
        if needs_admin:
            detail = "Skipped without admin rights: " + ", ".join(needs_admin[:4])
        if not dialogs.confirm(
            self.app,
            f"Remove {human_size(total)}?",
            f"{count} items across {len(chosen)} categories will be permanently deleted.",
            ok_text="Delete now",
            danger=True,
            detail=detail,
        ):
            return

        self._cleaning = True
        self.clean_btn.configure(state="disabled", text="Cleaning…")
        self.scan_btn.configure(state="disabled")
        cancel = threading.Event()

        def progress(path, index, total_items):
            self.app.post(self._on_progress, index, total_items)

        def work():
            return cleaner.clean_results(chosen, cancel, progress)

        def done(report, error):
            self._cleaning = False
            self.clean_btn.configure(text="Clean selected")
            self.scan_btn.configure(state="normal", text="Scan again")
            if error or report is None:
                dialogs.notice(self.app, "Cleanup failed", str(error or ""), kind="danger")
                self._selection_changed()
                return
            self._results.clear()
            self.summary.configure(text=f"Freed {human_size(report.freed)}")
            detail = None
            if report.failed:
                detail = f"{report.failed} item(s) were locked or in use and were skipped."
            dialogs.notice(
                self.app,
                f"{human_size(report.freed)} freed",
                f"Removed {report.deleted} items. Drive space is available again.",
                detail=detail,
            )
            self.start_scan()

        self.app.run_bg(work, done)

    def _on_progress(self, index: int, total: int) -> None:
        self.clean_btn.configure(text=f"Cleaning {index}/{total}")
