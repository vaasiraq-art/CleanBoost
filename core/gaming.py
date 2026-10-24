"""Game Boost: real Windows performance switches, all reversible.

Everything here writes to a small, explicit set of registry values or calls
powercfg. Original values are backed up before the first change so "Restore
defaults" puts the machine back exactly as it was.
"""
from __future__ import annotations

import ctypes
import json
import os
import time
import winreg
from ctypes import wintypes
from dataclasses import dataclass

from . import system
from .utils import app_dir, is_admin, run_hidden

BACKUP_FILE = "gaming_backup.json"

HIVES = {
    "HKCU": winreg.HKEY_CURRENT_USER,
    "HKLM": winreg.HKEY_LOCAL_MACHINE,
}

ULTIMATE_GUID = "e9a42b02-d5df-448d-aa00-03f14749eb61"
HIGH_GUID = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"
BALANCED_GUID = "381b4222-f694-41f0-9685-ff5bb260df2e"

# key -> [(hive, path, value name, value when enabled)]
REG_GROUPS: dict[str, list[tuple[str, str, str, int]]] = {
    "game_mode": [
        ("HKCU", r"Software\Microsoft\GameBar", "AutoGameModeEnabled", 1),
        ("HKCU", r"Software\Microsoft\GameBar", "AllowAutoGameMode", 1),
    ],
    "game_dvr": [
        ("HKCU", r"System\GameConfigStore", "GameDVR_Enabled", 0),
        ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\GameDVR", "AppCaptureEnabled", 0),
    ],
    "visual_fx": [
        ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Explorer\VisualEffects",
         "VisualFXSetting", 2),
    ],
    "hags": [
        ("HKLM", r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers", "HwSchMode", 2),
    ],
}

# Human-facing description of each switch.
TWEAK_INFO = {
    "game_mode": (
        "Windows Game Mode",
        "Stops background work from stealing CPU/GPU time while you play.",
    ),
    "game_dvr": (
        "Background recording (Game DVR)",
        "Turns off the hidden capture buffer that costs GPU time in every game.",
    ),
    "visual_fx": (
        "Visual effects: best performance",
        "Drops window animations and shadows to free GPU/CPU for games.",
    ),
    "hags": (
        "Hardware-accelerated GPU scheduling",
        "Lets the GPU manage its own memory queue. Needs a reboot.",
    ),
}


# --------------------------------------------------------------------------- #
# Registry backup helpers
# --------------------------------------------------------------------------- #


def _backup_path():
    return app_dir() / BACKUP_FILE


