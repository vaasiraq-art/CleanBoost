"""Game Boost screen: real performance switches plus hardware readiness."""
from __future__ import annotations

import tkinter as tk

from core import gaming, system
from core.utils import human_size, is_admin
from ui import dialogs
from ui import theme as t
from ui.widgets import Card, Meter, ScrollFrame, Switch, Table, button, divider, muted
from .base import Page

SWITCHES = [
    ("game_mode", "Windows Game Mode",
     "Stops background work from stealing CPU and GPU time while you play."),
    ("game_dvr", "Background recording off (Game DVR)",
     "Turns off the hidden capture buffer that costs GPU time in every game."),
    ("power", "High / Ultimate performance plan",
     "Removes CPU clock caps and core parking so the chip boosts fully."),
    ("visual_fx", "Visual effects: best performance",
     "Drops window animations and shadows to give the GPU back a little headroom."),
    ("hags", "Hardware-accelerated GPU scheduling",
     "GPU manages its own memory queue. Needs a reboot and admin rights."),
]

TIPS = [
    "Most FPS lives in the game settings: shadows, anti-aliasing and resolution scale first.",
    "Update your GPU driver — it is the single biggest free performance win.",
    "Keep the game on an SSD with 15%+ free space so shader caches can grow.",
    "Cap FPS a few frames below your refresh rate for steadier frame times.",
    "Close browsers and launchers: they hold VRAM and CPU even when idle.",
    "Do not disable the page file — several modern games crash without it.",
]


