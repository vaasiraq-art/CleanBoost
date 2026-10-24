"""Visual language for CleanBoost: one dark palette, one type scale."""
from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

# ---------------------------------------------------------------- palette ---
BG = "#0D1015"
SIDEBAR = "#10151C"
SURFACE = "#161C25"
SURFACE_ALT = "#1C2330"
SURFACE_HOVER = "#232C3A"
BORDER = "#242C39"
BORDER_SOFT = "#1C2430"

TEXT = "#E9EDF4"
TEXT_DIM = "#98A3B5"
TEXT_FAINT = "#67717F"

ACCENT = "#3B82F6"
ACCENT_HOVER = "#5494FF"
ACCENT_SOFT = "#152741"

GREEN = "#3DDC97"
GREEN_SOFT = "#0F2A21"
AMBER = "#F5B544"
AMBER_SOFT = "#2A2213"
RED = "#F87171"
RED_SOFT = "#2E1618"

RISK = {
    "safe": (GREEN, GREEN_SOFT, "Safe"),
    "caution": (AMBER, AMBER_SOFT, "Careful"),
    "review": (RED, RED_SOFT, "Review"),
}

# ------------------------------------------------------------- dimensions ---
PAD = 22
GAP = 14
SIDEBAR_W = 214
CARD_PAD = 18
ROW_H = 30

FAMILY = "Segoe UI"


def font(size: int = 10, weight: str = "normal", family: str = FAMILY):
    return (family, size, weight)


DISPLAY = font(27, "bold")
H1 = font(17, "bold")
H2 = font(12, "bold")
H3 = font(10, "bold")
BODY = font(10)
SMALL = font(9)
TINY = font(8)
MONO = ("Consolas", 9)


def setup(root: tk.Tk) -> None:
    """Apply ttk styles once, globally."""
    try:
        style = ttk.Style(root)
        style.theme_use("clam")
    except tk.TclError:  # pragma: no cover
        return

    style.configure(
        "Treeview",
        background=SURFACE,
        fieldbackground=SURFACE,
        foreground=TEXT,
        borderwidth=0,
        relief="flat",
        rowheight=ROW_H,
        font=SMALL,
    )
    style.map(
        "Treeview",
        background=[("selected", ACCENT_SOFT)],
        foreground=[("selected", TEXT)],
    )
    style.configure(
        "Treeview.Heading",
        background=SURFACE_ALT,
        foreground=TEXT_DIM,
        relief="flat",
        borderwidth=0,
        padding=(10, 8),
        font=SMALL,
    )
    style.map(
        "Treeview.Heading",
        background=[("active", SURFACE_HOVER)],
        foreground=[("active", TEXT)],
    )
    style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])

    style.configure(
        "Vertical.TScrollbar",
        background=SURFACE_ALT,
        troughcolor=BG,
        bordercolor=BG,
        arrowcolor=TEXT_FAINT,
        darkcolor=SURFACE_ALT,
        lightcolor=SURFACE_ALT,
        relief="flat",
        borderwidth=0,
        width=9,
    )
    style.map(
        "Vertical.TScrollbar",
        background=[("active", TEXT_FAINT), ("pressed", ACCENT)],
    )
    style.layout(
        "Vertical.TScrollbar",
        [("Vertical.Scrollbar.trough", {"sticky": "ns", "children": [("Vertical.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})]})],
    )


def preferred_family(root: tk.Misc) -> None:
    """Prefer Segoe UI Variable when the machine has it (Win11)."""
    global FAMILY, DISPLAY, H1, H2, H3, BODY, SMALL, TINY
    try:
        families = set(tkfont.families(root))
    except tk.TclError:
        return
    if "Segoe UI Variable Text" in families:
        FAMILY = "Segoe UI Variable Text"
        DISPLAY = font(27, "bold")
        H1 = font(17, "bold")
        H2 = font(12, "bold")
        H3 = font(10, "bold")
        BODY = font(10)
        SMALL = font(9)
        TINY = font(8)
