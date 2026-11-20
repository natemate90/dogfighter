#!/usr/bin/env python3
"""Converts the game's .gti textures to PNG and back.

The .gti format, as found in the files of the English release
-------------------------------------------------------------
All numbers are little-endian 32-bit.

  "GtIm", version 4
  then chunks until the end of the file: a 4-byte tag, a size, the data

  "CRC0" chunk, 4 bytes: the sharing key (see below).
  "Imag" chunk: pixel format, width, height, palette entries, mipmap levels,
                the palette (4 bytes an entry: blue, green, red, unused),
                then the levels, largest first.

A file holds the same picture more than once, in different pixel formats. The
game asks for the format its video driver wants and reads only that chunk.
Every file in the packs has one palette chunk and one true-colour chunk:
formats 3 and 7 for a picture without alpha, 4 and 8 for one with alpha.
If the wanted format is missing the game reads format 8, then 7, and converts.
So a file with only the true-colour chunk is complete.

  format  bits  layout of one pixel
  3       8     palette index
  4       16    palette index, alpha
  6       16    alpha, red, green, blue, 4 bits each (three font files only)
  7       24    red, green, blue
  8       32    blue, green, red, alpha
  The game also knows 1 and 2 (16-colour palette) and 5 (16 bit). No file
  uses them.

Rows run top to bottom. Level n is (width >> n) by (height >> n) pixels, but
its block is always (level 0 bytes) >> 2n long. For a width or height that is
not a power of two the block is a little longer than the picture; the rest is
padding. A file may hold at most 9 levels: the game has 9 slots.

Quirks, all kept when a file is read and written back unchanged:
  - a chunk's size may be larger than its content; the extra bytes are unused
  - the last chunk's size may run past the end of the file
  - there may be several CRC0 chunks; the game uses the last one

The sharing key
---------------
CRC0 is not a checksum of the file. The game uses it to find pictures that are
the same under two names: before it loads a texture it looks for a loaded one
with the same key and uses that instead. A changed picture with the old key
can therefore show up as another texture, or not at all. A missing key works,
but the game then loads the file twice to work one out.

The key is the CRC-32 of all levels in format 8. A format 7 picture is
converted first, with alpha 0. encode() writes a key made that way, so two
replacements share a surface exactly when their pixels are equal.
"""
import os
import struct
import sys
import zlib

MAGIC = b"GtIm"
VERSION = 4
MAX_LEVELS = 9
PIXEL_BITS = {1: 4, 2: 8, 3: 8, 4: 16, 5: 16, 6: 16, 7: 24, 8: 32}
FORMAT_NAMES = {3: "palette", 4: "palette+alpha", 6: "ARGB4444", 7: "RGB888", 8: "BGRA8888"}
DECODE_ORDER = (8, 7, 4, 3, 6)


