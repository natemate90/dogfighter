#!/usr/bin/env python3
"""Rebuilds the website's icon files from site/favicon.svg: python3 tools/favicons.py

Needs only the standard library. It draws the circles of the SVG itself, so the
SVG may hold nothing but <circle> elements with a fill and an optional stroke.
Android may crop a maskable icon to a circle 80% of its width, so that drawing
stays inside 70%.
"""
import math
import struct
import zlib
from pathlib import Path
from xml.etree import ElementTree

SITE = Path(__file__).resolve().parent.parent / "site"
PAPER = (0xEB, 0xE4, 0xCF)
TOUCH_SHARE = 0.82
MASKABLE_SHARE = 0.70


def hex_colour(text):
    text = text.lstrip("#")
    return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))


def read_discs():
    root = ElementTree.parse(SITE / "favicon.svg").getroot()
    left, top, width, height = (float(n) for n in root.get("viewBox").split())
    if width != height:
        raise SystemExit("favicon.svg is not square")
    discs = []
    for node in root:
        if node.tag.rsplit("}", 1)[-1] != "circle":
            raise SystemExit(f"favicon.svg holds a <{node.tag}>; this tool only draws circles")
        cx, cy, r = (float(node.get(k)) for k in ("cx", "cy", "r"))
        cx, cy = cx - left, cy - top
        stroke = node.get("stroke")
        half = float(node.get("stroke-width", "1")) / 2 if stroke else 0
        if stroke:
            discs.append((cx, cy, r + half, hex_colour(stroke)))
        discs.append((cx, cy, r - half, hex_colour(node.get("fill"))))
    return width, discs


def draw(size, share=1.0, background=None):
    box, discs = read_discs()
    per_unit = size * share / box
    offset = size * (1 - share) / 2
    rows = []
    for y in range(size):
        row = []
        for x in range(size):
            u = (x + 0.5 - offset) / per_unit
            v = (y + 0.5 - offset) / per_unit
            red, green, blue = background or (0, 0, 0)
            alpha = 1.0 if background else 0.0
            for cx, cy, r, colour in discs:
                cover = (r - math.hypot(u - cx, v - cy)) * per_unit + 0.5
                if cover <= 0:
                    continue
                cover = min(cover, 1.0)
                rest = alpha * (1 - cover)
                total = cover + rest
                red = (colour[0] * cover + red * rest) / total
                green = (colour[1] * cover + green * rest) / total
                blue = (colour[2] * cover + blue * rest) / total
                alpha = total
            row.append((round(red), round(green), round(blue), round(alpha * 255)))
        rows.append(row)
    return rows


def png(rows, opaque):
    size = len(rows)
    raw = bytearray()
    for row in rows:
        raw.append(0)
        for pixel in row:
            raw += bytes(pixel[:3] if opaque else pixel)

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    head = struct.pack(">IIBBBBB", size, size, 8, 2 if opaque else 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", head) + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b"")


def ico_bitmap(rows):
    size = len(rows)
    data = bytearray(struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0, 0, 0, 0, 0, 0))
    for row in reversed(rows):
        for red, green, blue, alpha in row:
            data += bytes((blue, green, red, alpha))
    stride = (size + 31) // 32 * 4
    for row in reversed(rows):
        bits = bytearray(stride)
        for x, pixel in enumerate(row):
            if pixel[3] == 0:
                bits[x // 8] |= 0x80 >> (x % 8)
        data += bits
    return bytes(data)


def ico(sizes):
    bitmaps = [ico_bitmap(draw(size)) for size in sizes]
    out = bytearray(struct.pack("<HHH", 0, 1, len(sizes)))
    offset = 6 + 16 * len(sizes)
    for size, bitmap in zip(sizes, bitmaps):
        out += struct.pack("<BBBBHHII", size, size, 0, 0, 1, 32, len(bitmap), offset)
        offset += len(bitmap)
    for bitmap in bitmaps:
        out += bitmap
    return bytes(out)


def main():
    files = {"favicon.ico": ico((16, 32, 48))}
    for size in (32, 48, 96, 192, 512):
        files[f"favicon-{size}.png"] = png(draw(size), opaque=False)
    files["apple-touch-icon.png"] = png(draw(180, TOUCH_SHARE, PAPER), opaque=True)
    files["favicon-maskable-512.png"] = png(draw(512, MASKABLE_SHARE, PAPER), opaque=True)
    for name, data in files.items():
        (SITE / name).write_bytes(data)
        print(f"{name}  {len(data)} bytes")


if __name__ == "__main__":
    main()
