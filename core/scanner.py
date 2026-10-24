"""Junk detection engine.

Every location here is an explicit allow-list. Nothing outside a target's
declared root can ever be returned, which the cleaner re-checks before
deleting anything.
"""
from __future__ import annotations

import ctypes
import fnmatch
import glob
import os
import time
from dataclasses import dataclass, field
from typing import Callable, Iterable

from .utils import human_size, is_reparse

FILE_ATTRIBUTE_REPARSE_POINT = 0x400
MAX_ENTRIES_PER_TARGET = 60_000


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #


@dataclass
class Entry:
    path: str
    size: int
    mtime: float
    is_dir: bool = False
    root: str = ""


@dataclass
class Target:
    key: str
    title: str
    subtitle: str
    category: str = "Everyday"
    risk: str = "safe"  # safe | caution | review
    action: str = "delete"  # delete | recyclebin
    roots: tuple[str, ...] = ()
    patterns: tuple[str, ...] = ()
    min_age_days: float = 0.0
    needs_admin: bool = False
    default_on: bool = True
    collect_fn: Callable[[object], list[Entry]] | None = None
    note: str = ""

    def hint(self) -> str:
        bits = [self.subtitle]
        if self.needs_admin:
            bits.append("admin")
        if self.min_age_days:
            bits.append(f"older than {int(self.min_age_days)} days")
        return "  ·  ".join(b for b in bits if b)


@dataclass
class TargetResult:
    target: Target
    entries: list[Entry] = field(default_factory=list)
    error: str | None = None

    @property
    def total(self) -> int:
        return sum(e.size for e in self.entries)

    @property
    def count(self) -> int:
        return len(self.entries)


# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #


def _env_path(*parts: str) -> str:
    base = os.path.expandvars(parts[0])
    return os.path.join(base, *parts[1:]) if len(parts) > 1 else base


def _loc(*parts: str) -> str:
    return _env_path("%LOCALAPPDATA%", *parts)


def _roam(*parts: str) -> str:
    return _env_path("%APPDATA%", *parts)


def _common(*parts: str) -> str:
    return _env_path("%ProgramData%", *parts)


def _win(*parts: str) -> str:
    return _env_path("%SystemRoot%", *parts)


def _user(*parts: str) -> str:
    return _env_path("%USERPROFILE%", *parts)


def _drive(*parts: str) -> str:
    return _env_path("%SystemDrive%\\", *parts)


# --------------------------------------------------------------------------- #
# Low level scanning
# --------------------------------------------------------------------------- #


def _dir_size(path: str, cancel=None) -> int:
    total = 0
    stack = [path]
    while stack:
        if cancel is not None and cancel.is_set():
            return total
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                for node in it:
                    try:
                        if node.is_dir(follow_symlinks=False):
                            if is_reparse(node.path):
                                continue
                            stack.append(node.path)
                        elif node.is_file(follow_symlinks=False):
                            total += node.stat(follow_symlinks=False).st_size
                    except OSError:
                        continue
        except OSError:
            continue
    return total


def _expand_roots(pattern: str) -> list[str]:
    pattern = os.path.expandvars(os.path.expanduser(pattern))
    if any(ch in pattern for ch in "*?["):
        return sorted(glob.glob(pattern))
    return [pattern]


def _match(name: str, patterns: tuple[str, ...]) -> bool:
    low = name.lower()
    return any(fnmatch.fnmatch(low, pat.lower()) for pat in patterns)


def _scan_root(root: str, target: Target, cancel=None) -> list[Entry]:
    """Return one Entry per direct child of `root` (recursive sizes)."""
    entries: list[Entry] = []
    cutoff = time.time() - target.min_age_days * 86400 if target.min_age_days else 0
    try:
        with os.scandir(root) as it:
            for node in it:
                if cancel is not None and cancel.is_set():
                    break
                try:
                    name = node.name
                    if name.lower() in {"desktop.ini", "thumbs.db", ".ds_store"}:
                        continue
                    is_dir = node.is_dir(follow_symlinks=False)
                    if not is_dir and target.patterns and not _match(name, target.patterns):
                        continue
                    stat = node.stat(follow_symlinks=False)
                    if cutoff and stat.st_mtime > cutoff:
                        continue
                    size = _dir_size(node.path, cancel) if is_dir else int(stat.st_size)
                    if size <= 0 and is_dir:
                        continue
                    entries.append(
                        Entry(
                            path=node.path,
                            size=size,
                            mtime=stat.st_mtime,
                            is_dir=is_dir,
                            root=root,
                        )
                    )
                except OSError:
                    continue
    except OSError:
        pass
    return entries


