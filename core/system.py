"""Windows system information and maintenance actions (ctypes, no deps)."""
from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from dataclasses import dataclass

from .utils import run_hidden

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
psapi = ctypes.WinDLL("psapi", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)

# --------------------------------------------------------------------------- #
# Memory
# --------------------------------------------------------------------------- #


class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", wintypes.DWORD),
        ("dwMemoryLoad", wintypes.DWORD),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def memory_info() -> dict[str, float]:
    stat = MEMORYSTATUSEX()
    stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    if not kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
        return {"total": 0, "used": 0, "free": 0, "percent": 0}
    total = float(stat.ullTotalPhys)
    free = float(stat.ullAvailPhys)
    used = max(0.0, total - free)
    return {
        "total": total,
        "used": used,
        "free": free,
        "percent": (used / total * 100.0) if total else 0.0,
    }


# --------------------------------------------------------------------------- #
# Drives
# --------------------------------------------------------------------------- #

DRIVE_TYPES = {
    0: "Unknown",
    1: "Invalid",
    2: "Removable",
    3: "Fixed",
    4: "Network",
    5: "CD-ROM",
    6: "RAM disk",
}


@dataclass
class DriveInfo:
    letter: str
    total: int
    free: int
    used: int
    kind: str
    label: str = ""

    @property
    def percent(self) -> float:
        return (self.used / self.total * 100.0) if self.total else 0.0


def _volume_label(root: str) -> str:
    name_buf = ctypes.create_unicode_buffer(261)
    fs_buf = ctypes.create_unicode_buffer(261)
    serial = wintypes.DWORD()
    max_len = wintypes.DWORD()
    flags = wintypes.DWORD()
    try:
        ok = kernel32.GetVolumeInformationW(
            root,
            name_buf,
            261,
            ctypes.byref(serial),
            ctypes.byref(max_len),
            ctypes.byref(flags),
            fs_buf,
            261,
        )
        return name_buf.value if ok else ""
    except Exception:
        return ""


def drives(include_removable: bool = True) -> list[DriveInfo]:
    result: list[DriveInfo] = []
    mask = kernel32.GetLogicalDrives()
    for i in range(26):
        if not (mask >> i) & 1:
            continue
        root = f"{chr(65 + i)}:\\"
        kind_id = kernel32.GetDriveTypeW(root)
        if kind_id != 3 and not (include_removable and kind_id == 2):
            continue
        free = ctypes.c_ulonglong()
        total = ctypes.c_ulonglong()
        if not kernel32.GetDiskFreeSpaceExW(
            root, ctypes.byref(free), ctypes.byref(total), None
        ):
            continue
        total_i = int(total.value)
        free_i = int(free.value)
        result.append(
            DriveInfo(
                letter=chr(65 + i),
                total=total_i,
                free=free_i,
                used=max(0, total_i - free_i),
                kind=DRIVE_TYPES.get(kind_id, "Drive"),
                label=_volume_label(root),
            )
        )
    return result


def system_drive() -> DriveInfo | None:
    for drive in drives(False):
        if drive.letter.upper() == (os.environ.get("SystemDrive") or "C:").rstrip(":\\").upper():
            return drive
    fixed = drives(False)
    return fixed[0] if fixed else None


# --------------------------------------------------------------------------- #
# Processes
# --------------------------------------------------------------------------- #

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_TERMINATE = 0x0001
PROCESS_VM_READ = 0x0010


class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


@dataclass
class ProcessInfo:
    pid: int
    name: str
    memory: int
    exe: str = ""


def _process_name(handle: int) -> tuple[str, str]:
    buf = ctypes.create_unicode_buffer(1024)
    size = wintypes.DWORD(1024)
    try:
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            full = buf.value
            return os.path.basename(full), full
    except Exception:
        pass
    return "", ""


def top_processes(limit: int = 18) -> list[ProcessInfo]:
    """Processes sorted by working-set memory (descending)."""
    count = 2048
    while True:
        arr = (wintypes.DWORD * count)()
        needed = wintypes.DWORD()
        if not psapi.EnumProcesses(ctypes.byref(arr), ctypes.sizeof(arr), ctypes.byref(needed)):
            return []
        if needed.value < ctypes.sizeof(arr):
            break
        count *= 2

    total = needed.value // ctypes.sizeof(wintypes.DWORD)
    found: list[ProcessInfo] = []
    for i in range(total):
        pid = int(arr[i])
        if pid == 0:
            continue
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            continue
        try:
            counters = PROCESS_MEMORY_COUNTERS()
            counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
            if psapi.GetProcessMemoryInfo(
                handle, ctypes.byref(counters), counters.cb
            ):
                name, exe = _process_name(handle)
                if not name:
                    continue
                found.append(
                    ProcessInfo(pid=pid, name=name, memory=int(counters.WorkingSetSize), exe=exe)
                )
        except Exception:
            continue
        finally:
            kernel32.CloseHandle(handle)

    found.sort(key=lambda p: p.memory, reverse=True)
    return found[:limit]