class GamingPage(Page):
    title = "Game Boost"
    subtitle = "Real Windows performance switches. Nothing fake, everything reversible."

    def build(self) -> None:
        self._switches: dict[str, Switch] = {}
        self._procs: dict[str, system.WindowedProcess] = {}
        self._busy = False

        self.scroll = ScrollFrame(self.body, bg=t.BG)
        self.scroll.pack(fill="both", expand=True)
        wrap = self.scroll.body

        self._build_hero(wrap)
        self._build_switches(wrap)
        self._build_processes(wrap)
        self._build_hardware(wrap)
        self._build_tips(wrap)

    # ------------------------------------------------------------------ #
    def _build_hero(self, parent) -> None:
        card = Card(parent)
        card.pack(fill="x")
        top = tk.Frame(card.body, bg=t.SURFACE)
        top.pack(fill="x")

        left = tk.Frame(top, bg=t.SURFACE)
        left.pack(side="left", fill="both", expand=True)
        tk.Label(left, text="CORE BOOST", font=t.TINY, fg=t.TEXT_FAINT, bg=t.SURFACE,
                 anchor="w").pack(anchor="w")
        self.status_value = tk.Label(left, text="—", font=t.DISPLAY, fg=t.TEXT, bg=t.SURFACE,
                                     anchor="w")
        self.status_value.pack(anchor="w", pady=(2, 0))
        self.status_line = muted(left, "")
        self.status_line.pack(anchor="w")
        self.level_meter = Meter(left, height=8)
        self.level_meter.pack(fill="x", pady=(12, 0))

        right = tk.Frame(top, bg=t.SURFACE)
        right.pack(side="right", anchor="n", padx=(28, 0))
        self.boost_btn = button(right, "Activate Game Boost", self.activate, "primary",
                                padx=20, pady=10)
        self.boost_btn.pack(fill="x")
        self.restore_btn = button(right, "Restore defaults", self.restore, "quiet",
                                  padx=20, pady=7)
        self.restore_btn.pack(fill="x", pady=(8, 0))

        note = "Applies Ultimate Performance, Game Mode and disables the Game DVR buffer."
        if not is_admin():
            note += "  Some switches need administrator rights."
        muted(card.body, note, bg=t.SURFACE).pack(anchor="w", pady=(16, 0))

    def _build_switches(self, parent) -> None:
        card = Card(parent)
        card.pack(fill="x", pady=(t.GAP, 0))
        tk.Label(card.body, text="Performance switches", font=t.H2, fg=t.TEXT, bg=t.SURFACE,
                 anchor="w").pack(anchor="w")
        muted(card.body, "Flip any switch on its own. Every change is backed up.",
              bg=t.SURFACE).pack(anchor="w", pady=(2, 10))

        for index, (key, title, hint) in enumerate(SWITCHES):
            if index:
                divider(card.body, bg=t.SURFACE).pack(fill="x")
            row = tk.Frame(card.body, bg=t.SURFACE)
            row.pack(fill="x")
            inner = tk.Frame(row, bg=t.SURFACE)
            inner.pack(fill="x", pady=11)
            texts = tk.Frame(inner, bg=t.SURFACE)
            texts.pack(side="left", fill="x", expand=True)
            tk.Label(texts, text=title, font=t.H3, fg=t.TEXT, bg=t.SURFACE, anchor="w").pack(anchor="w")
            tk.Label(texts, text=hint, font=t.TINY, fg=t.TEXT_FAINT, bg=t.SURFACE, anchor="w",
                     justify="left", wraplength=620).pack(anchor="w", pady=(2, 0))
            switch = Switch(inner, value=False, command=lambda value, k=key: self._toggle(k, value))
            switch.pack(side="right", padx=(16, 0))
            self._switches[key] = switch

    def _build_processes(self, parent) -> None:
        card = Card(parent)
        card.pack(fill="x", pady=(t.GAP, 0))
        head = tk.Frame(card.body, bg=t.SURFACE)
        head.pack(fill="x")
        titles = tk.Frame(head, bg=t.SURFACE)
        titles.pack(side="left", anchor="w")
        tk.Label(titles, text="Boost a running game", font=t.H2, fg=t.TEXT,
                 bg=t.SURFACE, anchor="w").pack(anchor="w")
        muted(titles, "Raises the process priority so Windows schedules it first.").pack(anchor="w")
        button(head, "Refresh", self.refresh_processes, "ghost", padx=14, pady=6).pack(side="right")

        self.proc_table = Table(
            card.body,
            [
                ("name", "Process", 180, "w"),
                ("title", "Window", 300, "w"),
                ("pid", "PID", 70, "e"),
                ("mem", "Memory", 110, "e"),
            ],
            height=5,
        )
        self.proc_table.pack(fill="both", expand=True, pady=(12, 0))

        actions = tk.Frame(card.body, bg=t.SURFACE)
        actions.pack(fill="x", pady=(12, 0))
        button(actions, "High priority", lambda: self.set_priority(True), "green",
               padx=14, pady=6).pack(side="left")
        button(actions, "Normal priority", lambda: self.set_priority(False), "ghost",
               padx=14, pady=6).pack(side="left", padx=(10, 0))
        muted(actions, "Priority resets when the game closes. Do not boost everything.").pack(
            side="left", padx=(12, 0)
        )

    def _build_hardware(self, parent) -> None:
        card = Card(parent)
        card.pack(fill="x", pady=(t.GAP, 0))
        head = tk.Frame(card.body, bg=t.SURFACE)
        head.pack(fill="x")
        tk.Label(head, text="Your hardware", font=t.H2, fg=t.TEXT, bg=t.SURFACE,
                 anchor="w").pack(side="left")
        self.score_label = tk.Label(head, text="", font=t.SMALL, fg=t.TEXT_DIM, bg=t.SURFACE)
        self.score_label.pack(side="right")

        grid = tk.Frame(card.body, bg=t.SURFACE)
        grid.pack(fill="x", pady=(12, 0))
        grid.columnconfigure(1, weight=1)
        self.hw: dict[str, tk.Label] = {}
        for index, (key, title) in enumerate(
            (("cpu", "CPU"), ("gpus", "GPU"), ("ram", "Memory"),
             ("display", "Display"), ("free", "System drive"))
        ):
            tk.Label(grid, text=title, font=t.TINY, fg=t.TEXT_FAINT, bg=t.SURFACE,
                     anchor="w", width=12).grid(row=index, column=0, sticky="w", pady=3)
            value = tk.Label(grid, text="—", font=t.SMALL, fg=t.TEXT, bg=t.SURFACE, anchor="w",
                             justify="left", wraplength=720)
            value.grid(row=index, column=1, sticky="w", pady=3)
            self.hw[key] = value

        divider(card.body, bg=t.SURFACE).pack(fill="x", pady=(12, 0))
        self.readiness_box = tk.Frame(card.body, bg=t.SURFACE)
        self.readiness_box.pack(fill="x", pady=(12, 0))

    def _build_tips(self, parent) -> None:
        card = Card(parent)
        card.pack(fill="x", pady=(t.GAP, 0))
        tk.Label(card.body, text="What actually raises FPS", font=t.H2, fg=t.TEXT,
                 bg=t.SURFACE, anchor="w").pack(anchor="w", pady=(0, 10))
        for tip in TIPS:
            row = tk.Frame(card.body, bg=t.SURFACE)
            row.pack(fill="x", pady=3)
            tk.Label(row, text="•", font=t.BODY, fg=t.ACCENT, bg=t.SURFACE).pack(side="left", anchor="n")
            tk.Label(row, text=tip, font=t.SMALL, fg=t.TEXT_DIM, bg=t.SURFACE, anchor="w",
                     justify="left", wraplength=780).pack(side="left", padx=(8, 0), anchor="w")

    # ------------------------------------------------------------------ #
    def on_show(self) -> None:
        self.after(30, self._refresh)

    def _refresh(self) -> None:
        level = gaming.boost_level()
        self.status_value.configure(text=f"{level} / 3")
        self.level_meter.set(level / 3.0,
                             t.GREEN if level == 3 else (t.AMBER if level else t.TEXT_FAINT))
        if level == 3:
            self.status_value.configure(fg=t.GREEN)
            self.status_line.configure(
                text="Game Mode on · Game DVR off · high-performance power plan active"
            )
        elif level:
            self.status_value.configure(fg=t.AMBER)
            self.status_line.configure(
                text=f"{level} of 3 core switches active — Game Mode · Game DVR off · power plan."
            )
        else:
            self.status_value.configure(fg=t.TEXT_DIM)
            self.status_line.configure(text="Stock Windows settings. Nothing applied yet.")

        self._switches["game_mode"].set(gaming.group_state("game_mode"))
        self._switches["game_dvr"].set(gaming.group_state("game_dvr"))
        self._switches["power"].set(gaming.is_high_power())
        self._switches["visual_fx"].set(gaming.group_state("visual_fx"))
        self._switches["hags"].set(gaming.group_state("hags"))

        self._refresh_hardware()
        self.refresh_processes()

    def _refresh_hardware(self) -> None:
        data = gaming.hardware()
        self.hw["cpu"].configure(text=data["cpu"])
        self.hw["gpus"].configure(text="  ·  ".join(data["gpus"]))
        self.hw["ram"].configure(
            text=f"{human_size(data['ram'])} installed · {human_size(data['ram_free'])} available"
        )
        self.hw["display"].configure(text=data["display"])
        self.hw["free"].configure(
            text=f"{human_size(data['free'])} free of {human_size(data['total'])}"
        )

        for child in self.readiness_box.winfo_children():
            child.destroy()
        rows = gaming.readiness()
        passed = sum(1 for _l, ok, _h in rows if ok)
        self.score_label.configure(
            text=f"{passed} / {len(rows)} checks passed",
            fg=t.GREEN if passed == len(rows) else (t.AMBER if passed >= 3 else t.RED),
        )
        for label_text, ok, hint in rows:
            row = tk.Frame(self.readiness_box, bg=t.SURFACE)
            row.pack(fill="x", pady=2)
            tk.Label(row, text="✓" if ok else "!", font=t.SMALL,
                     fg=t.GREEN if ok else t.AMBER, bg=t.SURFACE).pack(side="left", anchor="n")
            text = tk.Frame(row, bg=t.SURFACE)
            text.pack(side="left", fill="x", expand=True, padx=(8, 0))
            tk.Label(text, text=label_text, font=t.SMALL,
                     fg=t.TEXT if ok else t.TEXT_DIM, bg=t.SURFACE, anchor="w").pack(anchor="w")
            tk.Label(text, text=hint, font=t.TINY, fg=t.TEXT_FAINT, bg=t.SURFACE, anchor="w",
                     justify="left", wraplength=700).pack(anchor="w")

    # ------------------------------------------------------------------ #
    def refresh_processes(self) -> None:
        try:
            processes = system.windowed_processes(30)
        except Exception:
            processes = []
        self.proc_table.clear()
        self._procs.clear()
        for proc in processes:
            iid = self.proc_table.add(
                (proc.name, proc.title, str(proc.pid), human_size(proc.memory))
            )
            self._procs[iid] = proc

    def set_priority(self, high: bool) -> None:
        row = self.proc_table.selected_first()
        if not row:
            dialogs.notice(self.app, "No app selected",
                           "Pick the game from the list first. Start the game, then press Refresh.",
                           kind="info")
            return
        pid = int(row[2])
        ok, message = gaming.set_priority(pid, high)
        if ok:
            self.app.toast(f"{row[0]} set to {'high' if high else 'normal'} priority")
        else:
            dialogs.notice(self.app, "Could not change priority", message, kind="warn",
                           detail="Games with anti-cheat protection may block this. That is normal.")

    # ------------------------------------------------------------------ #
    def _toggle(self, key: str, value: bool) -> None:
        if key == "power":
            if value:
                gaming.remember_power_plan()
                ok, message = gaming.ensure_ultimate()
            else:
                ok, message = gaming.restore_balanced()
        else:
            ok, message = gaming.set_group(key, value)
            if ok and key == "hags" and value:
                message = "Reboot Windows to apply this one."
                ok = True

        if not ok:
            dialogs.notice(self.app, "Windows refused the change",
                           message or "Access denied.",
                           kind="warn",
                           detail="Restart CleanBoost as administrator to use this switch.")
        else:
            if key == "hags" and value:
                dialogs.notice(self.app, "GPU scheduling enabled",
                               "Restart Windows for hardware-accelerated GPU scheduling to take effect.",
                               kind="info")
            else:
                self.app.toast(f"{dict((k, t_) for k, t_, _h in SWITCHES)[key]} "
                               f"{'enabled' if value else 'disabled'}")
        self._refresh()

    # ------------------------------------------------------------------ #
    def activate(self) -> None:
        if self._busy:
            return
        self._busy = True
        self.boost_btn.configure(state="disabled", text="Boosting…")

        def work():
            return gaming.activate()

        def done(results, error):
            self._busy = False
            self.boost_btn.configure(state="normal", text="Activate Game Boost")
            if error or results is None:
                dialogs.notice(self.app, "Boost failed", str(error or ""), kind="danger")
                self._refresh()
                return
            ok_count = sum(1 for r in results if r.ok)
            detail = "\n".join(
                f"{'✓' if r.ok else '✗'}  {r.title}" + (f" — {r.message}" if r.message else "")
                for r in results
            )
            dialogs.notice(
                self.app,
                f"Game Boost applied ({ok_count}/{len(results)})",
                "Windows is now configured for maximum performance.",
                detail=detail,
                kind="success" if ok_count else "warn",
            )
            self._refresh()

        self.app.run_bg(work, done)

    def restore(self) -> None:
        if self._busy:
            return
        if not dialogs.confirm(
            self.app,
            "Restore Windows defaults?",
            "Game Mode, Game DVR, visual effects and GPU scheduling go back to their previous values.",
            ok_text="Restore defaults",
            detail="The Balanced power plan is re-activated. This is the same as before you used Game Boost.",
        ):
            return
        self._busy = True
        self.restore_btn.configure(state="disabled", text="Restoring…")

        def work():
            return gaming.deactivate()

        def done(results, error):
            self._busy = False
            self.restore_btn.configure(state="normal", text="Restore defaults")
            if error:
                dialogs.notice(self.app, "Restore failed", str(error), kind="danger")
            else:
                self.app.toast("Windows defaults restored")
            self._refresh()

        self.app.run_bg(work, done)