def collect(target: Target, cancel=None) -> TargetResult:
    result = TargetResult(target=target)
    if cancel is not None and cancel.is_set():
        return result
    try:
        if target.collect_fn is not None:
            result.entries = target.collect_fn(cancel)
            return result

        seen: set[str] = set()
        for raw in target.roots:
            for root in _expand_roots(raw):
                if os.path.isfile(root):
                    try:
                        st = os.stat(root, follow_symlinks=False)
                        if not target.min_age_days or st.st_mtime <= time.time() - target.min_age_days * 86400:
                            result.entries.append(
                                Entry(root, int(st.st_size), st.st_mtime, False, os.path.dirname(root))
                            )
                    except OSError:
                        pass
                    continue
                if not os.path.isdir(root):
                    continue
                key = os.path.normcase(root)
                if key in seen:
                    continue
                seen.add(key)
                result.entries.extend(_scan_root(root, target, cancel))
                if len(result.entries) > MAX_ENTRIES_PER_TARGET:
                    break
    except Exception as exc:  # pragma: no cover - defensive
        result.error = str(exc)
    return result


# --------------------------------------------------------------------------- #
# Recycle bin
# --------------------------------------------------------------------------- #


class SHQUERYRBINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_uint32),
        ("i64Size", ctypes.c_longlong),
        ("i64NumItems", ctypes.c_longlong),
    ]


def recycle_bin_info() -> tuple[int, int]:
    try:
        info = SHQUERYRBINFO()
        info.cbSize = ctypes.sizeof(SHQUERYRBINFO)
        rc = ctypes.windll.shell32.SHQueryRecycleBinW(None, ctypes.byref(info))
        if rc == 0:
            return max(0, int(info.i64Size)), max(0, int(info.i64NumItems))
    except Exception:
        pass
    return 0, 0


def _collect_recycle_bin(cancel=None) -> list[Entry]:
    size, count = recycle_bin_info()
    if size <= 0:
        return []
    return [Entry("Recycle Bin", size, time.time(), True, "")]


def empty_recycle_bin() -> tuple[bool, str]:
    flags = 0x1 | 0x2 | 0x4  # no confirmation, no progress UI, no sound
    try:
        rc = ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, flags)
        return rc in (0, -2147418113), ""
    except Exception as exc:
        return False, str(exc)


# --------------------------------------------------------------------------- #
# Browser caches
# --------------------------------------------------------------------------- #

CHROMIUM_PROFILES = [
    ("Chrome", _loc("Google", "Chrome", "User Data")),
    ("Edge", _loc("Microsoft", "Edge", "User Data")),
    ("Brave", _loc("BraveSoftware", "Brave-Browser", "User Data")),
    ("Vivaldi", _loc("Vivaldi", "User Data")),
    ("Opera", _loc("Opera Software", "Opera Stable")),
    ("Opera GX", _loc("Opera Software", "Opera GX Stable")),
]

CHROMIUM_SUBDIRS = (
    "Cache",
    "Code Cache",
    "GPUCache",
    "DawnGraphiteCache",
    "DawnWebGPUCache",
    os.path.join("Service Worker", "CacheStorage"),
    os.path.join("Service Worker", "ScriptCache"),
)

CHROMIUM_ROOT_CACHE = ("ShaderCache", "GrShaderCache", "GraphiteDawnCache")


def _collect_browser_caches(cancel=None) -> list[Entry]:
    entries: list[Entry] = []
    seen: set[str] = set()

    def add(path: str, root: str) -> None:
        key = os.path.normcase(path)
        if key in seen or not os.path.isdir(path):
            return
        seen.add(key)
        size = _dir_size(path, cancel)
        if size > 0:
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                mtime = 0.0
            entries.append(Entry(path, size, mtime, True, root))

    for _brand, base in CHROMIUM_PROFILES:
        if not os.path.isdir(base):
            continue
        for cache in CHROMIUM_ROOT_CACHE:
            add(os.path.join(base, cache), base)
        try:
            with os.scandir(base) as it:
                children = [n for n in it if n.is_dir(follow_symlinks=False)]
        except OSError:
            continue
        for child in children:
            if child.name.lower() in {"crashpad", "browsermetrics", "snapshots", "system profile"}:
                continue
            for sub in CHROMIUM_SUBDIRS:
                add(os.path.join(child.path, sub), base)

    # Firefox
    ff_cache = _loc("Mozilla", "Firefox", "Profiles")
    if os.path.isdir(ff_cache):
        try:
            with os.scandir(ff_cache) as it:
                profiles = [n for n in it if n.is_dir(follow_symlinks=False)]
        except OSError:
            profiles = []
        for profile in profiles:
            add(os.path.join(profile.path, "cache2"), ff_cache)
            add(os.path.join(profile.path, "startupCache"), ff_cache)

    return entries


