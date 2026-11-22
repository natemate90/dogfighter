"""Redraws the letters of four of the game's fonts from the typefaces they came from, for tools/upscale-textures.py.

The game cuts its letters out of font pictures in Graphics\\Fonts, with the
boxes of the .fnt tables. Four of those fonts are typefaces that come with
macOS: typewriter and typewriter_small are American Typewriter, system is
Arial and system12 is Helvetica. Each glyph of their six pictures is drawn
again from the typeface, 4 times as large (or 2 with --font-times 2), into
its own box. The made picture of the set, enlarged by repeating pixels, is
the start: it keeps every glyph that is not drawn and everything outside the
boxes. The .fnt tables do not change.

tools/fonts.json
  fonts   each typeface by file name, with its path on macOS and its
          SHA-256. It is only read to draw pixels.
  tables  per font table: the typeface and its face (the index in a .ttc),
          size (em in original pixels), stretch, weight (original pixels
          added around each stroke) and gain (the alpha of a fully covered
          pixel, 1 for opaque) for the whole font; the
          pictures it covers with the SHA-256 of the game's own picture;
    glyphs  one row per box: picture, x, y, width, height, the character
            drawn, the left edge of its ink and its baseline in the box (in
            original pixels), its size (the font's, or smaller where the
            game's glyph is smaller) and its match when the values were set.
    kept    one row per box that keeps the made picture's pixels, with why.
  Where several characters of a table share a box, the one that fits best is
  drawn. The game's own mappings stay: system draws Y where its table
  says Ü.

Colour: the alpha of a drawn pixel is the glyph's coverage times gain. Its
colour is the one the original picture gives that alpha, so a font whose
colour follows its alpha keeps doing so.

Weight and gain: the game draws the small original letters enlarged and
smoothed, so on screen their strokes are about one original pixel wide and
only partly opaque: heavier and lighter than the thin, opaque strokes of the
typeface. Both numbers were fitted once per font so that the drawn glyphs,
softened by a Gaussian of one pixel at 4x, come closest to the original
picture enlarged 4x the smooth way the game does.

Checks, for each drawn glyph:
  match    the glyph is drawn with MARGIN original pixels around its box
           and shrunk to the original size (the mean of each block). Inside
           the box it is compared with the original alpha; all ink outside
           the box counts as difference, since the box cuts it off. The
           match is 100 * (1 - difference / (new ink + old ink)), and must
           be at least LIMIT.
  place    the glyph is also drawn one original pixel left, right, up and
           down. At its own place it must match better than at each of
           those by LEAD. A glyph one pixel off has its right place next to
           it, which matches better, so it fails. LIMIT alone cannot tell:
           the heavier, lighter strokes of weight and gain score lower at
           the right place, and a glyph one pixel off often scores as well.
           The bar | of system12 fails this: it fills its box from top to
           bottom, so one pixel up matches exactly as well.
  outside  at most OUTSIDE of the glyph's ink may fall outside the box,
           measured on the glyph drawn with weight 0 and full alpha, so the
           extra weight, which the box cuts off as the game's glyphs are
           cut, does not count.
A glyph that fails keeps the made pixels. For the whole picture:
  picture  pixels of the new picture that differ from the made picture
           outside the drawn boxes: must be 0.
A picture is left as made when the game's picture is not the listed one, the
typeface is missing (one line per font says so), the helper fails or the
picture check fails.

The glyphs are drawn by tools/lettering-draw.c with its cover job.
"""
import hashlib
import json
import os
import struct
import subprocess

import gti
import lettering
import up

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = os.path.join(HERE, "fonts.json")
WAY = "font"
LIMIT = 60.0
LEAD = 1.0
OUTSIDE = 0.05
STEPS = ((0, 0), (-1, 0), (1, 0), (0, -1), (0, 1))
TIMES = 4
MARGIN = 3


def load_spec():
    with open(SPEC) as f:
        return json.load(f)


def wanted(sources, skip):
    """{path: (table name, why or None)} for each font picture of this run that the spec names and nothing else replaces."""
    found = {}
    for name, table in load_spec()["tables"].items():
        for path, digest in table["pictures"].items():
            if path in sources and path not in skip:
                same = hashlib.sha256(sources[path]).hexdigest() == digest
                found[path] = (name, None if same else "the game's picture is not the one the font was fitted to")
    return found


def typefaces():
    """{name: (file, checksum, None)} for each typeface on this Mac, else (None, None, why)."""
    found = {}
    for name, font in load_spec()["fonts"].items():
        if os.path.isfile(font["system"]):
            found[name] = (font["system"], up.sha256_of(font["system"]), None)
        else:
            found[name] = (None, None, "%s is not on this Mac" % name)
    return found


