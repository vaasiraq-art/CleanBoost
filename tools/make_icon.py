"""Generate assets/icon.ico (PNG-compressed ICO, no third-party libraries)."""
from __future__ import annotations

import os
import struct
import zlib

SIZES = [16, 24, 32, 48, 64, 128, 256]
ACCENT_TOP = (59, 130, 246)
ACCENT_BOTTOM = (37, 99, 235)
CHECK = (255, 255, 255)
SS = 4  # supersampling factor


def _near_segment(x, y, x1, y1, x2, y2, width) -> bool:
    vx, vy = x2 - x1, y2 - y1
    wx, wy = x - x1, y - y1
    length2 = vx * vx + vy * vy
    t = max(0.0, min(1.0, (wx * vx + wy * vy) / length2))
    cx, cy = x1 + t * vx, y1 + t * vy
    return (x - cx) ** 2 + (y - cy) ** 2 <= (width / 2) ** 2


def _render(size: int) -> bytes:
    """Return a PNG for one icon size."""
    px = size * SS
    radius = px * 0.24
    width = px * 0.085
    rows = []
    for y in range(px):
        row = bytearray()
        for x in range(px):
            dx = 0.0
            dy = 0.0
            if x < radius:
                dx = radius - x
            elif x > px - radius:
                dx = x - (px - radius)
            if y < radius:
                dy = radius - y
            elif y > px - radius:
                dy = y - (px - radius)
            inside = (dx * dx + dy * dy) <= radius * radius
            if not inside:
                row.extend((0, 0, 0, 0))
                continue
            blend = y / max(1, px - 1)
            r = int(ACCENT_TOP[0] + (ACCENT_BOTTOM[0] - ACCENT_TOP[0]) * blend)
            g = int(ACCENT_TOP[1] + (ACCENT_BOTTOM[1] - ACCENT_TOP[1]) * blend)
            b = int(ACCENT_TOP[2] + (ACCENT_BOTTOM[2] - ACCENT_TOP[2]) * blend)
            hit = _near_segment(x, y, px * 0.28, px * 0.52, px * 0.44, px * 0.68, width) or _near_segment(
                x, y, px * 0.44, px * 0.68, px * 0.73, px * 0.35, width
            )
            if hit:
                r, g, b = CHECK
            row.extend((r, g, b, 255))
        rows.append(bytes(row))

    # box-filter downsample
    out_rows = []
    count = SS * SS
    for y in range(size):
        row = bytearray()
        for x in range(size):
            acc = [0, 0, 0, 0]
            for sy in range(SS):
                source = rows[y * SS + sy]
                for sx in range(SS):
                    offset = (x * SS + sx) * 4
                    acc[0] += source[offset]
                    acc[1] += source[offset + 1]
                    acc[2] += source[offset + 2]
                    acc[3] += source[offset + 3]
            row.extend((acc[0] // count, acc[1] // count, acc[2] // count, acc[3] // count))
        out_rows.append(bytes(row))

    raw = b"".join(b"\x00" + r for r in out_rows)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def main() -> None:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    assets = os.path.join(root, "assets")
    os.makedirs(assets, exist_ok=True)
    images = [_render(size) for size in SIZES]

    offset = 6 + 16 * len(images)
    directory = b""
    for size, data in zip(SIZES, images):
        directory += struct.pack(
            "<BBBBHHII",
            0 if size >= 256 else size,
            0 if size >= 256 else size,
            0,
            0,
            1,
            32,
            len(data),
            offset,
        )
        offset += len(data)

    ico = struct.pack("<HHH", 0, 1, len(images)) + directory + b"".join(images)
    path = os.path.join(assets, "icon.ico")
    with open(path, "wb") as handle:
        handle.write(ico)
    print(f"wrote {path} ({len(ico)} bytes)")


if __name__ == "__main__":
    main()