# --------------------------------------------------------------------------- #
# Leftover app data (heuristic, review-only)
# --------------------------------------------------------------------------- #

LEFTOVER_EXCLUDES = {
    "microsoft",
    "packages",
    "temp",
    "programs",
    "connecteddevicesplatform",
    "comms",
    "virtualstore",
    "placeholderviews",
    "history",
    "tilelayerscache",
    "pmodata",
    "crashdumps",
    "d3dscache",
    "nvidia",
    "intel",
    "amd",
    "google",
    "mozilla",
    "adobe",
    "packages",
    "application data",
    "desktop",
    "documents",
    "downloads",
    "links",
    "favorites",
    "start menu",
    "templates",
    "netcache",
    "onedrivetemp",
    "elevateddiagnostics",
    "publisher",
    "microsoft corporation",
}


def _normalize_name(name: str) -> str:
    return "".join(ch for ch in name.lower() if ch.isalnum())


def installed_apps() -> tuple[set[str], set[str]]:
    """Return (normalized display names, normalized install-folder names)."""
    import winreg

    names: set[str] = set()
    installs: set[str] = set()
    roots = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    for hive, path in roots:
        try:
            with winreg.OpenKey(hive, path) as key:
                for index in range(winreg.QueryInfoKey(key)[0]):
                    try:
                        sub_name = winreg.EnumKey(key, index)
                        with winreg.OpenKey(key, sub_name) as sub:
                            try:
                                display, _ = winreg.QueryValueEx(sub, "DisplayName")
                                if display:
                                    names.add(_normalize_name(str(display)))
                            except OSError:
                                pass
                            try:
                                location, _ = winreg.QueryValueEx(sub, "InstallLocation")
                                if location:
                                    base = os.path.basename(str(location).rstrip("\\/"))
                                    if base:
                                        installs.add(_normalize_name(base))
                            except OSError:
                                pass
                    except OSError:
                        continue
        except OSError:
            continue
    return names, installs


def _collect_leftovers(cancel=None) -> list[Entry]:
    apps, installs = installed_apps()
    entries: list[Entry] = []
    cutoff = time.time() - 180 * 86400
    roots = [_loc(), _roam()]
    for root in roots:
        if not os.path.isdir(root):
            continue
        try:
            with os.scandir(root) as it:
                children = [n for n in it if n.is_dir(follow_symlinks=False)]
        except OSError:
            continue
        for child in children:
            if cancel is not None and cancel.is_set():
                return entries
            name = child.name
            normalized = _normalize_name(name)
            if not normalized or normalized in LEFTOVER_EXCLUDES:
                continue
            if "microsoft" in normalized or normalized.startswith("{"):
                continue
            matched = False
            for app in apps:
                if len(app) < 4:
                    continue
                if normalized in app or app in normalized:
                    matched = True
                    break
            if not matched:
                for install in installs:
                    if len(install) < 4:
                        continue
                    if normalized in install or install in normalized:
                        matched = True
                        break
            if matched:
                continue
            try:
                if child.stat(follow_symlinks=False).st_mtime > cutoff:
                    continue
            except OSError:
                continue
            size = _dir_size(child.path, cancel)
            if size < 100 * 1024 * 1024:
                continue
            try:
                mtime = child.stat(follow_symlinks=False).st_mtime
            except OSError:
                mtime = 0.0
            entries.append(Entry(child.path, size, mtime, True, root))
    entries.sort(key=lambda e: e.size, reverse=True)
    return entries[:80]


# --------------------------------------------------------------------------- #
# The target registry
# --------------------------------------------------------------------------- #

