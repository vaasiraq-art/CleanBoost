"""Shared helpers: sizes, paths, elevation and shell integration."""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

APP_NAME = "CleanBoost"
APP_VERSION = "1.1.0"
APP_TAGLINE = "Clean. Speed up. Take your space back."

# --------------------------------------------------------------------------- #
# Paths / formatting
# --------------------------------------------------------------------------- #


def app_dir() -> Path:
    """Per-user writable folder for config, logs and startup backups."""
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    path = Path(base) / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def human_size(value: float | int | None) -> str:
    """476382 -> '465.2 MB'."""
    size = float(value or 0)
    if size < 1024:
        return f"{int(size)} B"
    for unit in ("KB", "MB", "GB", "TB"):
        size /= 1024.0
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}"
    return f"{size:.1f} TB"


def human_count(value: int) -> str:
    value = int(value or 0)
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}K"
    return str(value)


def human_age(mtime: float) -> str:
    if not mtime:
        return "-"
    days = max(0, int((time.time() - mtime) / 86400))
    if days == 0:
        return "today"
    if days == 1:
        return "yesterday"
    if days < 30:
        return f"{days} days ago"
    if days < 365:
        return f"{days // 30} mo ago"
    return f"{days // 365} yr ago"


def format_time(ts: float | None = None) -> str:
    return time.strftime("%d %b %Y, %H:%M", time.localtime(ts or time.time()))


def expand(path: str) -> str:
    return os.path.expandvars(os.path.expanduser(path))


def exists(path: str) -> bool:
    try:
        return os.path.exists(path)
    except (OSError, ValueError):
        return False


def is_reparse(path: str) -> bool:
    """True for junctions / symlinks / OneDrive placeholders (never recurse)."""
    try:
        st = os.stat(path, follow_symlinks=False)
    except OSError:
        return True
    return bool(getattr(st, "st_file_attributes", 0) & 0x400)


# --------------------------------------------------------------------------- #
# Elevation
# --------------------------------------------------------------------------- #


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin() -> bool:
    """Start a second, elevated copy of the app. Returns True on success."""
    if is_admin():
        return True
    if getattr(sys, "frozen", False):
        exe = sys.executable
        args = sys.argv[1:]
    else:
        exe = sys.executable
        args = [os.path.abspath(sys.argv[0]), *sys.argv[1:]]
    params = subprocess.list2cmdline(args)
    try:
        rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, None, 1)
        return int(rc) > 32
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# Shell helpers
# --------------------------------------------------------------------------- #


def open_path(path: str) -> None:
    try:
        os.startfile(path)  # noqa: S606 - intentional shell open
    except Exception:
        reveal_path(path)


def reveal_path(path: str) -> None:
    try:
        if os.path.isdir(path):
            subprocess.Popen(["explorer", os.path.normpath(path)])
        else:
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
    except Exception:
        pass


def run_hidden(args: list[str] | str, timeout: int = 30) -> tuple[int, str]:
    """Run a console command without flashing a window."""
    if isinstance(args, str):
        args = [args]
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 0
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except Exception as exc:  # pragma: no cover - defensive
        return 1, str(exc)


# --------------------------------------------------------------------------- #
# Recycle bin (safe delete for personal files)
# --------------------------------------------------------------------------- #

FO_DELETE = 3
FOF_SILENT = 0x0004
FOF_NOCONFIRMATION = 0x0010
FOF_ALLOWUNDO = 0x0040
FOF_NOERRORUI = 0x0400


class SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("wFunc", wintypes.UINT),
        ("pFrom", wintypes.LPCWSTR),
        ("pTo", wintypes.LPCWSTR),
        ("fFlags", ctypes.c_uint16),
        ("fAnyOperationsAborted", wintypes.BOOL),
        ("hNameMappings", ctypes.c_void_p),
        ("lpszProgressTitle", wintypes.LPCWSTR),
    ]


def recycle_paths(paths: list[str]) -> tuple[int, int]:
    """Move files to the Recycle Bin. Returns (ok, failed)."""
    ok = failed = 0
    for path in paths:
        if not exists(path):
            continue
        try:
            op = SHFILEOPSTRUCTW()
            op.hwnd = None
            op.wFunc = FO_DELETE
            op.pFrom = os.path.abspath(path) + "\0\0"
            op.pTo = None
            op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI
            rc = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
            if rc == 0 and not op.fAnyOperationsAborted:
                ok += 1
            else:
                failed += 1
        except Exception:
            failed += 1
    return ok, failed


# --------------------------------------------------------------------------- #
# Misc
# --------------------------------------------------------------------------- #


def normalize(path: str) -> str:
    return os.path.normcase(os.path.normpath(os.path.abspath(path)))


def is_within(path: str, root: str) -> bool:
    """True when `path` lives inside `root` (but is not `root` itself)."""
    try:
        p = normalize(path)
        r = normalize(root)
        if p == r:
            return False
        return os.path.commonpath([p, r]) == r
    except (ValueError, OSError):
        return False


def enable_dpi_awareness() -> None:
    """Crisp text on high-DPI screens."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def app_icon_path() -> str:
    return str(Path(__file__).resolve().parent.parent / "assets" / "icon.ico")
