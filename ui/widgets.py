"""Reusable widgets, all drawn in the app palette."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from ui import theme as t


# --------------------------------------------------------------------------- #
# Card
# --------------------------------------------------------------------------- #
class Card(tk.Frame):
    """A 1px-bordered surface with generous inner padding."""

    def __init__(self, master, padding: int = t.CARD_PAD, bg: str = t.SURFACE, **kwargs):
        super().__init__(master, bg=t.BORDER, **kwargs)
        self._inner_shell = tk.Frame(self, bg=bg)
        self._inner_shell.pack(fill="both", expand=True, padx=1, pady=1)
        self.body = tk.Frame(self._inner_shell, bg=bg)
        self.body.pack(fill="both", expand=True, padx=padding, pady=padding)


# --------------------------------------------------------------------------- #
# Buttons
# --------------------------------------------------------------------------- #
VARIANTS = {
    "primary": dict(bg=t.ACCENT, fg="#FFFFFF", hover=t.ACCENT_HOVER, active=t.ACCENT_HOVER),
    "ghost": dict(bg=t.SURFACE_ALT, fg=t.TEXT, hover=t.SURFACE_HOVER, active=t.SURFACE_HOVER),
    "quiet": dict(bg=t.SURFACE, fg=t.TEXT_DIM, hover=t.SURFACE_ALT, active=t.SURFACE_ALT),
    "danger": dict(bg=t.RED_SOFT, fg=t.RED, hover="#3B1B1E", active="#3B1B1E"),
    "green": dict(bg=t.GREEN_SOFT, fg=t.GREEN, hover="#16382C", active="#16382C"),
}


def button(
    master,
    text: str,
    command: Callable | None = None,
    variant: str = "primary",
    *,
    width: int | None = None,
    font=None,
    padx: int = 15,
    pady: int = 8,
    state: str = "normal",
) -> tk.Button:
    style = VARIANTS.get(variant, VARIANTS["ghost"])
    btn = tk.Button(
        master,
        text=text,
        command=command,
        bg=style["bg"],
        fg=style["fg"],
        activebackground=style["active"],
        activeforeground=style["fg"],
        disabledforeground=t.TEXT_FAINT,
        relief="flat",
        bd=0,
        highlightthickness=0,
        cursor="hand2",
        font=font or t.H3,
        padx=padx,
        pady=pady,
        takefocus=0,
    )
    if width:
        btn.configure(width=width)
    if state == "disabled":
        btn.configure(state="disabled", cursor="arrow")

    def on_enter(_event=None):
        if str(btn["state"]) != "disabled":
            btn.configure(bg=style["hover"])

    def on_leave(_event=None):
        if str(btn["state"]) != "disabled":
            btn.configure(bg=style["bg"])

    btn.bind("<Enter>", on_enter)
    btn.bind("<Leave>", on_leave)
    return btn


def link(master, text: str, command: Callable, *, fg: str = t.ACCENT, bg: str = t.SURFACE, font=None) -> tk.Label:
    label = tk.Label(master, text=text, bg=bg, fg=fg, font=font or t.SMALL, cursor="hand2")
    label.bind("<Button-1>", lambda _e: command())
    label.bind("<Enter>", lambda _e: label.configure(fg=t.ACCENT_HOVER))
    label.bind("<Leave>", lambda _e: label.configure(fg=fg))
    return label


# --------------------------------------------------------------------------- #
# Badge
# --------------------------------------------------------------------------- #
class Badge(tk.Label):
    def __init__(self, master, text: str = "", fg: str = t.TEXT_DIM, bg: str = t.SURFACE_ALT, **kwargs):
        super().__init__(
            master,
            text=f" {text} ",
            bg=bg,
            fg=fg,
            font=t.TINY,
            padx=5,
            pady=2,
            **kwargs,
        )

    def set_risk(self, risk: str) -> None:
        fg, bg, label = t.RISK.get(risk, (t.TEXT_DIM, t.SURFACE_ALT, risk.title()))
        self.configure(text=f" {label} ", fg=fg, bg=bg)


# --------------------------------------------------------------------------- #
# Checkbox
# --------------------------------------------------------------------------- #
class CheckBox(tk.Canvas):
    def __init__(self, master, variable: tk.BooleanVar, bg: str = t.SURFACE, size: int = 18, command=None):
        super().__init__(master, width=size, height=size, bg=bg, highlightthickness=0, bd=0, cursor="hand2")
        self._var = variable
        self._size = size
        self._command = command
        self._bg = bg
        self._var.trace_add("write", lambda *_: self._draw())
        self.bind("<Button-1>", self._toggle)
        self._draw()

    def _toggle(self, _event=None) -> None:
        self._var.set(not self._var.get())
        if self._command:
            self._command()

    def _draw(self) -> None:
        self.delete("all")
        pad = 1
        s = self._size
        if self._var.get():
            self.create_rectangle(pad, pad, s - pad, s - pad, fill=t.ACCENT, outline=t.ACCENT)
            self.create_line(5, s * 0.52, s * 0.42, s * 0.74, fill="#FFFFFF", width=2, capstyle="round")
            self.create_line(s * 0.42, s * 0.74, s - 4, s * 0.30, fill="#FFFFFF", width=2, capstyle="round")
        else:
            self.create_rectangle(pad, pad, s - pad, s - pad, fill=self._bg, outline=t.BORDER, width=1)


# --------------------------------------------------------------------------- #
# Segmented control
# --------------------------------------------------------------------------- #
class Segmented(tk.Frame):
    """A row of pill buttons, one selected."""

    def __init__(self, master, options: list[tuple[str, object]], value, command=None, bg: str = t.SURFACE):
        super().__init__(master, bg=bg)
        self._command = command
        self._value = value
        self._buttons: dict[object, tk.Label] = {}
        for text, val in options:
            pill = tk.Label(
                self,
                text=text,
                font=t.SMALL,
                bg=t.SURFACE_ALT,
                fg=t.TEXT_DIM,
                padx=12,
                pady=5,
                cursor="hand2",
            )
            pill.pack(side="left", padx=(0, 6))
            pill.bind("<Button-1>", lambda _e, v=val: self.set(v))
            self._buttons[val] = pill
        self._paint()

    def set(self, value) -> None:
        self._value = value
        self._paint()
        if self._command:
            self._command(value)

    def get(self):
        return self._value

    def _paint(self) -> None:
        for val, pill in self._buttons.items():
            if val == self._value:
                pill.configure(bg=t.ACCENT, fg="#FFFFFF")
            else:
                pill.configure(bg=t.SURFACE_ALT, fg=t.TEXT_DIM)


# --------------------------------------------------------------------------- #
# Switch
# --------------------------------------------------------------------------- #
class Switch(tk.Canvas):
    """A small iOS-style toggle."""

    def __init__(self, master, value: bool = False, command=None, bg: str = t.SURFACE,
                 width: int = 44, height: int = 24):
        super().__init__(master, width=width, height=height, bg=bg, highlightthickness=0,
                         bd=0, cursor="hand2")
        self._value = bool(value)
        self._command = command
        self._track_w = width
        self._track_h = height
        self.bind("<Button-1>", self._toggle)
        self._draw()

    def get(self) -> bool:
        return self._value

    def set(self, value: bool) -> None:
        self._value = bool(value)
        self._draw()

    def _toggle(self, _event=None) -> None:
        self._value = not self._value
        self._draw()
        if self._command:
            self._command(self._value)

    def _draw(self) -> None:
        self.delete("all")
        w, h = self._track_w, self._track_h
        pad = 2
        track = t.ACCENT if self._value else t.SURFACE_ALT
        knob = "#FFFFFF" if self._value else t.TEXT_FAINT
        # pill track
        self.create_oval(pad, pad, h - pad, h - pad, fill=track, outline="")
        self.create_oval(w - h + pad, pad, w - pad, h - pad, fill=track, outline="")
        self.create_rectangle(h / 2, pad, w - h / 2, h - pad, fill=track, outline="")
        # knob
        r = (h - pad * 2) / 2 - 2
        cy = h / 2
        cx = (w - h / 2 - 3) if self._value else (h / 2 + 1)
        self.create_oval(cx - r, cy - r, cx + r, cy + r, fill=knob, outline="")


# --------------------------------------------------------------------------- #
# Meter
# --------------------------------------------------------------------------- #
class Meter(tk.Canvas):
    """A thin proportional bar. Colour changes with fill level."""

    def __init__(self, master, bg: str = t.SURFACE, height: int = 8, color: str | None = None):
        super().__init__(master, height=height, bg=bg, highlightthickness=0, bd=0)
        self._value = 0.0
        self._color = color
        self._height = height
        self.bind("<Configure>", lambda _e: self._draw())

    def set(self, fraction: float, color: str | None = None) -> None:
        self._value = max(0.0, min(1.0, float(fraction)))
        if color:
            self._color = color
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        width = max(1, self.winfo_width())
        h = self._height
        r = h / 2
        self.create_oval(0, 0, h, h, fill=t.SURFACE_ALT, outline="")
        self.create_oval(width - h, 0, width, h, fill=t.SURFACE_ALT, outline="")
        self.create_rectangle(0, 0, width, h, fill=t.SURFACE_ALT, outline="")
        fill = self._color
        if not fill:
            fill = t.GREEN if self._value < 0.7 else (t.AMBER if self._value < 0.88 else t.RED)
        span = self._value * width
        if span > 1:
            self.create_oval(0, 0, h, h, fill=fill, outline="")
            if span > h:
                self.create_oval(span - h, 0, span, h, fill=fill, outline="")
            self.create_rectangle(min(h / 2, span), 0, max(h / 2, span - h / 2), h, fill=fill, outline="")


# --------------------------------------------------------------------------- #
# Scrollable area
# --------------------------------------------------------------------------- #
class ScrollFrame(tk.Frame):
    def __init__(self, master, bg: str = t.BG):
        super().__init__(master, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.vsb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.body = tk.Frame(self.canvas, bg=bg)
        self._window = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.body.bind("<Configure>", self._on_body)
        self.canvas.bind("<Configure>", self._on_canvas)
        self.canvas.bind("<Enter>", self._bind_wheel)
        self.canvas.bind("<Leave>", self._unbind_wheel)

    def _on_body(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas(self, event):
        self.canvas.itemconfigure(self._window, width=event.width)

    def _bind_wheel(self, _event=None):
        self.canvas.bind_all("<MouseWheel>", self._wheel)

    def _unbind_wheel(self, _event=None):
        self.canvas.unbind_all("<MouseWheel>")

    def _wheel(self, event):
        if self.canvas.winfo_height() >= self.body.winfo_reqheight():
            return
        self.canvas.yview_scroll(int(-event.delta / 120), "units")

    def clear(self):
        for child in self.body.winfo_children():
            child.destroy()

    def scroll_top(self):
        self.canvas.yview_moveto(0)


# --------------------------------------------------------------------------- #
# Table
# --------------------------------------------------------------------------- #
class Table(tk.Frame):
    """Treeview + themed scrollbar with a typed helper API."""

    def __init__(self, master, columns: list[tuple[str, str, int, str]], height: int = 8, bg: str = t.SURFACE):
        super().__init__(master, bg=bg)
        self.columns = columns
        keys = [c[0] for c in columns]
        widest = max(columns, key=lambda c: c[2])[0]
        self.tree = ttk.Treeview(self, columns=keys, show="headings", height=height, selectmode="extended")
        for key, title, width, anchor in columns:
            self.tree.heading(key, text=title, anchor=anchor)
            self.tree.column(key, width=width, anchor=anchor, stretch=(key == widest))
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=self.vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        self.vsb.pack(side="right", fill="y")

    def clear(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

    def add(self, values: tuple, tags: tuple = (), iid: str | None = None):
        return self.tree.insert("", "end", values=values, tags=tags, iid=iid)

    def selected_iids(self) -> tuple[str, ...]:
        return self.tree.selection()

    def selected_first(self) -> tuple | None:
        sel = self.tree.selection()
        if not sel:
            return None
        return self.tree.item(sel[0], "values")

    def bind_double(self, callback):
        self.tree.bind("<Double-1>", callback)


# --------------------------------------------------------------------------- #
# Small pieces
# --------------------------------------------------------------------------- #
def label(master, text: str, font=None, fg: str = t.TEXT, bg: str = t.SURFACE, **kwargs) -> tk.Label:
    return tk.Label(master, text=text, font=font or t.BODY, fg=fg, bg=bg, anchor="w", **kwargs)


def muted(master, text: str, bg: str = t.SURFACE, **kwargs) -> tk.Label:
    return tk.Label(master, text=text, font=t.SMALL, fg=t.TEXT_DIM, bg=bg, anchor="w", **kwargs)


def divider(master, bg: str = t.SURFACE) -> tk.Frame:
    outer = tk.Frame(master, bg=bg)
    line = tk.Frame(outer, bg=t.BORDER_SOFT, height=1)
    line.pack(fill="x")
    return outer


def logo(parent, size: int = 30, bg: str = t.SIDEBAR) -> tk.Canvas:
    """The CleanBoost mark: rounded accent tile with a check."""
    canvas = tk.Canvas(parent, width=size, height=size, bg=bg, highlightthickness=0, bd=0)
    r = size * 0.26
    x1, y1, x2, y2 = 1, 1, size - 1, size - 1
    points = [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
        x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]
    canvas.create_polygon(points, smooth=True, splinesteps=32, fill=t.ACCENT, outline="")
    s = size
    canvas.create_line(s * 0.27, s * 0.52, s * 0.44, s * 0.70, fill="#FFFFFF", width=max(2, int(size / 11)),
                       capstyle="round")
    canvas.create_line(s * 0.44, s * 0.70, s * 0.74, s * 0.33, fill="#FFFFFF", width=max(2, int(size / 11)),
                       capstyle="round")
    return canvas