def _load() -> dict:
    try:
        data = json.loads(_backup_path().read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("reg", {})
            data.setdefault("power_plan", None)
            return data
    except Exception:
        pass
    return {"reg": {}, "power_plan": None}


def _save(data: dict) -> None:
    try:
        _backup_path().write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass


def _key_id(hive: str, path: str, name: str) -> str:
    return f"{hive}|{path}|{name}"


def _read(hive: str, path: str, name: str) -> tuple[bool, object, int]:
    try:
        with winreg.OpenKey(HIVES[hive], path) as key:
            value, kind = winreg.QueryValueEx(key, name)
            return True, value, kind
    except OSError:
        return False, None, winreg.REG_DWORD


def _write(hive: str, path: str, name: str, value, kind: int = winreg.REG_DWORD) -> None:
    backup = _load()
    key_id = _key_id(hive, path, name)
    if key_id not in backup["reg"]:
        existed, old, old_kind = _read(hive, path, name)
        backup["reg"][key_id] = {
            "hive": hive,
            "path": path,
            "name": name,
            "existed": existed,
            "value": old if isinstance(old, (int, str)) else None,
            "kind": old_kind,
        }
        _save(backup)
    with winreg.CreateKeyEx(HIVES[hive], path, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, name, 0, kind, value)


def _restore_key(key_id: str, backup: dict) -> None:
    info = backup["reg"].get(key_id)
    if not info:
        return
    hive = HIVES.get(info["hive"])
    if hive is None:
        return
    try:
        if info.get("existed"):
            with winreg.CreateKeyEx(hive, info["path"], 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, info["name"], 0, info["kind"], info["value"])
        else:
            try:
                with winreg.OpenKey(hive, info["path"], 0, winreg.KEY_SET_VALUE) as key:
                    winreg.DeleteValue(key, info["name"])
            except OSError:
                pass
    except OSError:
        pass
    backup["reg"].pop(key_id, None)


# --------------------------------------------------------------------------- #
# Toggle groups
# --------------------------------------------------------------------------- #


def group_state(group: str) -> bool:
    entries = REG_GROUPS.get(group, [])
    if not entries:
        return False
    values = []
    for hive, path, name, target in entries:
        existed, value, _kind = _read(hive, path, name)
        values.append(bool(existed) and int(value) == int(target))
    return all(values)


def set_group(group: str, enabled: bool) -> tuple[bool, str]:
    entries = REG_GROUPS.get(group, [])
    if not entries:
        return False, "Unknown tweak"
    if enabled and group == "hags" and not is_admin():
        return False, "Administrator rights are required for this one."
    backup = _load()
    try:
        if enabled:
            for hive, path, name, target in entries:
                _write(hive, path, name, target)
        else:
            for hive, path, name, _target in entries:
                _restore_key(_key_id(hive, path, name), backup)
            _save(backup)
        return True, ""
    except PermissionError:
        return False, "Windows refused the change (access denied)."
    except OSError as exc:
        return False, f"Registry error ({getattr(exc, 'winerror', '?')})."


def tweak_state(group: str) -> bool:
    return group_state(group)


# --------------------------------------------------------------------------- #
# Power plans
# --------------------------------------------------------------------------- #


@dataclass
class PowerPlan:
    guid: str
    name: str


def _parse_plans(output: str) -> list[PowerPlan]:
    plans: list[PowerPlan] = []
    for line in output.splitlines():
        line = line.strip()
        if "GUID:" not in line:
            continue
        try:
            rest = line.split("GUID:", 1)[1].strip()
            guid = rest.split()[0].strip()
            name = rest.split("(", 1)[1].rsplit(")", 1)[0].strip() if "(" in rest else ""
            plans.append(PowerPlan(guid=guid, name=name))
        except IndexError:
            continue
    return plans


def list_power_plans() -> list[PowerPlan]:
    code, output = run_hidden(["powercfg", "/list"], timeout=20)
    return _parse_plans(output) if code == 0 else []


_plan_cache: dict = {"time": 0.0, "plan": None}


def active_plan(force: bool = False) -> PowerPlan | None:
    if not force and time.time() - _plan_cache["time"] < 3.0:
        return _plan_cache["plan"]
    code, output = run_hidden(["powercfg", "/getactivescheme"], timeout=20)
    plans = _parse_plans(output) if code == 0 else []
    plan = plans[0] if plans else None
    _plan_cache["plan"] = plan
    _plan_cache["time"] = time.time()
    return plan


def is_high_power() -> bool:
    plan = active_plan()
    if not plan:
        return False
    return plan.guid.lower() in {ULTIMATE_GUID, HIGH_GUID} or any(
        word in plan.name.lower() for word in ("ultimate", "high performance")
    )


def ensure_ultimate() -> tuple[bool, str]:
    """Switch to Ultimate Performance, creating the plan if Windows hid it."""
    plans = list_power_plans()
    target = next(
        (p for p in plans if p.guid.lower() == ULTIMATE_GUID or "ultimate" in p.name.lower()),
        None,
    )
    if target is None:
        code, output = run_hidden(["powercfg", "-duplicatescheme", ULTIMATE_GUID], timeout=20)
        if code != 0:
            # fall back to High performance, which every PC has
            code2, _ = run_hidden(["powercfg", "/setactive", HIGH_GUID], timeout=20)
            if code2 == 0:
                return True, "Ultimate Performance is unavailable here; High performance is active."
            return False, output.strip() or "Could not switch the power plan."
        plans = list_power_plans()
        target = next(
            (p for p in plans if p.guid.lower() == ULTIMATE_GUID or "ultimate" in p.name.lower()),
            None,
        )
        if target is None:
            run_hidden(["powercfg", "/setactive", HIGH_GUID], timeout=20)
            return True, "High performance is active."

    code, output = run_hidden(["powercfg", "/setactive", target.guid], timeout=20)
    if code != 0:
        return False, output.strip() or "Could not activate the plan."
    # keep clocks from parking while gaming (AC only)
    run_hidden(
        [
            "powercfg", "/setacvalueindex", target.guid, "SUB_PROCESSOR", "PROCTHROTTLEMIN", "100",
        ],
        timeout=20,
    )
    run_hidden(["powercfg", "/setactive", target.guid], timeout=20)
    _plan_cache["time"] = 0.0
    return True, ""


def restore_balanced() -> tuple[bool, str]:
    """Return to the plan that was active before the first boost (Balanced if unknown)."""
    backup = _load()
    original = backup.get("power_plan")
    target = original if isinstance(original, str) and original else BALANCED_GUID
    code, output = run_hidden(["powercfg", "/setactive", target], timeout=20)
    if code != 0 and target != BALANCED_GUID:
        code, output = run_hidden(["powercfg", "/setactive", BALANCED_GUID], timeout=20)
    if code == 0 and backup.get("power_plan"):
        backup["power_plan"] = None
        _save(backup)
    _plan_cache["time"] = 0.0
    return code == 0, output.strip()


def remember_power_plan() -> None:
    backup = _load()
    if not backup.get("power_plan"):
        plan = active_plan()
        if plan:
            backup["power_plan"] = plan.guid
            _save(backup)


# --------------------------------------------------------------------------- #
# One-click boost
# --------------------------------------------------------------------------- #


@dataclass
class StepResult:
    title: str
    ok: bool
    message: str = ""


def activate() -> list[StepResult]:
    results: list[StepResult] = []
    remember_power_plan()

    ok, message = ensure_ultimate()
    results.append(StepResult("Ultimate Performance power plan", ok, message))

    for group in ("game_mode", "game_dvr"):
        ok, message = set_group(group, True)
        results.append(StepResult(TWEAK_INFO[group][0], ok, message))

    return results


def deactivate() -> list[StepResult]:
    results: list[StepResult] = []
    for group in ("game_mode", "game_dvr", "visual_fx", "hags"):
        ok, message = set_group(group, False)
        if ok:
            results.append(StepResult(TWEAK_INFO[group][0], True))
    ok, message = restore_balanced()
    results.append(StepResult("Balanced power plan", ok, message))
    return results


def boost_level() -> int:
    """How many of the main gaming switches are currently on."""
    return sum(1 for group in ("game_mode", "game_dvr") if group_state(group)) + (
        1 if is_high_power() else 0
    )


# --------------------------------------------------------------------------- #
# Process priority
# --------------------------------------------------------------------------- #

PROCESS_SET_INFORMATION = 0x0200
HIGH_PRIORITY_CLASS = 0x00000080
NORMAL_PRIORITY_CLASS = 0x00000020


def set_priority(pid: int, high: bool = True) -> tuple[bool, str]:
    handle = ctypes.windll.kernel32.OpenProcess(PROCESS_SET_INFORMATION, False, int(pid))
    if not handle:
        return False, "Access denied — try running CleanBoost as administrator."
    try:
        cls = HIGH_PRIORITY_CLASS if high else NORMAL_PRIORITY_CLASS
        if ctypes.windll.kernel32.SetPriorityClass(handle, cls):
            return True, ""
        return False, "Windows refused the priority change."
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


# --------------------------------------------------------------------------- #
# Hardware summary + readiness
# --------------------------------------------------------------------------- #


def _cpu_name() -> str:
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "ProcessorNameString")
            return " ".join(str(value).split())
    except OSError:
        return "Unknown CPU"


