"""Page scaffolding shared by every screen."""
from __future__ import annotations

import tkinter as tk
from typing import Callable

from ui import theme as t


class Page(tk.Frame):
    title = ""
    subtitle = ""

    def __init__(self, master, app):
        super().__init__(master, bg=t.BG)
        self.app = app

        head = tk.Frame(self, bg=t.BG)
        head.pack(fill="x", padx=t.PAD, pady=(t.PAD, 14))

        left = tk.Frame(head, bg=t.BG)
        left.pack(side="left", anchor="w")
        tk.Label(left, text=self.title, font=t.H1, fg=t.TEXT, bg=t.BG, anchor="w").pack(anchor="w")
        if self.subtitle:
            tk.Label(
                left, text=self.subtitle, font=t.SMALL, fg=t.TEXT_DIM, bg=t.BG, anchor="w"
            ).pack(anchor="w", pady=(3, 0))

        self.actions = tk.Frame(head, bg=t.BG)
        self.actions.pack(side="right", anchor="e")

        self.body = tk.Frame(self, bg=t.BG)
        self.body.pack(fill="both", expand=True, padx=t.PAD, pady=(0, t.PAD))

        self.build()

    # --- hooks ----------------------------------------------------------- #
    def build(self) -> None:
        """Construct widgets inside self.body."""

    def on_show(self) -> None:
        pass

    def on_hide(self) -> None:
        pass
