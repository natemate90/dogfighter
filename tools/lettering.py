"""Redraws the short lettering of a few textures with real fonts, for tools/upscale-textures.py.

An upscaler cannot read: on a label a few pixels high it draws letters that
are not quite letters. For the textures in tools/lettering.json the made
texture is taken, the old letters in each box are painted out from the
pixels around them, and the words are set again with a font. Size, stretch,
weight, position and the shift of each letter were fitted once to the
original pixels and are kept in that file, so every run draws the same.

tools/lettering.json
  fonts     each font by file name, with its SHA-256. A downloaded font has
            its pinned url and its licence beside it; --fetch-tools puts it
            in upscale-tools/fonts/<folder>/. A system font has its path on
            macOS and is only read to draw pixels.
  textures  each with a name, the words it sets, the paths it is drawn
            for with the SHA-256 of the game's own texture there, and a list
            of regions:
    box     x0 y0 x1 y1 in original pixels; nothing outside it changes.
    turn    how often the box is turned a quarter left before the lines are
            set, for writing that runs up a book spine.
    ink     the colour of the old letters, which are painted out. The
            paint-out blends into the pixels just outside the box, except on
            the sides listed in framed (left, top, right, bottom; true for
            all), where the box meets a drawn frame or other dark lines and
            only its own pixels are used. threshold (default 0.12) is how far
            a pixel must lean from the background to the ink to count as an
            old letter.
    lines   text, font, face (the index in a .ttc), size (em in original
            pixels), stretch, weight (original pixels added around each
            stroke), x (left edge of the ink), base (baseline), track,
            shift (per letter) and layers, laid on in order: colour, an
            optional "to" colour that the colour turns into from the top of
            the capitals to the baseline, and spread, which widens the
            letters of that layer (below 0 narrows them). Without layers the
            letters take the ink colour. The numbers are in original pixels
            inside the turned box.
    copy    "plain" instead of lines: the box is taken from the plain filter.

A texture is left as made, and a line says why, when its game texture is
not the listed one, a font is missing, or a check fails:
  outside   pixels changed outside the boxes, or alpha changed: must be 0.
  edges     for a tiling texture, the edge rows and columns: unchanged.
  match     each box shrunk back to the original size against the original,
            as PSNR in dB: at least LIMIT. The drawn textures score 11 to 34;
            the same words moved 2 pixels or drawn 20% smaller score 6 to 9.
A system font with another checksum than listed is drawn anyway; the checks
catch a font whose letters moved.

tools/lettering-draw.c, built with the Xcode Command Line Tools, reads jobs
on stdin as fields that each end in a NUL byte and prints "ok" or
"fail <why>" for each:
  draw MADE WIDTH HEIGHT SCALE OUT COPY REGIONS, then per region either
    copy X0 Y0 X1 Y1, or
    text X0 Y0 X1 Y1 TURN AROUND_LEFT AROUND_TOP AROUND_RIGHT AROUND_BOTTOM
      INK_R INK_G INK_B THRESHOLD LINES, then per line
      FONT FACE TEXT SIZE STRETCH WEIGHT X BASE TRACK SHIFTS SHIFT... LAYERS,
      then per layer SPREAD R G B R2 G2 B2
  cover WIDTH HEIGHT SCALE OUT SPREAD, then one line with LAYERS 0: the
    line's coverage as raw floats, used when the numbers were fitted.
MADE, OUT and COPY are raw RGBA at the made size.
"""
import hashlib
import json
import math
import os
import subprocess

import gti
import up

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = os.path.join(HERE, "lettering.json")
WAY = "lettering"
LIMIT = 10.0
THRESHOLD = 0.12
SIDES = ("left", "top", "right", "bottom")


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load_spec():
    with open(SPEC) as f:
        return json.load(f)


def font_file(tools, name, font):
    return font["system"] if "system" in font else os.path.join(tools, "fonts", font["folder"], name)


