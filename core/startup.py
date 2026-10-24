"""Startup program management with a reversible backup."""
from __future__ import annotations

import json
import os
import shutil
import winreg
from dataclasses import dataclass

from .utils import app_dir

RUN_KEYS = [
    ("HKCU", winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"),
    ("HKLM", winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run"),
    (
        "HKLM",
        winreg.HKEY_LOCAL_MACHINE,
        r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Run",
    ),
]

HIVES = {
    "HKCU": winreg.HKEY_CURRENT_USER,
    "HKLM": winreg.HKEY_LOCAL_MACHINE,
}

STARTUP_FOLDERS = [
    os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"),
    os.path.expandvars(r"%ProgramData%\Microsoft\Windows\Start Menu\Programs\Startup"),
]

BACKUP_FILE = "startup_backup.json"
OFF_DIR = "startup_off"


@dataclass
class StartupItem:
    key: str
    name: str
    command: str
    location: str
    source: str  # registry | folder
    enabled: bool = True
    hive: str = ""
    subkey: str = ""
    value_name: str = ""
    file_path: str = ""

    @property
    def state(self) -> str:
        return "Enabled" if self.enabled else "Disabled"


def _off_dir() -> str:
    path = app_dir() / OFF_DIR
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def _load_backup() -> dict:
    path = app_dir() / BACKUP_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("registry", {})
            data.setdefault("folder", {})
            return data
    except Exception:
        pass
    return {"registry": {}, "folder": {}}


def _save_backup(data: dict) -> None:
    try:
        (app_dir() / BACKUP_FILE).write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass


def _registry_items() -> list[StartupItem]:
    items: list[StartupItem] = []
    for hive_name, hive, subkey in RUN_KEYS:
        try:
            with winreg.OpenKey(hive, subkey) as key:
                index = 0
                while True:
                    try:
                        name, value, _kind = winreg.EnumValue(key, index)
                    except OSError:
                        break
                    index += 1
                    if not name:
                        continue
                    items.append(
                        StartupItem(
                            key=f"reg|{hive_name}|{subkey}|{name}",
                            name=name,
                            command=str(value),
                            location=f"{hive_name}\\...\\Run",
                            source="registry",
                            enabled=True,
                            hive=hive_name,
                            subkey=subkey,
                            value_name=name,
                        )
                    )
        except OSError:
            continue
    return items


def _folder_items() -> list[StartupItem]:
    items: list[StartupItem] = []
    for folder in STARTUP_FOLDERS:
        if not os.path.isdir(folder):
            continue
        try:
            names = os.listdir(folder)
        except OSError:
            continue
        for name in names:
            if name.lower() in {"desktop.ini", "thumbs.db"}:
                continue
            full = os.path.join(folder, name)
            if not os.path.isfile(full):
                continue
            items.append(
                StartupItem(
                    key=f"folder|{os.path.normcase(full)}",
                    name=os.path.splitext(name)[0],
                    command=full,
                    location="Startup folder",
                    source="folder",
                    enabled=True,
                    file_path=full,
                )
            )
    return items


def _disabled_items() -> list[StartupItem]:
    backup = _load_backup()
    items: list[StartupItem] = []
    off = _off_dir()
    for key, info in backup.get("registry", {}).items():
        items.append(
            StartupItem(
                key=key,
                name=info.get("name", "?"),
                command=info.get("command", ""),
                location=info.get("location", "Registry"),
                source="registry",
                enabled=False,
                hive=info.get("hive", ""),
                subkey=info.get("subkey", ""),
                value_name=info.get("name", ""),
            )
        )
    for name, info in backup.get("folder", {}).items():
        stored = os.path.join(off, name)
        items.append(
            StartupItem(
                key=f"folder|{os.path.normcase(info.get('original', stored))}",
                name=os.path.splitext(name)[0],
                command=info.get("original", ""),
                location="Startup folder",
                source="folder",
                enabled=False,
                file_path=stored,
            )
        )
    return items


def list_startup() -> list[StartupItem]:
    items = _registry_items() + _folder_items()
    items.sort(key=lambda i: (not i.enabled, i.name.lower()))
    return items + _disabled_items()


def disable(item: StartupItem) -> tuple[bool, str]:
    backup = _load_backup()
    if item.source == "registry":
        hive = HIVES.get(item.hive)
        if hive is None:
            return False, "Unknown registry hive"
        try:
            with winreg.OpenKey(
                hive, item.subkey, 0, winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE
            ) as key:
                value, kind = winreg.QueryValueEx(key, item.value_name)
                winreg.DeleteValue(key, item.value_name)
            backup["registry"][item.key] = {
                "name": item.value_name,
                "command": value,
                "hive": item.hive,
                "subkey": item.subkey,
                "location": item.location,
                "kind": kind,
            }
            _save_backup(backup)
            return True, ""
        except OSError as exc:
            return False, f"Registry access denied ({exc.winerror})"
    # folder shortcut
    if not os.path.isfile(item.file_path):
        return False, "File not found"
    try:
        destination = os.path.join(_off_dir(), os.path.basename(item.file_path))
        shutil.move(item.file_path, destination)
        backup["folder"][os.path.basename(item.file_path)] = {
            "original": item.file_path,
            "name": item.name,
        }
        _save_backup(backup)
        return True, ""
    except Exception as exc:
        return False, str(exc)


def enable(item: StartupItem) -> tuple[bool, str]:
    backup = _load_backup()
    if item.source == "registry":
        info = backup["registry"].get(item.key, {})
        hive = HIVES.get(item.hive or info.get("hive", ""))
        subkey = item.subkey or info.get("subkey", "")
        command = info.get("command") or item.command
        name = item.value_name or item.name
        kind = info.get("kind", winreg.REG_SZ)
        if hive is None or not subkey:
            return False, "Missing backup data"
        try:
            with winreg.OpenKey(hive, subkey, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, name, 0, kind, command)
            backup["registry"].pop(item.key, None)
            _save_backup(backup)
            return True, ""
        except OSError as exc:
            return False, f"Registry access denied ({exc.winerror})"
    original = backup["folder"].get(os.path.basename(item.file_path), {}).get("original")
    if not original:
        return False, "Missing backup data"
    try:
        if os.path.exists(item.file_path):
            shutil.move(item.file_path, original)
        backup["folder"].pop(os.path.basename(item.file_path), None)
        _save_backup(backup)
        return True, ""
    except Exception as exc:
        return False, str(exc)


def enabled_count() -> int:
    try:
        return sum(1 for item in list_startup() if item.enabled)
    except Exception:
        return 0
