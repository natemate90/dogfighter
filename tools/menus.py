"""The flat pictures of the menus, the loading screens and the HUD, for tools/upscale-textures.py.

tools/menu-pictures.json lists them. The game draws each at the size stored
in its file, so a larger copy needs the marker file the launcher's helper
reads: <name>.2x or <name>.4x.

  "pictures"  folders whose pictures are enlarged one by one. "times" is 2
              or 4, "ways" the order in which the ways are tried.
  "screens"   pictures the game lays next to each other to fill the 640x480
              screen. They are put together first, enlarged as one picture
              and cut again, so no edge shows between two tiles.
                "grid"    a path with %d for the twelve tiles of a full
                          screen, laid out in three columns and four rows
                "range"   makes one screen for each number, put in for {n}
                "pieces"  [path, x, y] for tiles that are not on the grid
                "states"  pictures drawn over the screen now and then, such
                          as the highlight under the mouse: for each state
                          the screen is enlarged once more with those laid
                          in, and only they are cut out. Their edges then
                          continue into the screen around them.

Left out, because the game reads their pixels one by one: the Paint Room's
pieces, the stickers and Graphics\\Misc.
"""
import hashlib
import json
import os
import struct

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = os.path.join(HERE, "menu-pictures.json")
WAY = "menu"
MARKERS = (".2x", ".4x")
GRID_X = (0, 256, 512)
GRID_Y = (0, 256, 384, 448)
TGA_HEAD = "<BBBHHBHHHHBB"
TGA_TAIL = b"\0" * 8 + b"TRUEVISION-XFILE.\0"


def load_spec():
    with open(SPEC) as f:
        return json.load(f)


def read_tga(data):
    """(width, height, RGBA top row first, has alpha) of a true-colour .tga that is not compressed."""
    id_length, palette, kind, _, _, _, _, _, width, height, bits, descriptor = struct.unpack_from(TGA_HEAD, data)
    size = bits // 8
    if palette or kind != 2 or bits not in (24, 32) or len(data) < 18 + id_length + width * height * size:
        raise ValueError("not a plain true-colour .tga")
    body = data[18 + id_length:18 + id_length + width * height * size]
    rows = [body[y * width * size:(y + 1) * width * size] for y in range(height)]
    if not descriptor & 0x20:
        rows.reverse()
    body = b"".join(rows)
    pixels = bytearray(width * height * 4)
    pixels[0::4], pixels[1::4], pixels[2::4] = body[2::size], body[1::size], body[0::size]
    pixels[3::4] = body[3::4] if size == 4 else b"\xff" * (width * height)
    return width, height, bytes(pixels), size == 4


def write_tga(width, height, rgba, alpha):
    """A .tga as the game's own photos are: not compressed, bottom row first."""
    size = 4 if alpha else 3
    body = bytearray(width * height * size)
    body[0::size], body[1::size], body[2::size] = rgba[2::4], rgba[1::4], rgba[0::4]
    if alpha:
        body[3::4] = rgba[3::4]
    rows = [bytes(body[y * width * size:(y + 1) * width * size]) for y in range(height)]
    head = struct.pack(TGA_HEAD, 0, 0, 2, 0, 0, 0, 0, 0, width, height, size * 8, 8 if alpha else 0)
    return head + b"".join(reversed(rows)) + TGA_TAIL


def expanded(spec):
    """Every screen of the spec with its pieces and states written out: {name: screen}."""
    screens = {}
    for listed in spec["screens"]:
        first, last = listed.get("range", (0, 0))
        for n in range(first, last + 1):
            def put(text):
                return text.replace("{n}", str(n))
            pieces = [[put(path), x, y] for path, x, y in listed.get("pieces", [])]
            if "grid" in listed:
                pieces += [[put(listed["grid"]) % (i + 1), GRID_X[i % 3], GRID_Y[i // 3]] for i in range(12)]
            states = {state: [[put(path), x, y] for path, x, y in laid] for state, laid in listed.get("states", {}).items()}
            screens[put(listed["name"])] = {"size": listed.get("size", [640, 480]), "times": listed["times"], "ways": listed["ways"],
                                            "pieces": pieces, "states": states}
    return screens


def plans(packs):
    """What to do with each menu picture the packs hold.

    Returns ({path as the pack spells it: plan}, {screen name: screen}). A
    plan holds "times" and "ways", and for a piece of a screen "screen",
    "state" (None for the screen itself) and "at". A screen with a piece that
    no pack holds is left out.
    """
    spec = load_spec()
    spelled = {entry.path.lower(): entry.path for pack in packs for entry in pack.entries}
    found, screens = {}, {}
    for name, screen in expanded(spec).items():
        laid = [(None, piece) for piece in screen["pieces"]] + [(state, piece) for state in sorted(screen["states"]) for piece in screen["states"][state]]
        if any(piece[0].lower() not in spelled for _, piece in laid):
            print("  screen %s is left as it is: the packs do not hold all its pictures" % name)
            continue
        layout = hashlib.sha256(json.dumps(screen, sort_keys=True).encode()).hexdigest()
        screens[name] = dict(screen, layout=layout)
        for state, (path, x, y) in laid:
            found[spelled[path.lower()]] = {"times": screen["times"], "ways": screen["ways"], "screen": name, "state": state,
                                            "at": [x, y], "layout": layout}
    for lower, path in spelled.items():
        if path in found or not lower.endswith((".gti", ".tga")):
            continue
        for listed in spec["pictures"]:
            if lower.startswith(listed["under"].lower()) and not any(word.lower() in lower for word in listed.get("not", [])):
                found[path] = {"times": listed["times"], "ways": listed["ways"], "screen": None}
                break
    return found, screens


def asked(plan):
    """What a menu picture asks of this tool; it is made again when this changes."""
    said = {"way": WAY, "times": plan["times"], "ways": plan["ways"]}
    if plan["screen"]:
        said.update(screen=plan["screen"], layout=plan["layout"])
    return said


def composed(size, laid):
    """RGBA of a screen: laid is [(x, y, width, height, RGBA)], later ones over earlier ones."""
    full_w, full_h = size
    canvas = bytearray(b"\0\0\0\xff" * (full_w * full_h))
    for x, y, width, height, pixels in laid:
        if x < 0 or y < 0 or x + width > full_w or y + height > full_h:
            raise ValueError("a piece lies outside the screen")
        for row in range(height):
            at = ((y + row) * full_w + x) * 4
            canvas[at:at + width * 4] = pixels[row * width * 4:(row + 1) * width * 4]
    return canvas


def cut(pixels, full_w, x, y, width, height):
    return b"".join(pixels[((y + row) * full_w + x) * 4:((y + row) * full_w + x + width) * 4] for row in range(height))
