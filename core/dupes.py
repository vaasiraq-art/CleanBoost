"""Duplicate file finder (size -> quick hash -> full hash)."""
from __future__ import annotations

import hashlib
import os
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable, Iterable

from .utils import is_reparse

CHUNK = 1024 * 1024
HEAD = 64 * 1024


@dataclass
class DupGroup:
    size: int
    digest: str
    paths: list[str] = field(default_factory=list)

    @property
    def wasted(self) -> int:
        return self.size * max(0, len(self.paths) - 1)

    @property
    def title(self) -> str:
        name = os.path.basename(self.paths[0]) if self.paths else "?"
        return f"{name}  ({len(self.paths)} copies)"


def _hash_head(path: str) -> str | None:
    try:
        with open(path, "rb") as handle:
            return hashlib.blake2b(handle.read(HEAD), digest_size=16).hexdigest()
    except OSError:
        return None


def _hash_full(path: str) -> str | None:
    digest = hashlib.blake2b(digest_size=16)
    try:
        with open(path, "rb") as handle:
            while True:
                block = handle.read(CHUNK)
                if not block:
                    break
                digest.update(block)
        return digest.hexdigest()
    except OSError:
        return None


def find_duplicates(
    roots: Iterable[str],
    min_size: int = 1024 * 1024,
    cancel=None,
    on_progress: Callable[[int], None] | None = None,
) -> list[DupGroup]:
    """Return groups of byte-identical files, biggest waste first."""
    by_size: dict[int, list[str]] = defaultdict(list)
    scanned = 0

    for root in roots:
        if not os.path.isdir(root):
            continue
        stack = [root]
        while stack:
            if cancel is not None and cancel.is_set():
                return []
            current = stack.pop()
            try:
                with os.scandir(current) as it:
                    for node in it:
                        if cancel is not None and cancel.is_set():
                            return []
                        try:
                            if node.is_dir(follow_symlinks=False):
                                if not is_reparse(node.path):
                                    stack.append(node.path)
                            elif node.is_file(follow_symlinks=False):
                                size = node.stat(follow_symlinks=False).st_size
                                if size >= min_size:
                                    by_size[size].append(node.path)
                                    scanned += 1
                                    if on_progress and scanned % 200 == 0:
                                        on_progress(scanned)
                        except OSError:
                            continue
            except OSError:
                continue

    candidates = {size: paths for size, paths in by_size.items() if len(paths) > 1}
    del by_size

    # Stage 1: head hash narrows the field cheaply.
    by_head: dict[tuple[int, str], list[str]] = defaultdict(list)
    for size, paths in candidates.items():
        if cancel is not None and cancel.is_set():
            return []
        for path in paths:
            digest = _hash_head(path)
            if digest:
                by_head[(size, digest)].append(path)

    groups: list[DupGroup] = []
    for (size, _head), paths in by_head.items():
        if len(paths) < 2:
            continue
        by_full: dict[str, list[str]] = defaultdict(list)
        for path in paths:
            if cancel is not None and cancel.is_set():
                return []
            digest = _hash_full(path)
            if digest:
                by_full[digest].append(path)
        for digest, identical in by_full.items():
            if len(identical) > 1:
                groups.append(DupGroup(size=size, digest=digest, paths=sorted(identical)))

    groups.sort(key=lambda g: g.wasted, reverse=True)
    return groups


def total_wasted(groups: Iterable[DupGroup]) -> int:
    return sum(g.wasted for g in groups)


def extras(groups: Iterable[DupGroup], keep: str = "oldest") -> list[str]:
    """All copies except the one to keep per group."""
    result: list[str] = []
    for group in groups:
        paths = list(group.paths)
        if len(paths) < 2:
            continue
        if keep == "oldest":
            def mtime(p: str) -> float:
                try:
                    return os.path.getmtime(p)
                except OSError:
                    return 0.0

            keep_path = min(paths, key=mtime)
        elif keep == "newest":
            def mtime2(p: str) -> float:
                try:
                    return os.path.getmtime(p)
                except OSError:
                    return 0.0

            keep_path = max(paths, key=mtime2)
        else:
            keep_path = min(paths, key=len)
        result.extend(p for p in paths if p != keep_path)
    return result