def kill_process(pid: int) -> bool:
    handle = kernel32.OpenProcess(PROCESS_TERMINATE, False, int(pid))
    if not handle:
        return False
    try:
        return bool(kernel32.TerminateProcess(handle, 1))
    except Exception:
        return False
    finally:
        kernel32.CloseHandle(handle)


# --------------------------------------------------------------------------- #
# Windowed (foreground-capable) apps — used by Game Boost
# --------------------------------------------------------------------------- #

user32 = ctypes.WinDLL("user32", use_last_error=True)
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


@dataclass
class WindowedProcess:
    pid: int
    name: str
    title: str
    memory: int


def windowed_processes(limit: int = 40) -> list[WindowedProcess]:
    """Visible top-level windows, deduplicated by process."""
    found: dict[int, WindowedProcess] = {}
    own_pid = os.getpid()

    def callback(hwnd, _lparam):
        try:
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            title = buffer.value.strip()
            if not title:
                return True
            pid_value = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_value))
            pid = int(pid_value.value)
            if not pid or pid == own_pid or pid in found:
                return True
            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not handle:
                return True
            try:
                name, _exe = _process_name(handle)
                counters = PROCESS_MEMORY_COUNTERS()
                counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
                memory = 0
                if psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                    memory = int(counters.WorkingSetSize)
                if name:
                    found[pid] = WindowedProcess(pid=pid, name=name, title=title, memory=memory)
            finally:
                kernel32.CloseHandle(handle)
        except Exception:
            pass
        return True

    try:
        user32.EnumWindows(WNDENUMPROC(callback), 0)
    except Exception:
        return []
    items = sorted(found.values(), key=lambda p: p.memory, reverse=True)
    return items[:limit]


# --------------------------------------------------------------------------- #
# Maintenance actions
# --------------------------------------------------------------------------- #


def flush_dns() -> tuple[bool, str]:
    code, output = run_hidden(["ipconfig", "/flushdns"], timeout=20)
    return code == 0, output.strip()


def hibernation_size() -> int:
    path = os.path.join(os.environ.get("SystemDrive", "C:"), "hiberfil.sys")
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def disable_hibernation() -> tuple[bool, str]:
    code, output = run_hidden(["powercfg", "/h", "off"], timeout=30)
    return code == 0, output.strip()


def enable_hibernation() -> tuple[bool, str]:
    code, output = run_hidden(["powercfg", "/h", "on"], timeout=30)
    return code == 0, output.strip()


def hibernation_enabled() -> bool:
    code, output = run_hidden(["powercfg", "/a"], timeout=20)
    text = output.lower()
    return code == 0 and "hibernate" in text and "not been enabled" not in text


POWER_PLANS = {
    "High performance": "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c",
    "Balanced": "381b4222-f694-41f0-9685-ff5bb260df2e",
    "Power saver": "a1841308-3541-4fab-bc81-f71556f20b4a",
}


def set_power_plan(name: str) -> tuple[bool, str]:
    guid = POWER_PLANS.get(name)
    if not guid:
        return False, "Unknown power plan"
    code, output = run_hidden(["powercfg", "/s", guid], timeout=20)
    return code == 0, output.strip()


def open_windows_tool(tool: str) -> None:
    commands = {
        "disk_cleanup": ["cleanmgr"],
        "storage": ["cmd", "/c", "start", "ms-settings:storagesense"],
        "task_manager": ["taskmgr"],
        "startup_settings": ["cmd", "/c", "start", "ms-settings:startupapps"],
        "installed_apps": ["cmd", "/c", "start", "ms-settings:appsfeatures"],
        "windows_update": ["cmd", "/c", "start", "ms-settings:windowsupdate"],
    }
    args = commands.get(tool)
    if not args:
        return
    try:
        import subprocess

        subprocess.Popen(args, creationflags=subprocess.CREATE_NO_WINDOW)
    except Exception:
        pass


def os_caption() -> str:
    try:
        return f"{os.environ.get('OS', 'Windows')} (build {os.environ.get('OS_BUILD', '')})".strip()
    except Exception:
        return "Windows"
