"""Startup apps screen."""
from __future__ import annotations

import tkinter as tk

from core import startup, system
from ui import dialogs
from ui import theme as t
from ui.widgets import Card, Table, button, link, muted
from .base import Page


class StartupPage(Page):
    title = "Startup Apps"
    subtitle = "Fewer boot apps means a faster login and lower memory use."

    def build(self) -> None:
        self._items: dict[str, startup.StartupItem] = {}

        self.refresh_btn = button(self.actions, "Refresh", self.refresh, "ghost", padx=16)
        self.refresh_btn.pack(side="right")

        card = Card(self.body)
        card.pack(fill="both", expand=True)

        head = tk.Frame(card.body, bg=t.SURFACE)
        head.pack(fill="x")
        tk.Label(head, text="Programs that start with Windows", font=t.H2, fg=t.TEXT,
                 bg=t.SURFACE, anchor="w").pack(side="left")
        self.count_label = tk.Label(head, text="", font=t.SMALL, fg=t.TEXT_DIM, bg=t.SURFACE)
        self.count_label.pack(side="right")

        self.table = Table(
            card.body,
            [
                ("name", "Program", 280, "w"),
                ("state", "State", 95, "w"),
                ("location", "Source", 140, "w"),
                ("command", "Command", 400, "w"),
            ],
            height=14,
        )
        self.table.pack(fill="both", expand=True, pady=(14, 0))
        self.table.tree.tag_configure("off", foreground=t.TEXT_FAINT)
        self.table.tree.tag_configure("on", foreground=t.TEXT)
        self.table.tree.bind("<<TreeviewSelect>>", self._selection_changed)
        self.table.bind_double(lambda _e: self.toggle_selected())

        actions = tk.Frame(card.body, bg=t.SURFACE)
        actions.pack(fill="x", pady=(14, 0))
        self.disable_btn = button(actions, "Disable selected", self.toggle_selected, "danger",
                                  padx=16, pady=7, state="disabled")
        self.disable_btn.pack(side="left")
        button(actions, "Open Windows startup settings",
               lambda: system.open_windows_tool("startup_settings"), "ghost", padx=14, pady=7).pack(
            side="left", padx=(10, 0)
        )
        muted(actions, "Disabled entries are backed up here and can be switched back on.").pack(
            side="left", padx=(14, 0)
        )

    # ------------------------------------------------------------------ #
    def on_show(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        try:
            items = startup.list_startup()
        except Exception as exc:
            dialogs.notice(self.app, "Could not read startup items", str(exc), kind="danger")
            items = []
        self._items.clear()
        self.table.clear()
        for item in items:
            iid = self.table.add(
                (item.name, item.state, item.location, item.command),
                tags=("on" if item.enabled else "off",),
            )
            self._items[iid] = item
        enabled = sum(1 for item in items if item.enabled)
        self.count_label.configure(text=f"{enabled} enabled · {len(items) - enabled} disabled")
        self._selection_changed()

    def _selection_changed(self, _event=None) -> None:
        selection = self.table.tree.selection()
        if not selection:
            self.disable_btn.configure(state="disabled", text="Disable selected")
            return
        item = self._items.get(selection[0])
        if not item:
            self.disable_btn.configure(state="disabled")
            return
        self.disable_btn.configure(
            state="normal",
            text="Disable selected" if item.enabled else "Enable selected",
        )

    # ------------------------------------------------------------------ #
    def toggle_selected(self) -> None:
        selection = self.table.tree.selection()
        if not selection:
            return
        item = self._items.get(selection[0])
        if not item:
            return
        if item.enabled:
            if not dialogs.confirm(
                self.app,
                f"Disable {item.name}?",
                "It will no longer start automatically when you sign in.",
                ok_text="Disable",
                detail="This is reversible: the entry is backed up and appears here as disabled.",
            ):
                return
            ok, message = startup.disable(item)
        else:
            ok, message = startup.enable(item)
        if ok:
            self.app.toast(f"{item.name} {'disabled' if item.enabled else 'enabled'}")
            self.refresh()
        else:
            dialogs.notice(self.app, "Windows refused the change", message or "Access denied.",
                           kind="danger",
                           detail="Registry Run keys may need administrator rights.")
