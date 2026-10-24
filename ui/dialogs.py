"""Dark modal dialogs (confirmations and results)."""
from __future__ import annotations

import tkinter as tk

from ui import theme as t
from ui.widgets import button


class Modal(tk.Toplevel):
    def __init__(
        self,
        parent,
        title: str,
        message: str,
        *,
        ok_text: str = "OK",
        cancel_text: str | None = "Cancel",
        danger: bool = False,
        kind: str = "info",
        detail: str | None = None,
    ):
        super().__init__(parent)
        self.result = False
        self.withdraw()
        self.overrideredirect(True)
        self.configure(bg=t.BORDER)
        try:
            self.attributes("-topmost", True)
        except tk.TclError:
            pass

        inner = tk.Frame(self, bg=t.SURFACE)
        inner.pack(fill="both", expand=True, padx=1, pady=1)

        content = tk.Frame(inner, bg=t.SURFACE)
        content.pack(fill="both", expand=True, padx=24, pady=22)

        accent = {
            "info": t.ACCENT,
            "success": t.GREEN,
            "warn": t.AMBER,
            "danger": t.RED,
            "question": t.ACCENT,
        }.get(kind, t.ACCENT)

        top = tk.Frame(content, bg=t.SURFACE)
        top.pack(fill="x")
        mark = tk.Canvas(top, width=34, height=34, bg=t.SURFACE, highlightthickness=0)
        mark.pack(side="left", anchor="n")
        mark.create_oval(1, 1, 33, 33, fill=accent, outline="")
        glyph = {"success": "✓", "warn": "!", "danger": "!", "question": "?", "info": "i"}.get(kind, "i")
        mark.create_text(17, 18, text=glyph, fill="#0D1015" if kind != "danger" else "#2E1618",
                         font=(t.FAMILY, 15, "bold"))

        text_wrap = tk.Frame(top, bg=t.SURFACE)
        text_wrap.pack(side="left", fill="x", expand=True, padx=(14, 0))
        tk.Label(text_wrap, text=title, font=t.H2, fg=t.TEXT, bg=t.SURFACE, anchor="w",
                 justify="left").pack(anchor="w")
        tk.Label(
            text_wrap,
            text=message,
            font=t.BODY,
            fg=t.TEXT_DIM,
            bg=t.SURFACE,
            anchor="w",
            justify="left",
            wraplength=430,
        ).pack(anchor="w", pady=(6, 0))

        if detail:
            box = tk.Frame(content, bg=t.SURFACE_ALT)
            box.pack(fill="x", pady=(16, 0))
            tk.Label(
                box,
                text=detail,
                font=t.SMALL,
                fg=t.TEXT_DIM,
                bg=t.SURFACE_ALT,
                justify="left",
                anchor="w",
                wraplength=420,
            ).pack(fill="x", padx=12, pady=10)

        actions = tk.Frame(content, bg=t.SURFACE)
        actions.pack(fill="x", pady=(22, 0))

        ok_variant = "danger" if danger else "primary"
        ok_btn = button(actions, ok_text, self._ok, ok_variant, padx=18, pady=7)
        ok_btn.pack(side="right")
        if cancel_text:
            cancel_btn = button(actions, cancel_text, self._cancel, "ghost", padx=18, pady=7)
            cancel_btn.pack(side="right", padx=(0, 10))

        self.bind("<Escape>", lambda _e: self._cancel())
        self.bind("<Return>", lambda _e: self._ok())

        self.update_idletasks()
        width = max(self.winfo_reqwidth(), 380)
        height = self.winfo_reqheight()
        self.geometry(f"{width}x{height}")
        parent.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width() - width) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - height) // 3
        self.geometry(f"+{max(0, px)}+{max(0, py)}")
        self.deiconify()
        try:
            self.grab_set()
            self.focus_force()
        except tk.TclError:
            pass

    def _ok(self):
        self.result = True
        self.destroy()

    def _cancel(self):
        self.result = False
        self.destroy()


def confirm(parent, title: str, message: str, *, ok_text: str = "Continue",
            danger: bool = False, detail: str | None = None, kind: str = "question") -> bool:
    dialog = Modal(parent, title, message, ok_text=ok_text, danger=danger, detail=detail, kind=kind)
    parent.wait_window(dialog)
    return dialog.result


def notice(parent, title: str, message: str, *, kind: str = "success",
           detail: str | None = None, ok_text: str = "Done") -> None:
    dialog = Modal(parent, title, message, ok_text=ok_text, cancel_text=None, kind=kind, detail=detail)
    parent.wait_window(dialog)