TARGETS: list[Target] = [
    # ---------------- everyday, no admin ----------------
    Target(
        key="user_temp",
        title="Temporary files",
        subtitle="Scratch files left by installers, updates and apps",
        category="Everyday",
        risk="safe",
        roots=("%TEMP%", r"%LOCALAPPDATA%\Temp"),
        min_age_days=0.5,
        default_on=True,
    ),
    Target(
        key="browser_cache",
        title="Browser caches",
        subtitle="Chrome / Edge / Brave / Firefox page and shader caches",
        category="Everyday",
        risk="caution",
        collect_fn=_collect_browser_caches,
        default_on=False,
        note="Close your browsers first so locked files are not skipped.",
    ),
    Target(
        key="thumbnails",
        title="Thumbnail & icon cache",
        subtitle="Explorer previews that Windows rebuilds automatically",
        category="Everyday",
        risk="safe",
        roots=(r"%LOCALAPPDATA%\Microsoft\Windows\Explorer",),
        patterns=("thumbcache_*.db", "iconcache_*.db"),
        default_on=True,
    ),
    Target(
        key="shader_cache",
        title="GPU shader caches",
        subtitle="DirectX and NVIDIA compiled shader files",
        category="Everyday",
        risk="safe",
        roots=(
            r"%LOCALAPPDATA%\D3DSCache",
            r"%LOCALAPPDATA%\NVIDIA\DXCache",
            r"%LOCALAPPDATA%\NVIDIA\GLCache",
            r"%LOCALAPPDATA%\AMD\DxCache",
        ),
        default_on=True,
    ),
    Target(
        key="crash_dumps",
        title="Crash dumps",
        subtitle="Memory dumps written when an app crashed",
        category="Everyday",
        risk="safe",
        roots=(r"%LOCALAPPDATA%\CrashDumps",),
        default_on=True,
    ),
    Target(
        key="wer_reports",
        title="Error reporting queues",
        subtitle="Windows Error Reporting archives and temp copies",
        category="Everyday",
        risk="safe",
        roots=(
            r"%LOCALAPPDATA%\Microsoft\Windows\WER",
            r"%PROGRAMDATA%\Microsoft\Windows\WER",
        ),
        default_on=True,
    ),
    Target(
        key="old_installers",
        title="Old installers in Downloads",
        subtitle="Setup files you already installed (30+ days old)",
        category="Everyday",
        risk="review",
        roots=(r"%USERPROFILE%\Downloads",),
        patterns=("*.exe", "*.msi", "*.msix", "*.appx", "*.iso", "*.zip", "*.7z", "*.rar"),
        min_age_days=30,
        default_on=False,
        note="Review this list before deleting — some installers are worth keeping.",
    ),
    # ---------------- system ----------------
    Target(
        key="win_temp",
        title="Windows temporary files",
        subtitle="System-wide temp folder used by services",
        category="System",
        risk="safe",
        roots=(r"%WINDIR%\Temp",),
        min_age_days=0.5,
        needs_admin=True,
        default_on=True,
    ),
    Target(
        key="recycle_bin",
        title="Recycle Bin",
        subtitle="Deleted files still occupying disk space",
        category="System",
        risk="safe",
        action="recyclebin",
        collect_fn=_collect_recycle_bin,
        default_on=True,
    ),
    Target(
        key="delivery_optimization",
        title="Delivery Optimization cache",
        subtitle="Windows Update peer-to-peer download cache",
        category="System",
        risk="safe",
        roots=(
            r"%WINDIR%\SoftwareDistribution\DeliveryOptimization",
            r"%WINDIR%\ServiceProfiles\NetworkService\AppData\Local\Microsoft\Windows\DeliveryOptimization",
        ),
        needs_admin=True,
        default_on=True,
    ),
    Target(
        key="prefetch",
        title="Prefetch data",
        subtitle="Boot traces Windows rebuilds after a restart or two",
        category="System",
        risk="caution",
        roots=(r"%WINDIR%\Prefetch",),
        needs_admin=True,
        default_on=False,
    ),
    Target(
        key="win_update_cache",
        title="Windows Update cache",
        subtitle="Already-installed update packages",
        category="System",
        risk="caution",
        roots=(r"%WINDIR%\SoftwareDistribution\Download",),
        needs_admin=True,
        default_on=False,
        note="Stop Windows Update first if the files stay locked.",
    ),
    Target(
        key="win_logs",
        title="Windows log files",
        subtitle="CBS, DISM and update logs",
        category="System",
        risk="caution",
        roots=(
            r"%WINDIR%\Logs\CBS",
            r"%WINDIR%\Logs\DISM",
            r"%WINDIR%\Logs\WindowsUpdate",
            r"%WINDIR%\Logs\MoSetup",
        ),
        needs_admin=True,
        default_on=False,
    ),
    Target(
        key="panther",
        title="Setup & upgrade logs",
        subtitle="Leftover Windows setup traces",
        category="System",
        risk="caution",
        roots=(r"%WINDIR%\Panther", r"%WINDIR%\Panther\UnattendGC"),
        needs_admin=True,
        default_on=False,
    ),
    Target(
        key="memory_dumps",
        title="System memory dumps",
        subtitle="Blue-screen dumps kept for debugging",
        category="System",
        risk="caution",
        roots=(r"%WINDIR%\Minidump", r"%WINDIR%\LiveKernelReports"),
        patterns=("*.dmp",),
        needs_admin=True,
        default_on=False,
    ),
    Target(
        key="windows_old",
        title="Previous Windows installation",
        subtitle="C:\\Windows.old from an upgrade — often many GB",
        category="System",
        risk="review",
        roots=(_drive("Windows.old"),),
        needs_admin=True,
        default_on=False,
        note="You lose the ability to roll back to the previous Windows version.",
    ),
    Target(
        key="upgrade_leftovers",
        title="Windows upgrade leftovers",
        subtitle="$WINDOWS.~BT / ~WS / $GetCurrent folders",
        category="System",
        risk="review",
        roots=(
            _drive("$WINDOWS.~BT"),
            _drive("$WINDOWS.~WS"),
            _drive("$GetCurrent"),
            _drive("$SysReset"),
        ),
        needs_admin=True,
        default_on=False,
    ),
    # ---------------- review ----------------
    Target(
        key="leftovers",
        title="Leftover app data",
        subtitle="Folders in AppData with no matching installed app",
        category="Review",
        risk="review",
        collect_fn=_collect_leftovers,
        default_on=False,
        note="Heuristic guess. Check every item before deleting — some apps keep settings here.",
    ),
]

