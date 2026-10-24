"""CleanBoost window shell: sidebar, page router, toast and task plumbing."""
from __future__ import annotations

import ctypes
import os
import queue
import threading
import tkinter as tk
import traceback

from core.utils import (
    APP_NAME,
    APP_TAGLINE,
    APP_VERSION,
    app_icon_path,
    is_admin,
    relaunch_as_admin,
)
from ui import dialogs
from ui import theme as t
from ui.pages.about import AboutPage
from ui.pages.cleaner import CleanerPage
from ui.pages.dupes import DupesPage
from ui.pages.gaming import GamingPage
from ui.pages.overview import OverviewPage
from ui.pages.performance import PerformancePage
from ui.pages.space import SpacePage
from ui.pages.startup import StartupPage
from ui.widgets import logo

NAV = [
    ("overview", "Overview"),
    ("cleaner", "Junk Cleaner"),
    ("space", "Space Analyzer"),
    ("dupes", "Duplicate Files"),
    ("startup", "Startup Apps"),
    ("performance", "Performance"),
    ("gaming", "Game Boost"),
    ("about", "About"),
]

PAGES = {
    "overview": OverviewPage,
    "cleaner": CleanerPage,
    "space": SpacePage,
    "dupes": DupesPage,
    "startup": StartupPage,
    "performance": PerformancePage,
    "gaming": GamingPage,
    "about": AboutPage,
}


class NavItem(tk.Frame):
    def __init__(self, master, text: str, key: str, command):
        super().__init__(master, bg=t.SIDEBAR, cursor="hand2")
        self.key = key
        self._active = False
        self._command = command
        self.indicator = tk.Frame(self, bg=t.SIDEBAR, width=3)
        self.indicator.pack(side="left", fill="y")
        self.text = tk.Label(self, text=text, font=t.BODY, fg=t.TEXT_DIM, bg=t.SIDEBAR,
                             anchor="w", padx=0, pady=8)
        self.text.pack(side="left", fill="x", expand=True, padx=(13, 0))
        for widget in (self, self.text, self.indicator):
            widget.bind("<Button-1>", lambda _e: self._command(self.key))
            widget.bind("<Enter>", self._hover_on)
            widget.bind("<Leave>", self._hover_off)

    def _paint(self, bg: str, fg: str, indicator: str) -> None:
        self.configure(bg=bg)
        self.text.configure(bg=bg, fg=fg)
        self.indicator.configure(bg=indicator)

    def set_active(self, active: bool) -> None:
        self._active = active
        if active:
            self._paint(t.SURFACE, t.TEXT, t.ACCENT)
        else:
            self._paint(t.SIDEBAR, t.TEXT_DIM, t.SIDEBAR)

    def _hover_on(self, _event=None) -> None:
        if not self._active:
            self._paint(t.SURFACE_ALT, t.TEXT, t.SIDEBAR)

    def _hover_off(self, _event=None) -> None:
        if not self._active:
            self._paint(t.SIDEBAR, t.TEXT_DIM, t.SIDEBAR)


class CleanBoostApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.withdraw()
        self.title(f"{APP_NAME} — {APP_TAGLINE}")
        self.configure(bg=t.BG)
        self.minsize(1040, 680)
        self._center(1240, 820)

        try:
            if app_icon_path() and __import__("os").path.exists(app_icon_path()):
                self.iconbitmap(app_icon_path())
        except tk.TclError:
            pass

        t.preferred_family(self)
        t.setup(self)

        self._ui_queue: queue.Queue = queue.Queue()
        self._toast: tk.Frame | None = None
        self._current: str | None = None
        self._nav_items: dict[str, NavItem] = {}

        self._build_sidebar()
        self._build_pages()
        self._bind_keys()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.deiconify()
        self.update_idletasks()
        self._dark_titlebar()
        start_page = os.environ.get("CLEANBOOST_PAGE", "overview")
        self.show(start_page if start_page in self.pages else "overview")
        self.after(60, self._poll)

    # ------------------------------------------------------------------ #
    def _center(self, width: int, height: int) -> None:
        try:
            screen_w = self.winfo_screenwidth()
            screen_h = self.winfo_screenheight()
            x = max(0, (screen_w - width) // 2)
            y = max(0, (screen_h - height) // 2 - 20)
            self.geometry(f"{width}x{height}+{x}+{y}")
        except Exception:
            self.geometry(f"{width}x{height}")

    def _dark_titlebar(self) -> None:
        try:
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            value = ctypes.c_int(1)
            for attribute in (20, 19):
                result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)
                )
                if result == 0:
                    break
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    def _build_sidebar(self) -> None:
        sidebar = tk.Frame(self, bg=t.SIDEBAR, width=t.SIDEBAR_W)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        brand = tk.Frame(sidebar, bg=t.SIDEBAR)
        brand.pack(fill="x", padx=18, pady=(22, 26))
        logo(brand, 32, bg=t.SIDEBAR).pack(side="left")
        brand_text = tk.Frame(brand, bg=t.SIDEBAR)
        brand_text.pack(side="left", padx=(10, 0))
        tk.Label(brand_text, text=APP_NAME, font=t.H2, fg=t.TEXT, bg=t.SIDEBAR,
                 anchor="w").pack(anchor="w")
        tk.Label(brand_text, text="PC care suite", font=t.TINY, fg=t.TEXT_FAINT,
                 bg=t.SIDEBAR, anchor="w").pack(anchor="w")

        nav = tk.Frame(sidebar, bg=t.SIDEBAR)
        nav.pack(fill="x", padx=10)
        for key, text in NAV:
            item = NavItem(nav, text, key, self.show)
            item.pack(fill="x", pady=1)
            self._nav_items[key] = item

        foot = tk.Frame(sidebar, bg=t.SIDEBAR, cursor="hand2")
        foot.pack(side="bottom", fill="x", padx=18, pady=16)
        dot = tk.Canvas(foot, width=8, height=8, bg=t.SIDEBAR, highlightthickness=0)
        dot.pack(side="left", pady=(2, 0))
        dot.create_oval(0, 0, 7, 7, fill=t.GREEN if is_admin() else t.AMBER, outline="")
        state = "Administrator" if is_admin() else "Standard user"
        state_label = tk.Label(foot, text=f"  {state}", font=t.TINY, fg=t.TEXT_DIM, bg=t.SIDEBAR)
        state_label.pack(side="left")
        version = tk.Label(foot, text=f" v{APP_VERSION}", font=t.TINY, fg=t.TEXT_FAINT, bg=t.SIDEBAR)
        version.pack(side="right")
        for widget in (foot, dot, state_label, version):
            widget.bind("<Button-1>", lambda _e: self.show("about"))

        tk.Frame(sidebar, bg=t.BORDER_SOFT, height=1).pack(side="bottom", fill="x", padx=18, pady=(0, 4))

    def _build_pages(self) -> None:
        container = tk.Frame(self, bg=t.BG)
        container.pack(side="left", fill="both", expand=True)
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        self.pages = {}
        for key, page_class in PAGES.items():
            page = page_class(container, self)
            page.grid(row=0, column=0, sticky="nsew")
            self.pages[key] = page

    def _bind_keys(self) -> None:
        for index, (key, _text) in enumerate(NAV, start=1):
            self.bind_all(f"<Control-Key-{index}>", lambda _e, k=key: self.show(k))
        self.bind_all("<F5>", lambda _e: self._refresh_current())

    def _refresh_current(self) -> None:
        if not self._current:
            return
        page = self.pages[self._current]
        refresh = getattr(page, "refresh", None)
        if callable(refresh):
            refresh()
            self.toast("Refreshed")

    # ------------------------------------------------------------------ #
    def show(self, key: str) -> None:
        if key not in self.pages:
            return
        if self._current == key:
            return
        if self._current:
            try:
                self.pages[self._current].on_hide()
            except Exception:
                traceback.print_exc()
        self._current = key
        for nav_key, item in self._nav_items.items():
            item.set_active(nav_key == key)
        page = self.pages[key]
        page.tkraise()
        try:
            page.on_show()
        except Exception:
            traceback.print_exc()

    # ------------------------------------------------------------------ #
    # Thread -> UI plumbing (Tkinter is single threaded)
    # ------------------------------------------------------------------ #
    def post(self, callback, *args) -> None:
        self._ui_queue.put(lambda: callback(*args))

    def run_bg(self, work, done) -> None:
        def runner():
            try:
                result = work()
            except Exception as exc:  # noqa: BLE001 - surfaced to the caller
                self._ui_queue.put(lambda: done(None, exc))
            else:
                self._ui_queue.put(lambda: done(result, None))

        threading.Thread(target=runner, daemon=True, name="cleanboost-task").start()

    def _poll(self) -> None:
        while True:
            try:
                job = self._ui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                job()
            except Exception:
                traceback.print_exc()
        try:
            self.after(50, self._poll)
        except tk.TclError:
            pass

    # ------------------------------------------------------------------ #
    def toast(self, text: str, ok: bool = True) -> None:
        try:
            if self._toast is not None and self._toast.winfo_exists():
                self._toast.destroy()
        except tk.TclError:
            pass
        fg = t.GREEN if ok else t.RED
        bg = t.GREEN_SOFT if ok else t.RED_SOFT
        frame = tk.Frame(self, bg=bg, highlightthickness=1, highlightbackground=fg)
        tk.Label(frame, text=text, bg=bg, fg=fg, font=t.SMALL, padx=16, pady=9).pack()
        frame.place(relx=0.5, rely=1.0, anchor="s", y=-22)
        frame.lift()
        self._toast = frame
        self.after(3400, lambda: self._dismiss_toast(frame))

    def _dismiss_toast(self, frame) -> None:
        try:
            frame.destroy()
        except tk.TclError:
            pass
        if self._toast is frame:
            self._toast = None

    # ------------------------------------------------------------------ #
    def elevate(self) -> None:
        if is_admin():
            self.toast("Already running as administrator")
            return
        if relaunch_as_admin():
            self.after(300, self.destroy)
        else:
            dialogs.notice(
                self,
                "Elevation cancelled",
                "CleanBoost keeps running in standard mode. Personal folders are still fully supported.",
                kind="info",
            )

    def _on_close(self) -> None:
        self.destroy()