def colours(rgba):
    """The original's colour for each alpha, the median of the pixels with that alpha, filled in between."""
    seen = {}
    for at in range(0, len(rgba), 4):
        if rgba[at + 3]:
            seen.setdefault(rgba[at + 3], []).append(rgba[at:at + 3])
    known = {alpha: bytes(sorted(c[i] for c in found)[len(found) // 2] for i in range(3)) for alpha, found in seen.items()}
    if not known:
        return [b"\xff\xff\xff"] * 256
    levels = sorted(known)
    table = []
    for alpha in range(256):
        below = max((level for level in levels if level <= alpha), default=None)
        above = min((level for level in levels if level >= alpha), default=None)
        if below is None or above is None or below == above:
            table.append(known[below if above is None else above])
        else:
            t = (alpha - below) / (above - below)
            table.append(bytes(int(known[below][i] + (known[above][i] - known[below][i]) * t + 0.5) for i in range(3)))
    table[0] = table[255]
    return table


def enlarged(rgba, width, height, times):
    """Each pixel repeated times across and down."""
    rows = []
    for y in range(height):
        row = b"".join(rgba[at:at + 4] * times for at in range(y * width * 4, (y + 1) * width * 4, 4))
        rows += [row] * times
    return bytearray(b"".join(rows))


def match(alpha, original, width, x, y, w, h, times):
    """The glyph, drawn with MARGIN around its box and shrunk to the original size, against the original alpha; 100 is the same.

    Also returns the share of the glyph's ink that falls outside the box.
    """
    side = (w + 2 * MARGIN) * times
    differ = total = spilt = ink = 0.0
    for by in range(-MARGIN, h + MARGIN):
        for bx in range(-MARGIN, w + MARGIN):
            block = sum(alpha[((by + MARGIN) * times + j) * side + (bx + MARGIN) * times + i] for j in range(times) for i in range(times))
            new = block / (times * times * 255.0)
            inside = 0 <= by < h and 0 <= bx < w
            old = original[((y + by) * width + x + bx) * 4 + 3] / 255.0 if inside else 0.0
            differ += abs(new - old)
            total += new + old
            ink += new
            spilt += 0.0 if inside else new
    return (round(100 * (1 - differ / total), 2) if total else 0.0), (spilt / ink if ink else 1.0)


def verdict(found):
    """(why the glyph is kept, or None; its lead) from the matches of STEPS and of the weight-0 drawing, in that order."""
    score = found[0][0]
    lead = round(score - max(other for other, _ in found[1:len(STEPS)]), 2)
    if score < LIMIT:
        return "match %.1f is under %.1f" % (score, LIMIT), lead
    if lead < LEAD:
        return "one pixel off it matches as well or better (lead %.1f)" % lead, lead
    if found[-1][1] > OUTSIDE:
        return "%.0f%% of its ink falls outside the box" % (100 * found[-1][1]), lead
    return None, lead


def draw(items, work, times=TIMES):
    """Draws the listed font pictures. items: [(path, table name, original data, made file)].

    Returns {path: (file, checksum, bytes, note)} for the pictures that were
    drawn; prints a line for each font or picture that was not.
    """
    done = {}
    if not items:
        return done
    spec = load_spec()
    faces = typefaces()
    folder = os.path.join(work, WAY)
    os.makedirs(folder, exist_ok=True)
    helper = None
    told = set()
    for number, (path, name, data, made_file) in enumerate(items):
        table = spec["tables"][name]
        font, digest, missing = faces[table["font"]]
        if missing:
            if name not in told:
                print("  font %s keeps its current enlargement: %s" % (name, missing))
                told.add(name)
            continue
        if helper is None:
            helper = lettering.build_helper(folder) or ""
        if not helper:
            print("Could not build tools/lettering-draw.c, so the fonts keep their current enlargement.")
            return done
        original = gti.parse(data).best()
        width, height, original_rgba = gti.to_rgba(original)
        with open(made_file, "rb") as f:
            made_gti = gti.parse(f.read())
        made_w, made_h, made_rgba = gti.to_rgba(made_gti.best())
        made_times = made_w // width
        if made_times * width != made_w or made_times * height != made_h or times % made_times:
            print("  font picture left as made: %s (the made picture is not %d or a part of %d times the original)" % (path, times, times))
            continue
        picture = os.path.splitext(path.split("\\")[-1])[0].lower()
        rows = [row for row in table["glyphs"] if row[0] == picture]
        stem = os.path.join(folder, "%02d" % number)
        fields = []
        for at, (_, x, y, w, h, char, left, base, size, _) in enumerate(rows):
            for step, (dx, dy) in enumerate(STEPS + ((0, 0),)):
                weight = table["weight"] if step < len(STEPS) else 0
                fields += ["cover", w + 2 * MARGIN, h + 2 * MARGIN, times, "%s-%03d-%d" % (stem, at, step), 0, font, table["face"], char,
                           size, table["stretch"], weight, left + MARGIN + dx, base + MARGIN + dy, 0, 0, 0]
        said = subprocess.run([helper], input=b"".join(os.fsencode(str(field)) + b"\0" for field in fields),
                              stdout=subprocess.PIPE).stdout.decode().splitlines()
        if len(said) != len(rows) * (len(STEPS) + 1) or any(not line.startswith("ok") for line in said):
            print("  font picture left as made: %s (the helper could not draw every glyph)" % path)
            continue
        big_w, big_h = width * times, height * times
        base_rgba = enlarged(made_rgba, made_w, made_h, times // made_times)
        drawn = bytearray(base_rgba)
        palette = colours(original_rgba)
        gain = table.get("gain", 1.0)
        inked, placed = {}, []
        kept = [{"char": row[5], "box": row[1:5], "why": row[6]} for row in table["kept"] if row[0] == picture]
        scores, leads = [], []
        for at, (_, x, y, w, h, char, _, _, _, _) in enumerate(rows):
            if x < 0 or y < 0 or x + w > width or y + h > height:
                kept.append({"char": char, "box": [x, y, w, h], "why": "the box runs past the picture"})
                continue
            side = (w + 2 * MARGIN) * times
            tried = []
            for step in range(len(STEPS) + 1):
                with open("%s-%03d-%d" % (stem, at, step), "rb") as f:
                    cover = struct.unpack("<%df" % (side * (h + 2 * MARGIN) * times), f.read())
                strength = gain if step < len(STEPS) else 1.0
                tried.append((bytes(min(255, max(0, int(value * strength * 255 + 0.5))) for value in cover)))
            found = [match(alpha, original_rgba, width, x, y, w, h, times) for alpha in tried]
            alpha, score = tried[0], found[0][0]
            why, lead = verdict(found)
            if why:
                kept.append({"char": char, "box": [x, y, w, h], "why": why})
                continue
            scores.append(score)
            leads.append(lead)
            placed.append((x, y, w, h))
            for by in range(h * times):
                for bx in range(w * times):
                    pixel = (y * times + by) * big_w + x * times + bx
                    value = max(alpha[(by + MARGIN * times) * side + bx + MARGIN * times], inked.get(pixel, 0))
                    inked[pixel] = value
                    drawn[pixel * 4:pixel * 4 + 4] = palette[value] + bytes([value])
        boxed = bytearray(big_w * big_h)
        for x, y, w, h in placed:
            for line in range(max(0, y * times), min(big_h, (y + h) * times)):
                start, end = line * big_w + max(0, x * times), line * big_w + min(big_w, (x + w) * times)
                boxed[start:end] = b"\1" * (end - start)
        outside = sum(1 for pixel in range(big_w * big_h)
                      if not boxed[pixel] and drawn[pixel * 4:pixel * 4 + 4] != base_rgba[pixel * 4:pixel * 4 + 4])
        if outside:
            print("  font picture left as made: %s (%d pixels changed outside the drawn boxes)" % (path, outside))
            continue
        result = gti.encode_like(made_gti, big_w, big_h, bytes(drawn))
        target = os.path.join(folder, "out", *up.safe_parts(path))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as f:
            f.write(result)
        scores.sort()
        note = {"table": name, "font": table["font"], "font_sha256": digest, "times": times, "drawn": len(scores),
                "kept": sorted(kept, key=lambda k: k["box"]), "outside": outside,
                "match": {"lowest": scores[0], "middle": scores[len(scores) // 2]} if scores else None,
                "lead": round(min(leads), 2) if leads else None,
                "spec_sha256": hashlib.sha256(json.dumps(table, sort_keys=True).encode()).hexdigest()}
        if digest != spec["fonts"][table["font"]]["sha256"]:
            note["font_not_as_fitted"] = True
            print("  font %s drawn with a %s that differs from the copy it was fitted with" % (name, table["font"]))
        done[path] = (target, hashlib.sha256(result).hexdigest(), len(result), note)
    return done