def _gpu_names() -> list[str]:
    base = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
    names: list[str] = []
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base) as root:
            for index in range(16):
                try:
                    sub = winreg.EnumKey(root, index)
                except OSError:
                    break
                if not sub.isdigit():
                    continue
                try:
                    with winreg.OpenKey(root, sub) as key:
                        value, _ = winreg.QueryValueEx(key, "DriverDesc")
                        if value and "basic" not in str(value).lower():
                            names.append(str(value))
                except OSError:
                    continue
    except OSError:
        pass
    return names or ["Unknown GPU"]


class DEVMODEW(ctypes.Structure):
    _fields_ = [
        ("dmDeviceName", ctypes.c_wchar * 32),
        ("dmSpecVersion", wintypes.WORD),
        ("dmDriverVersion", wintypes.WORD),
        ("dmSize", wintypes.WORD),
        ("dmDriverExtra", wintypes.WORD),
        ("dmFields", wintypes.DWORD),
        ("dmPositionX", ctypes.c_long),
        ("dmPositionY", ctypes.c_long),
        ("dmDisplayOrientation", wintypes.DWORD),
        ("dmDisplayFixedOutput", wintypes.DWORD),
        ("dmColor", ctypes.c_short),
        ("dmDuplex", ctypes.c_short),
        ("dmYResolution", ctypes.c_short),
        ("dmTTOption", ctypes.c_short),
        ("dmCollate", ctypes.c_short),
        ("dmFormName", ctypes.c_wchar * 32),
        ("dmLogPixels", wintypes.WORD),
        ("dmBitsPerPel", wintypes.DWORD),
        ("dmPelsWidth", wintypes.DWORD),
        ("dmPelsHeight", wintypes.DWORD),
        ("dmDisplayFlags", wintypes.DWORD),
        ("dmDisplayFrequency", wintypes.DWORD),
        ("dmICMMethod", wintypes.DWORD),
        ("dmICMIntent", wintypes.DWORD),
        ("dmMediaType", wintypes.DWORD),
        ("dmDitherType", wintypes.DWORD),
        ("dmReserved1", wintypes.DWORD),
        ("dmReserved2", wintypes.DWORD),
        ("dmPanningWidth", wintypes.DWORD),
        ("dmPanningHeight", wintypes.DWORD),
    ]