def fetch_fonts(tools):
    """Downloads the pinned fonts and their licences. A font that cannot be fetched only costs its textures their lettering."""
    good = True
    for name, font in sorted(load_spec()["fonts"].items()):
        if "url" not in font:
            continue
        folder = os.path.join(tools, "fonts", font["folder"])
        for target, url, digest in ((os.path.join(folder, name), font["url"], font["sha256"]),
                                    (os.path.join(folder, font["licence"]["file"]), font["licence"]["url"], font["licence"]["sha256"])):
            if os.path.isfile(target) and sha256_of(target) == digest:
                continue
            os.makedirs(folder, exist_ok=True)
            part = target + ".part"
            done = subprocess.run(["/usr/bin/curl", "-fsSL", "--retry", "3", "-o", part, url])
            if done.returncode or sha256_of(part) != digest:
                if os.path.exists(part):
                    os.remove(part)
                print("Could not fetch %s with its pinned checksum. Its lettering is left as made." % url)
                good = False
                continue
            os.replace(part, target)
    if good:
        print("The lettering fonts are in %s. Their checksums match." % os.path.join(tools, "fonts"))


def fonts_found(tools, spec):
    """{name: (path, None)} for each usable font, or (None, why)."""
    found = {}
    for name, font in spec["fonts"].items():
        path = font_file(tools, name, font)
        if not os.path.isfile(path):
            found[name] = (None, "font %s is not on this Mac" % name if "system" in font else
                           "font %s is missing; --fetch-tools fetches it" % name)
        elif "system" not in font and sha256_of(path) != font["sha256"]:
            found[name] = (None, "font %s does not match its pinned checksum" % name)
        else:
            found[name] = (path, None)
    return found


def build_helper(work):
    helper = os.path.join(work, "lettering-draw")
    command = ["/usr/bin/cc", "-O2", "-o", helper, os.path.join(HERE, "lettering-draw.c"),
               "-framework", "CoreText", "-framework", "CoreGraphics", "-framework", "CoreFoundation"]
    if subprocess.run(command).returncode:
        return None
    return helper


def wanted(sources, skip):
    """{path: (texture entry, why or None)} for each texture of this run that the spec names and nothing else replaces."""
    spec = load_spec()
    found = {}
    for entry in spec["textures"]:
        for path, digest in entry["paths"].items():
            if path in sources and path not in skip:
                same = hashlib.sha256(sources[path]).hexdigest() == digest
                found[path] = (entry, None if same else "the game's texture is not the one the lettering was fitted to")
    return found


def job_fields(entry, fonts, made, out, copy, width, height, scale):
    fields = ["draw", made, width, height, scale, out, copy, len(entry["regions"])]
    for region in entry["regions"]:
        fields += ["copy" if "copy" in region else "text"] + region["box"]
        if "copy" in region:
            continue
        framed = region.get("framed", [])
        fields += [region.get("turn", 0)] + [0 if framed is True or side in framed else 1 for side in SIDES] + region["ink"] + [region.get("threshold", THRESHOLD), len(region["lines"])]
        for line in region["lines"]:
            shift = line.get("shift", [])
            fields += [fonts[line["font"]][0], line.get("face", 0), line["text"], line["size"], line.get("stretch", 1.0),
                       line.get("weight", 0.0), line["x"], line["base"], line.get("track", 0.0), len(shift)] + shift
            layers = line.get("layers", [{"colour": region["ink"]}])
            fields.append(len(layers))
            for layer in layers:
                fields += [layer.get("spread", 0.0)] + layer["colour"] + layer.get("to", layer["colour"])
    return b"".join(os.fsencode(str(field)) + b"\0" for field in fields)


def psnr(made, original, width, scale, box):
    """The box of a picture scale times larger, shrunk by block average, against the original."""
    x0, y0, x1, y1 = box
    big = width * scale
    total = count = 0
    for y in range(y0, y1):
        rows = [made[((y * scale + j) * big + x0 * scale) * 4:((y * scale + j) * big + x1 * scale) * 4] for j in range(scale)]
        for x in range(x1 - x0):
            for c in range(3):
                block = sum(row[(x * scale + i) * 4 + c] for row in rows for i in range(scale))
                diff = block / (scale * scale) - original[((y * width) + x0 + x) * 4 + c]
                total += diff * diff
                count += 1
    return 99.0 if total == 0 else round(10 * math.log10(255 * 255 * count / total), 2)


