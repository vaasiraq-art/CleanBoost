"""Safe deletion layer.

Deletion is only ever allowed inside a root that the scanner produced, and a
hard block-list stops anything system-critical even if a rule is misconfigured.
"""
from __future__ import annotations

import json
import os
import shutil
import stat
import time
from dataclasses import dataclass, field
from typing import Callable, Iterable

from . import scanner
from .utils import app_dir, is_within, normalize

# Deleting anything *inside* these is forbidden outright.
PROTECTED_ANYWHERE = [
    os.path.expandvars(r"%SystemRoot%\System32"),
    os.path.expandvars(r"%SystemRoot%\SysWOW64"),
    os.path.expandvars(r"%SystemRoot%\WinSxS"),
    os.path.expandvars(r"%SystemRoot%\Boot"),
    os.path.expandvars(r"%SystemRoot%\servicing"),
    os.path.expandvars(r"%ProgramFiles%"),
    os.path.expandvars(r"%ProgramFiles(x86)%"),
    os.path.expandvars(r"%SystemDrive%\Users\Public"),
    os.path.expandvars(r"%SystemDrive%\Recovery"),
    os.path.expandvars(r"%SystemDrive%\System Volume Information"),
]

# These may not be deleted themselves, nor may any of their parents be.
PROTECTED_ROOTS = [
    os.path.expandvars(r"%SystemRoot%"),
    os.path.expandvars(r"%ProgramData%\Microsoft\Windows\Start Menu"),
    os.path.expandvars(r"%SystemDrive%\Users"),
    os.path.expandvars(r"%SystemDrive%\PerfLogs"),
]


def _protected() -> list[str]:
    paths = list(PROTECTED_ROOTS)
    profile = os.environ.get("USERPROFILE")
    if profile:
        paths.extend(
            [
                profile,
                os.path.join(profile, "Documents"),
                os.path.join(profile, "Desktop"),
                os.path.join(profile, "Pictures"),
                os.path.join(profile, "Music"),
                os.path.join(profile, "Videos"),
                os.path.join(profile, "OneDrive"),
                os.path.join(profile, "AppData"),
            ]
        )
    return [normalize(p) for p in paths]


PROTECTED = _protected()
PROTECTED_DEEP = [normalize(p) for p in PROTECTED_ANYWHERE if p]


def is_protected(path: str) -> bool:
    target = normalize(path)
    # a drive root (C:\) is always protected
    if len(target) <= 3:
        return True
    for guarded in PROTECTED_DEEP:
        if target == guarded or target.startswith(guarded + os.sep):
            return True
    for guarded in PROTECTED:
        if target == guarded:
            return True
        # path is an ancestor of a protected folder
        if guarded.startswith(target + os.sep):
            return True
    return False


def can_delete(path: str, roots: Iterable[str]) -> bool:
    if not path or is_protected(path):
        return False
    return any(is_within(path, root) for root in roots if root)


# --------------------------------------------------------------------------- #
# Primitive delete
# --------------------------------------------------------------------------- #


def _on_rm_error(func, path, exc_info):  # pragma: no cover - OS dependent
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        pass


def _remove_file(path: str) -> bool:
    try:
        os.remove(path)
        return True
    except PermissionError:
        try:
            os.chmod(path, stat.S_IWRITE)
            os.remove(path)
            return True
        except Exception:
            return False
    except OSError:
        return False


def _remove_dir(path: str) -> bool:
    try:
        shutil.rmtree(path, onerror=_on_rm_error)
        return True
    except Exception:
        return False


def delete_entry(entry: scanner.Entry, roots: Iterable[str]) -> tuple[bool, int]:
    """Delete one entry. Returns (success, bytes_actually_freed)."""
    if not can_delete(entry.path, roots):
        return False, 0
    if os.path.islink(entry.path) or os.path.isfile(entry.path):
        ok = _remove_file(entry.path)
        return ok, entry.size if ok else 0
    if os.path.isdir(entry.path):
        ok = _remove_dir(entry.path)
        if ok:
            return True, entry.size
        # partial removal: report what actually vanished
        return False, 0
    return False, 0


# --------------------------------------------------------------------------- #
# High level jobs
# --------------------------------------------------------------------------- #


@dataclass
class CleanReport:
    freed: int = 0
    deleted: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)
    duration: float = 0.0
    targets: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "freed": self.freed,
            "deleted": self.deleted,
            "skipped": self.skipped,
            "failed": self.failed,
            "duration": round(self.duration, 1),
            "targets": self.targets,
            "when": time.time(),
        }


def clean_results(
    results: Iterable[scanner.TargetResult],
    cancel=None,
    on_progress: Callable[[str, int, int], None] | None = None,
) -> CleanReport:
    """Delete every entry of every result. Reports partial success honestly."""
    report = CleanReport()
    started = time.time()
    all_entries: list[tuple[scanner.TargetResult, scanner.Entry, list[str]]] = []
    for result in results:
        report.targets.append(result.target.key)
        if result.target.action == "recyclebin":
            if result.total > 0:
                ok, message = scanner.empty_recycle_bin()
                if ok:
                    report.freed += result.total
                    report.deleted += result.count
                else:
                    report.failed += 1
                    if message:
                        report.errors.append(message)
            continue
        roots = [entry.root for entry in result.entries if entry.root]
        if not roots:
            roots = [d for raw in result.target.roots for d in scanner._expand_roots(raw)]
        for entry in result.entries:
            all_entries.append((result, entry, roots))

    total = len(all_entries)
    for index, (result, entry, roots) in enumerate(all_entries, start=1):
        if cancel is not None and cancel.is_set():
            report.skipped += total - index + 1
            break
        ok, freed = delete_entry(entry, roots)
        if ok:
            report.freed += freed
            report.deleted += 1
        else:
            if os.path.exists(entry.path):
                report.failed += 1
                if len(report.errors) < 8:
                    report.errors.append(entry.path)
            else:
                report.deleted += 1
        if on_progress and (index % 25 == 0 or index == total):
            on_progress(entry.path, index, total)

    report.duration = time.time() - started
    _log(report)
    return report


def clean_targets(
    targets: Iterable[scanner.Target],
    cancel=None,
    on_progress: Callable[[str, int, int], None] | None = None,
) -> CleanReport:
    results = scanner.scan(targets, cancel)
    return clean_results(list(results.values()), cancel, on_progress)


# --------------------------------------------------------------------------- #
# History / log
# --------------------------------------------------------------------------- #

HISTORY_FILE = "history.json"


def _log(report: CleanReport) -> None:
    try:
        path = app_dir() / HISTORY_FILE
        history: list[dict] = []
        if path.exists():
            try:
                history = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(history, list):
                    history = []
            except Exception:
                history = []
        history.insert(0, report.as_dict())
        path.write_text(json.dumps(history[:25], indent=2), encoding="utf-8")
    except Exception:
        pass


def history() -> list[dict]:
    try:
        path = app_dir() / HISTORY_FILE
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def last_clean() -> dict | None:
    items = history()
    return items[0] if items else None