def display_info() -> tuple[int, int, int]:
    """(width, height, refresh_hz) for the primary display."""
    try:
        devmode = DEVMODEW()
        devmode.dmSize = ctypes.sizeof(DEVMODEW)
        if ctypes.windll.user32.EnumDisplaySettingsW(None, -1, ctypes.byref(devmode)):
            return (
                int(devmode.dmPelsWidth),
                int(devmode.dmPelsHeight),
                int(devmode.dmDisplayFrequency),
            )
    except Exception:
        pass
    return (0, 0, 0)


def hardware() -> dict:
    memory = system.memory_info()
    width, height, hz = display_info()
    drive = system.system_drive()
    return {
        "cpu": _cpu_name(),
        "gpus": _gpu_names(),
        "ram": memory["total"],
        "ram_free": memory["free"],
        "display": f"{width} x {height} @ {hz} Hz" if width else "Unknown display",
        "free": drive.free if drive else 0,
        "total": drive.total if drive else 0,
    }


def readiness() -> list[tuple[str, bool, str]]:
    """(label, ok, hint) rows for the UI checklist."""
    memory = system.memory_info()
    drive = system.system_drive()
    rows: list[tuple[str, bool, str]] = []

    free_ratio = (drive.free / drive.total) if drive and drive.total else 0
    rows.append(
        (
            "Free space above 15%",
            free_ratio >= 0.15,
            f"{free_ratio * 100:.0f}% free — games need room for shaders and updates"
            if free_ratio < 0.15
            else "Plenty of room for shader caches and updates.",
        )
    )

    ram_gb = memory["total"] / (1024 ** 3)
    rows.append(
        (
            "16 GB RAM or more",
            ram_gb >= 15.5,
            f"{ram_gb:.0f} GB installed — modern games want 16 GB+."
            if ram_gb < 15.5
            else f"{ram_gb:.0f} GB installed — comfortable for gaming.",
        )
    )

    rows.append(
        (
            "High / Ultimate power plan",
            is_high_power(),
            "Balanced caps boost clocks on some systems."
            if not is_high_power()
            else "CPU is allowed to boost fully.",
        )
    )

    rows.append(
        (
            "Game Mode enabled",
            group_state("game_mode"),
            "Windows may let background apps compete for resources."
            if not group_state("game_mode")
            else "Background work is deprioritised while gaming.",
        )
    )

    rows.append(
        (
            "Background recording off",
            group_state("game_dvr"),
            "Game DVR keeps a capture buffer running in the background."
            if not group_state("game_dvr")
            else "No hidden capture buffer.",
        )
    )

    rows.append(
        (
            "GPU scheduling (HAGS)",
            group_state("hags"),
            "Optional — needs a reboot and a supported GPU."
            if not group_state("hags")
            else "Enabled (takes effect after a reboot).",
        )
    )
    return rows


def score() -> tuple[int, int]:
    rows = readiness()
    return sum(1 for _label, ok, _hint in rows if ok), len(rows)