class Image:
    def __init__(self, fmt, width, height, palette, levels, extra=b""):
        self.fmt, self.width, self.height = fmt, width, height
        self.palette, self.levels, self.extra = palette, levels, extra

    @property
    def alpha(self):
        return self.fmt in (2, 4, 6, 8)

    def body(self):
        head = struct.pack("<5I", self.fmt, self.width, self.height, len(self.palette) // 4, len(self.levels))
        return head + self.palette + b"".join(self.levels) + self.extra


def level_bytes(fmt, width, height, level):
    return ((width * height * PIXEL_BITS[fmt]) >> 3) >> (2 * level)


def level_count(width, height):
    """The number of levels the game itself makes: the smallest keeps both sides above 4."""
    count = MAX_LEVELS
    while count > 1 and not ((width >> (count - 1)) > 4 and (height >> (count - 1)) > 4):
        count -= 1
    return count


class Gti:
    """A file as a list of (tag, stated size, content). content is an Image for "Imag" chunks."""

    def __init__(self, chunks, tail=b""):
        self.chunks, self.tail = chunks, tail

    @property
    def images(self):
        return [c[2] for c in self.chunks if c[0] == b"Imag"]

    @property
    def keys(self):
        return [struct.unpack("<I", c[2][:4])[0] for c in self.chunks if c[0] == b"CRC0" and len(c[2]) >= 4]

    def best(self):
        for fmt in DECODE_ORDER:
            for image in self.images:
                if image.fmt == fmt:
                    return image
        raise ValueError("no chunk in a pixel format this tool reads")

    def build(self):
        out = [MAGIC, struct.pack("<I", VERSION)]
        for tag, size, content in self.chunks:
            out.append(tag + struct.pack("<I", size))
            out.append(content.body() if isinstance(content, Image) else content)
        return b"".join(out) + self.tail


def parse(data):
    if data[:4] != MAGIC or struct.unpack_from("<I", data, 4)[0] != VERSION:
        raise ValueError("not a version 4 .gti file")
    chunks = []
    at = 8
    while at + 8 <= len(data):
        tag = data[at:at + 4]
        size = struct.unpack_from("<I", data, at + 4)[0]
        body = data[at + 8:at + 8 + size]
        at += 8 + size
        if tag != b"Imag" or len(body) < 20:
            chunks.append((tag, size, body))
            continue
        fmt, width, height, colours, count = struct.unpack_from("<5I", body, 0)
        if fmt not in PIXEL_BITS or count > MAX_LEVELS:
            raise ValueError("pixel format %d with %d levels is not understood" % (fmt, count))
        pos = 20 + 4 * colours
        palette = body[20:pos]
        levels = []
        for level in range(count):
            length = level_bytes(fmt, width, height, level)
            levels.append(body[pos:pos + length])
            pos += length
        if pos > len(body):
            raise ValueError("the picture is cut short")
        chunks.append((tag, size, Image(fmt, width, height, palette, levels, body[pos:])))
    return Gti(chunks, data[at:])


def to_rgba(image, level=0):
    """One level as (width, height, RGBA bytes)."""
    width, height = image.width >> level, image.height >> level
    count = width * height
    data = image.levels[level]
    out = bytearray(count * 4)
    if image.fmt == 8:
        out[0::4], out[1::4], out[2::4], out[3::4] = data[2:count * 4:4], data[1:count * 4:4], data[0:count * 4:4], data[3:count * 4:4]
    elif image.fmt == 7:
        out[0::4], out[1::4], out[2::4] = data[0:count * 3:3], data[1:count * 3:3], data[2:count * 3:3]
        out[3::4] = b"\xff" * count
    elif image.fmt in (3, 4):
        step = 1 if image.fmt == 3 else 2
        index = data[0:count * step:step]
        entries = len(image.palette) // 4
        for channel, source in ((0, 2), (1, 1), (2, 0)):
            table = bytes(image.palette[4 * i + source] if i < entries else 0 for i in range(256))
            out[channel::4] = index.translate(table)
        out[3::4] = b"\xff" * count if image.fmt == 3 else data[1:count * 2:2]
    elif image.fmt == 6:
        low, high = data[0:count * 2:2], data[1:count * 2:2]
        spread = bytes((i & 15) * 17 for i in range(256)), bytes((i >> 4) * 17 for i in range(256))
        out[0::4], out[1::4] = high.translate(spread[0]), low.translate(spread[1])
        out[2::4], out[3::4] = low.translate(spread[0]), high.translate(spread[1])
    else:
        raise ValueError("pixel format %d is not read by this tool" % image.fmt)
    return width, height, bytes(out)


def halve(width, height, pixels, size):
    """A 2x2 average. size is the number of bytes in a pixel."""
    half_w, half_h = width >> 1, height >> 1
    out = bytearray(half_w * half_h * size)
    row = width * size
    for y in range(half_h):
        top = pixels[2 * y * row:(2 * y + 1) * row]
        bottom = pixels[(2 * y + 1) * row:(2 * y + 2) * row]
        for c in range(size):
            out[y * half_w * size + c:(y + 1) * half_w * size:size] = bytes(
                (a + b + d + e + 2) >> 2
                for a, b, d, e in zip(top[c::2 * size], top[size + c::2 * size],
                                      bottom[c::2 * size], bottom[size + c::2 * size]))
    return half_w, half_h, bytes(out)


def sharing_key(fmt, levels):
    if fmt == 8:
        return zlib.crc32(b"".join(levels)) & 0xFFFFFFFF
    crc = 0
    for level in levels:
        count = len(level) // 3
        wide = bytearray(count * 4)
        wide[0::4], wide[1::4], wide[2::4] = level[2:count * 3:3], level[1:count * 3:3], level[0:count * 3:3]
        crc = zlib.crc32(bytes(wide), crc)
    return crc & 0xFFFFFFFF


def encode(width, height, rgba, alpha, levels=None):
    """A new .gti with a key and one true-colour chunk. levels=None makes the game's own number."""
    count = level_count(width, height) if levels is None else max(1, min(levels, MAX_LEVELS))
    fmt, size = (8, 4) if alpha else (7, 3)
    pixels = bytearray(width * height * size)
    if alpha:
        pixels[0::4], pixels[1::4], pixels[2::4], pixels[3::4] = rgba[2::4], rgba[1::4], rgba[0::4], rgba[3::4]
    else:
        pixels[0::3], pixels[1::3], pixels[2::3] = rgba[0::4], rgba[1::4], rgba[2::4]
    blocks = []
    w, h, pixels = width, height, bytes(pixels)
    for level in range(count):
        if level:
            w, h, pixels = halve(w, h, pixels, size)
        blocks.append(pixels.ljust(level_bytes(fmt, width, height, level), b"\0"))
    image = Image(fmt, width, height, b"", blocks)
    key = struct.pack("<I", sharing_key(fmt, blocks))
    return Gti([(b"CRC0", 4, key), (b"Imag", len(image.body()), image)]).build()


def encode_like(original, width, height, rgba):
    """A replacement for original: same kind of alpha, and mipmaps only if original had them."""
    best = original.best()
    return encode(width, height, rgba, best.alpha, None if len(best.levels) > 1 else 1)


def write_png(width, height, rgba, alpha=True):
    size = 4 if alpha else 3
    if not alpha:
        rgb = bytearray(width * height * 3)
        rgb[0::3], rgb[1::3], rgb[2::3] = rgba[0::4], rgba[1::4], rgba[2::4]
        rgba = bytes(rgb)
    row = width * size
    raw = b"".join(b"\0" + rgba[y * row:(y + 1) * row] for y in range(height))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    head = struct.pack(">IIBBBBB", width, height, 8, 6 if alpha else 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", head) + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b"")


def _unfilter(raw, height, stride, size):
    out = bytearray()
    prev = bytearray(stride)
    mask_low = int.from_bytes(b"\x7f" * stride, "big")
    mask_high = int.from_bytes(b"\x80" * stride, "big")
    at = 0
    for _ in range(height):
        kind = raw[at]
        line = bytearray(raw[at + 1:at + 1 + stride])
        at += stride + 1
        if kind == 1:
            for i in range(size, stride):
                line[i] = (line[i] + line[i - size]) & 255
        elif kind == 2:
            a, b = int.from_bytes(line, "big"), int.from_bytes(prev, "big")
            line = bytearray((((a & mask_low) + (b & mask_low)) ^ ((a ^ b) & mask_high)).to_bytes(stride, "big"))
        elif kind == 3:
            for i in range(size):
                line[i] = (line[i] + (prev[i] >> 1)) & 255
            for i in range(size, stride):
                line[i] = (line[i] + ((line[i - size] + prev[i]) >> 1)) & 255
        elif kind == 4:
            for i in range(size):
                line[i] = (line[i] + prev[i]) & 255
            for i in range(size, stride):
                left, up, corner = line[i - size], prev[i], prev[i - size]
                p = left + up - corner
                pa, pb, pc = abs(p - left), abs(p - up), abs(p - corner)
                line[i] = (line[i] + (left if pa <= pb and pa <= pc else up if pb <= pc else corner)) & 255
        elif kind != 0:
            raise ValueError("bad PNG filter %d" % kind)
        out += line
        prev = line
    return bytes(out)


def read_png(data):
    """Returns (width, height, RGBA bytes, has_alpha). Reads every PNG kind except interlaced ones."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG file")
    at = 8
    head = palette = transparent = None
    packed = []
    while at + 8 <= len(data):
        length, tag = struct.unpack_from(">I4s", data, at)
        body = data[at + 8:at + 8 + length]
        at += 12 + length
        if tag == b"IHDR":
            head = struct.unpack(">IIBBBBB", body)
        elif tag == b"PLTE":
            palette = body
        elif tag == b"tRNS":
            transparent = body
        elif tag == b"IDAT":
            packed.append(body)
        elif tag == b"IEND":
            break
    width, height, depth, kind, _, _, interlace = head
    if interlace:
        raise ValueError("interlaced PNG files are not supported")
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[kind]
    size = max(1, channels * depth // 8)
    stride = (width * channels * depth + 7) // 8
    rows = _unfilter(zlib.decompress(b"".join(packed)), height, stride, size)

    if depth == 16:
        rows = rows[0::2]
        if transparent and kind in (0, 2):
            transparent = transparent[0::2]
    elif depth < 8:
        values = bytearray()
        scale = 255 // ((1 << depth) - 1) if kind == 0 else 1
        per_byte = 8 // depth
        for y in range(height):
            line = rows[y * stride:(y + 1) * stride]
            row = [((byte >> (8 - depth * (k + 1))) & ((1 << depth) - 1)) * scale for byte in line for k in range(per_byte)]
            values += bytes(row[:width])
        rows = bytes(values)
        if transparent and kind == 0:
            transparent = bytes([transparent[1] * scale])
    elif transparent and kind in (0, 2):
        transparent = transparent[1::2]

    count = width * height
    out = bytearray(count * 4)
    has_alpha = kind in (4, 6) or transparent is not None
    if kind == 3:
        for c in range(3):
            out[c::4] = rows.translate(bytes(palette[3 * i + c] if 3 * i + c < len(palette) else 0 for i in range(256)))
        out[3::4] = rows.translate(((transparent or b"") + b"\xff" * 256)[:256])
    elif kind in (0, 4):
        grey = rows[0::channels]
        out[0::4] = out[1::4] = out[2::4] = grey
        out[3::4] = rows[1::2] if kind == 4 else b"\xff" * count
        if kind == 0 and transparent:
            out[3::4] = grey.translate(bytes(0 if i == transparent[0] else 255 for i in range(256)))
    else:
        out[0::4], out[1::4], out[2::4] = rows[0::channels], rows[1::channels], rows[2::channels]
        out[3::4] = rows[3::4] if kind == 6 else b"\xff" * count
        if kind == 2 and transparent:
            key = bytes(transparent[:3])
            for i in range(count):
                if rows[3 * i:3 * i + 3] == key:
                    out[4 * i + 3] = 0
    return width, height, bytes(out), has_alpha


def pack_textures(pack_paths):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import up
    for path in pack_paths:
        pack = up.Pack(path)
        for entry in pack.entries:
            if entry.name.lower().endswith(".gti"):
                yield entry.path, pack.read(entry)


def check(pack_paths):
    """Round trip of every texture: .gti -> PNG -> .gti."""
    total = same_container = same_pixels = same_file = same_key = one_level = 0
    for name, data in pack_textures(pack_paths):
        total += 1
        original = parse(data)
        same_container += original.build() == data
        best = original.best()
        width, height, rgba = to_rgba(best)
        back = read_png(write_png(width, height, rgba, best.alpha))
        made = encode_like(original, back[0], back[1], back[2])
        copy = parse(made)
        ok = copy.best().fmt == best.fmt and copy.best().levels[0] == best.levels[0]
        same_pixels += ok
        same_file += made == data
        if len(best.levels) == 1 and original.keys:
            one_level += 1
            same_key += copy.keys[0] in original.keys
        if not ok or original.build() != data:
            print("differs: " + name)
    print("%d textures" % total)
    print("%d read and written back unchanged, byte for byte" % same_container)
    print("%d with identical full-size pixels after .gti -> PNG -> .gti" % same_pixels)
    print("%d of %d one-level textures got the key the game stored" % (same_key, one_level))
    print("%d whole files identical after .gti -> PNG -> .gti" % same_file)
    return 0 if total and same_container == total and same_pixels == total else 1


USAGE = """usage: gti.py info FILE.gti...
       gti.py decode FILE.gti FILE.png
       gti.py encode FILE.png FILE.gti [--like ORIGINAL.gti] [--levels N]
       gti.py check PACK.up...

decode writes the full-size picture from the best chunk in the file.
encode writes a sharing key and one true-colour chunk. With --like it copies
the original's kind (alpha or not, mipmaps or not). --levels sets the number
of mipmap levels; the default is what the game itself would make.
check runs .gti -> PNG -> .gti on every texture in the packs."""


def main(argv):
    if len(argv) >= 3 and argv[1] == "info":
        for path in argv[2:]:
            with open(path, "rb") as f:
                gti = parse(f.read())
            print("%s: keys %s" % (path, " ".join("%08x" % k for k in gti.keys) or "none"))
            for image in gti.images:
                print("  format %d (%s), %dx%d, %d palette entries, %d levels" % (
                    image.fmt, FORMAT_NAMES.get(image.fmt, "?"), image.width, image.height,
                    len(image.palette) // 4, len(image.levels)))
        return 0
    if len(argv) == 4 and argv[1] == "decode":
        with open(argv[2], "rb") as f:
            best = parse(f.read()).best()
        width, height, rgba = to_rgba(best)
        with open(argv[3], "wb") as f:
            f.write(write_png(width, height, rgba, best.alpha))
        return 0
    if len(argv) >= 4 and argv[1] == "encode":
        like = levels = None
        rest = argv[4:]
        while rest:
            if rest[0] == "--like" and len(rest) > 1:
                with open(rest[1], "rb") as f:
                    like = parse(f.read())
            elif rest[0] == "--levels" and len(rest) > 1 and rest[1].isdigit():
                levels = int(rest[1])
            else:
                sys.exit(USAGE)
            rest = rest[2:]
        with open(argv[2], "rb") as f:
            width, height, rgba, alpha = read_png(f.read())
        if like and levels is None:
            data = encode_like(like, width, height, rgba)
        else:
            data = encode(width, height, rgba, like.best().alpha if like else alpha, levels)
        with open(argv[3], "wb") as f:
            f.write(data)
        return 0
    if len(argv) >= 3 and argv[1] == "check":
        return check(argv[2:])
    sys.exit(USAGE)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
