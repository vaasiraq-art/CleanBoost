"""Offline self-test for the CleanBoost engine (no UI, no destructive surprises)."""
from __future__ import annotations

import os
import sys
import tempfile
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import cleaner, dupes, scanner, startup, system  # noqa: E402
from core.utils import human_size, is_admin  # noqa: E402

failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        failures.append(name)


def make_sandbox() -> str:
    root = os.path.join(tempfile.gettempdir(), "cleanboost_selftest")
    if os.path.isdir(root):
        import shutil

        shutil.rmtree(root, ignore_errors=True)
    os.makedirs(os.path.join(root, "nested", "deep"))
    files = {
        "a.tmp": 1200,
        "b.log": 3400,
        os.path.join("nested", "c.bin"): 8000,
        os.path.join("nested", "deep", "d.bin"): 15000,
    }
    for name, size in files.items():
        path = os.path.join(root, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(b"x" * size)
    return root


def main() -> int:
    print("CleanBoost self-test")
    print(f"  admin={is_admin()}  python={sys.version.split()[0]}")
    print(f"  windows={system.os_caption()}")

    print("\n[formatting]")
    check("human_size(0)", human_size(0) == "0 B", human_size(0))
    check("human_size(1024)", human_size(1024) == "1.0 KB", human_size(1024))
    check("human_size(1536)", human_size(1536) == "1.5 KB", human_size(1536))
    check("human_size(5GB)", "GB" in human_size(5 * 1024**3))

    print("\n[scan + clean sandbox]")
    root = make_sandbox()
    target = scanner.Target(
        key="sandbox",
        title="Sandbox",
        subtitle="self test",
        roots=(root,),
        min_age_days=0,
        default_on=False,
    )
    result = scanner.collect(target)
    check("entry count == 3", result.count == 3, str([e.path for e in result.entries]))
    check("total size", result.total == 1200 + 3400 + 8000 + 15000, str(result.total))

    report = cleaner.clean_results([result])
    check("files removed", report.deleted == 3, str(report.deleted))
    check("sandbox root survived", os.path.isdir(root), "root should not be deleted")
    check("sandbox empty", os.listdir(root) == [], str(os.listdir(root)))
    check("no failures", report.failed == 0, str(report.errors))

    print("\n[protection]")
    check(
        "system32 blocked",
        not cleaner.can_delete(r"C:\Windows\System32\drivers\etc\hosts", [r"C:\Windows\System32\drivers\etc"]),
    )
    check("windows dir blocked", not cleaner.can_delete(r"C:\Windows", ["C:\\"]))
    check("drive root blocked", not cleaner.can_delete("C:\\", ["C:\\"]))
    check("outside root blocked", not cleaner.can_delete(os.path.join(root, "x"), [r"D:\Other"]))
    check("inside root allowed", cleaner.can_delete(os.path.join(root, "x"), [root]))

    print("\n[duplicates]")
    dup_root = os.path.join(tempfile.gettempdir(), "cleanboost_dupes")
    os.makedirs(dup_root, exist_ok=True)
    payload = b"same-bytes" * 5000
    for name in ("one.bin", "two.bin", "three.bin"):
        with open(os.path.join(dup_root, name), "wb") as handle:
            handle.write(payload)
    with open(os.path.join(dup_root, "unique.bin"), "wb") as handle:
        handle.write(b"different" * 5000)
    groups = dupes.find_duplicates([dup_root], min_size=1000, cancel=threading.Event())
    check("one duplicate group", len(groups) == 1, str(len(groups)))
    if groups:
        check("three copies", len(groups[0].paths) == 3, str(len(groups[0].paths)))
        extras = dupes.extras(groups)
        check("two extras", len(extras) == 2, str(len(extras)))

    print("\n[system]")
    mem = system.memory_info()
    check("memory total > 0", mem["total"] > 0)
    check("memory percent sane", 0 <= mem["percent"] <= 100, str(mem["percent"]))
    drives = system.drives(False)
    check("found a fixed drive", len(drives) >= 1, str(len(drives)))
    if drives:
        print(f"       {drives[0].letter}: {human_size(drives[0].free)} free of {human_size(drives[0].total)}")
    procs = system.top_processes(5)
    check("process list", len(procs) > 0, str(len(procs)))
    if procs:
        print(f"       heaviest: {procs[0].name} {human_size(procs[0].memory)}")

    print("\n[startup]")
    try:
        items = startup.list_startup()
        check("startup list readable", isinstance(items, list), str(type(items)))
        print(f"       {len(items)} entries, {sum(1 for i in items if i.enabled)} enabled")
    except Exception as exc:  # pragma: no cover
        check("startup list readable", False, str(exc))

    print("\n[targets]")
    check("target registry non-empty", len(scanner.TARGETS) >= 12, str(len(scanner.TARGETS)))
    keys = [t.key for t in scanner.TARGETS]
    check("no duplicate target keys", len(keys) == len(set(keys)))
    for target in scanner.TARGETS:
        if not target.roots and not target.collect_fn:
            check(f"target {target.key} has a source", False)

    print("\n[recycle bin query]")
    size, count = scanner.recycle_bin_info()
    print(f"       {human_size(size)} in {count} items")
    check("recycle bin query works", size >= 0)

    print("\n[game boost]")
    from core import gaming  # noqa: E402
    import winreg  # noqa: E402

    hw = gaming.hardware()
    check("cpu name", bool(hw["cpu"]) and hw["cpu"] != "Unknown CPU", hw["cpu"])
    check("gpu list", len(hw["gpus"]) >= 1, str(hw["gpus"]))
    check("ram reported", hw["ram"] > 0, human_size(hw["ram"]))
    check("display reported", hw["display"] != "Unknown display", hw["display"])
    check("readiness rows", len(gaming.readiness()) == 6, str(len(gaming.readiness())))
    check("boost level in range", 0 <= gaming.boost_level() <= 3, str(gaming.boost_level()))
    check("unknown tweak rejected", gaming.set_group("nope", True)[0] is False)

    # Backup/restore round-trip on a throwaway key — no real setting is touched.
    probe_path = r"Software\CleanBoostSelfTest"
    probe_name = "Probe"
    probe_backup = os.path.join(tempfile.gettempdir(), "cleanboost_gaming_probe.json")
    if os.path.exists(probe_backup):
        os.remove(probe_backup)
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, probe_path, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, probe_name, 0, winreg.REG_DWORD, 111)
    original_groups = gaming.REG_GROUPS
    original_backup_path = gaming._backup_path
    gaming.REG_GROUPS = {"probe": [("HKCU", probe_path, probe_name, 222)]}
    gaming._backup_path = lambda: __import__("pathlib").Path(probe_backup)
    try:
        ok, _ = gaming.set_group("probe", True)
        check("probe write", ok and gaming.group_state("probe"))
        ok, _ = gaming.set_group("probe", False)
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, probe_path) as key:
            restored, _kind = winreg.QueryValueEx(key, probe_name)
        check("probe restored to original", ok and restored == 111, str(restored))
    finally:
        gaming.REG_GROUPS = original_groups
        gaming._backup_path = original_backup_path
        if os.path.exists(probe_backup):
            os.remove(probe_backup)
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, probe_path, 0, winreg.KEY_ALL_ACCESS) as key:
            try:
                winreg.DeleteValue(key, probe_name)
            except OSError:
                pass
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, probe_path)

    print("\n[cleanup]")
    import shutil

    shutil.rmtree(root, ignore_errors=True)
    shutil.rmtree(dup_root, ignore_errors=True)

    if failures:
        print(f"\n{len(failures)} FAILURE(S): {', '.join(failures)}")
        return 1
    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