TARGET_BY_KEY = {t.key: t for t in TARGETS}
CATEGORY_ORDER = ["Everyday", "System", "Review"]


def scan(
    targets: Iterable[Target] | None = None,
    cancel=None,
    on_target: Callable[[Target, TargetResult], None] | None = None,
) -> dict[str, TargetResult]:
    """Scan the given targets (all by default). Returns key -> result."""
    results: dict[str, TargetResult] = {}
    for target in targets if targets is not None else TARGETS:
        if cancel is not None and cancel.is_set():
            break
        result = collect(target, cancel)
        results[target.key] = result
        if on_target:
            try:
                on_target(target, result)
            except Exception:
                pass
    return results


# --------------------------------------------------------------------------- #
# Space analysis
# --------------------------------------------------------------------------- #


def find_large_files(
    roots: Iterable[str],
    min_bytes: int = 250 * 1024 * 1024,
    cancel=None,
    limit: int = 300,
) -> list[Entry]:
    found: list[Entry] = []
    for raw in roots:
        for root in _expand_roots(raw):
            if not os.path.isdir(root):
                continue
            stack = [root]
            while stack:
                if cancel is not None and cancel.is_set():
                    break
                current = stack.pop()
                try:
                    with os.scandir(current) as it:
                        for node in it:
                            try:
                                if node.is_dir(follow_symlinks=False):
                                    if is_reparse(node.path):
                                        continue
                                    # skip Windows component store (huge, never useful here)
                                    if os.path.normcase(node.path) == os.path.normcase(_win("WinSxS")):
                                        continue
                                    stack.append(node.path)
                                elif node.is_file(follow_symlinks=False):
                                    stat = node.stat(follow_symlinks=False)
                                    if stat.st_size >= min_bytes:
                                        found.append(
                                            Entry(node.path, int(stat.st_size), stat.st_mtime, False, root)
                                        )
                            except OSError:
                                continue
                except OSError:
                    continue
    found.sort(key=lambda e: e.size, reverse=True)
    return found[:limit]


def folder_breakdown(roots: Iterable[str], cancel=None) -> list[Entry]:
    """One row per direct child folder, recursive size, largest first."""
    rows: list[Entry] = []
    for raw in roots:
        for root in _expand_roots(raw):
            if not os.path.isdir(root):
                continue
            try:
                with os.scandir(root) as it:
                    children = [n for n in it if n.is_dir(follow_symlinks=False)]
            except OSError:
                continue
            for child in children:
                if cancel is not None and cancel.is_set():
                    return rows
                if is_reparse(child.path):
                    continue
                size = _dir_size(child.path, cancel)
                if size <= 0:
                    continue
                try:
                    mtime = child.stat(follow_symlinks=False).st_mtime
                except OSError:
                    mtime = 0.0
                rows.append(Entry(child.path, size, mtime, True, root))
    rows.sort(key=lambda e: e.size, reverse=True)
    return rows


def big_junk_summary(results: dict[str, TargetResult]) -> tuple[int, int]:
    total = sum(r.total for r in results.values())
    count = sum(r.count for r in results.values())
    return total, count


def describe(result: TargetResult) -> str:
    return f"{human_size(result.total)} in {result.count} items"