def checked(entry, drawn, made, original, width, height, scale, tiles):
    """The scores of a drawn texture, and None or why it may not be used."""
    big_w, big_h = width * scale, height * scale
    inside = bytearray(big_w * big_h)
    for region in entry["regions"]:
        x0, y0, x1, y1 = (v * scale for v in region["box"])
        for y in range(y0, y1):
            inside[y * big_w + x0:y * big_w + x1] = b"\1" * (x1 - x0)
    outside = sum(1 for i in range(big_w * big_h) if drawn[i * 4:i * 4 + 4] != made[i * 4:i * 4 + 4] and
                  (not inside[i] or drawn[i * 4 + 3] != made[i * 4 + 3]))
    edges = []
    if tiles[0]:
        edges += [y * big_w + x for y in range(big_h) for x in (0, big_w - 1)]
    if tiles[1]:
        edges += [y * big_w + x for y in (0, big_h - 1) for x in range(big_w)]
    edge_changes = sum(1 for i in edges if drawn[i * 4:i * 4 + 4] != made[i * 4:i * 4 + 4])
    match = [psnr(drawn, original, width, scale, region["box"]) for region in entry["regions"]]
    scores = {"outside": outside, "edges": edge_changes, "match": match}
    if outside:
        return scores, "%d pixels changed outside the boxes" % outside
    if edge_changes:
        return scores, "%d edge pixels of a tiling texture changed" % edge_changes
    if min(match) < LIMIT:
        return scores, "match %.1f dB is under %.1f" % (min(match), LIMIT)
    return scores, None


def draw(items, tools, work, plain):
    """Draws the listed textures. items: [(path, entry, original data, made file, tiles)].

    Returns {path: (file, checksum, bytes, note)} for those that passed;
    prints a line for each that did not. plain(data, scale, tiles) gives the
    plain filter's RGBA for a copy region.
    """
    done = {}
    if not items:
        return done
    spec = load_spec()
    fonts = fonts_found(tools, spec)
    folder = os.path.join(work, WAY)
    os.makedirs(folder, exist_ok=True)
    helper = build_helper(folder)
    if not helper:
        print("Could not build tools/lettering-draw.c, so the lettering is left as made.")
        return done
    for number, (path, entry, data, made_file, tiles) in enumerate(items):
        name = path.split("\\")[-1]
        names = sorted({line["font"] for region in entry["regions"] for line in region.get("lines", [])})
        missing = [fonts[n][1] for n in names if fonts[n][0] is None]
        if missing:
            print("  lettering left as made: %s (%s)" % (path, ", ".join(missing)))
            continue
        original = gti.parse(data).best()
        width, height, original_rgba = gti.to_rgba(original)
        with open(made_file, "rb") as f:
            made_gti = gti.parse(f.read())
        big_w, big_h, made_rgba = gti.to_rgba(made_gti.best())
        scale = big_w // width
        if scale * width != big_w or scale * height != big_h:
            print("  lettering left as made: %s (the made texture is not a whole multiple of the original)" % path)
            continue
        stem = os.path.join(folder, "%03d" % number)
        with open(stem + ".made", "wb") as f:
            f.write(made_rgba)
        copy = ""
        if any("copy" in region for region in entry["regions"]):
            copy = stem + ".plain"
            with open(copy, "wb") as f:
                f.write(plain(data, scale, tiles))
        said = subprocess.run([helper], input=job_fields(entry, fonts, stem + ".made", stem + ".out", copy, big_w, big_h, scale),
                              stdout=subprocess.PIPE).stdout.decode().strip()
        if not said.startswith("ok"):
            print("  lettering left as made: %s (%s)" % (path, said[5:] or "the helper stopped"))
            continue
        with open(stem + ".out", "rb") as f:
            drawn = f.read()
        scores, why = checked(entry, drawn, made_rgba, original_rgba, width, height, scale, tiles)
        if why:
            print("  lettering left as made: %s (%s)" % (path, why))
            continue
        result = gti.encode_like(made_gti, big_w, big_h, drawn)
        target = os.path.join(folder, "out", *up.safe_parts(path))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as f:
            f.write(result)
        note = {"fonts": {n: sha256_of(fonts[n][0]) for n in names}, "words": entry.get("words", ""),
                "spec_sha256": hashlib.sha256(json.dumps(entry, sort_keys=True).encode()).hexdigest(), "scores": scores}
        differ = [n for n in names if note["fonts"][n] != spec["fonts"][n]["sha256"]]
        if differ:
            note["fonts_not_as_fitted"] = differ
            print("  lettering for %s drawn with %s, which differs from the copy it was fitted with" % (name, ", ".join(differ)))
        done[path] = (target, hashlib.sha256(result).hexdigest(), len(result), note)
    return done
