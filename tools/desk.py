"""Draws the model kit boxes and paint tins on the main menu's desk again from photos of real ones, for tools/upscale-textures.py.

The upscaler cannot tell what the few pixels of a kit box or a paint tin
show, and paints smears. So after the main menu is made 4x, each box face and
each tin on the desk is drawn again from a photo of a real 1990s Airfix box or
of the tin on Humbrol's 1997 colour binder, fitted into the made picture's
colours and light. tools/desk-draw.py does the drawing; it needs numpy and
Pillow, which --fetch-tools and --fetch-desk put in a Python environment of
its own in upscale-tools/desk/venv, with the versions of
tools/desk-requirements.txt and a Python of PYTHONS, which have wheels for
them. Nothing is drawn by AI.

tools/desk.json
  screen        the screen of tools/menu-pictures.json the desk lies on.
  states        its highlights that lie over a box or a tin. Each is drawn
                again with the highlight laid in, and cut out.
  fitted_sha256 the checksum of the game's own pixels under the boxes and
                tins, which the numbers were fitted to. The four languages
                of the disc have the same pixels there.
  references    each photo by name: its url, its SHA-256 and what it shows.
                --fetch-tools and --fetch-desk put it in
                upscale-tools/desk/references/<name>.jpg.
  fonts         the fonts of tools/lettering.json it uses, by file name.
                --fetch-fonts, --fetch-desk and --fetch-tools fetch them.
  faces         drawn in this order. Each has the way it is built (make),
                the kit, its corners in the 4x menu (quad: the top left, top
                right, bottom right and bottom left of the printed face),
                shade_top for a side under another box, and paper_from for
                a face whose own pixels are no guide to the paper colour.
                invented marks a kit the game's picture is too small to
                identify; a kit of the right colours was chosen.
  fiat_lid, spitfire_lid, type11_side, type10_side, type11_end
                how each way builds its face: the photo, the corners of the
                face in the photo and the size it is straightened to, the
                areas painted over with the paper or the blue around them,
                and where the words and the strip of box painting go.
  colour_fit, soften, feather, side_shade
                how a face is fitted into the made picture.
  tins          the tin drawn on the binder (its rim ellipse and bottom, in
                the photo's pixels) and each tin in the 4x menu: centre x,
                half width, centre y and half height of its top ellipse, and
                the lowest point of its body. The game's tins are 2 to 28%
                taller than real ones. label_stretch is how much taller than
                in the drawing the label may be: 1.0 keeps Humbrol's own
                proportions. label_from_top is the share of the height left
                over that goes above the label, as plain label paper (the row
                label_paper pixels under the rim); the rest shows the bare
                tin below the label. At 0 the label starts under the rim, as
                on a real tin.

The desk is left as made, and the run says why in one line, when the game's
pixels under the items are not the fitted ones, a picture of the screen was
not made, the Python environment, a photo or a font is missing, or a drawn
piece scores under LIMIT: its PSNR against the game's own picture, after
shrinking by block average. The drawn pieces score 20 to 32 dB, the made
ones 48 to 69. The limit only catches a drawing gone wrong as a whole: with
every item moved 4 pixels of the original, the pieces still score 17 to 27.

A piece whose pixels change is listed in the manifest with way "desk". The
note under "desk" holds the checksums of the photos and fonts, the package
versions and the scores, and a key over everything the drawing reads. A later
run with the same key keeps the pieces as they are, without drawing again.
"""
import hashlib
import json
import math
import os
import subprocess

import gti
import menus
import up

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = os.path.join(HERE, "desk.json")
DRAW = os.path.join(HERE, "desk-draw.py")
REQUIREMENTS = os.path.join(HERE, "desk-requirements.txt")
WAY = "desk"
LIMIT = 15.0
PYTHONS = ((3, 9), (3, 14))


def load_spec():
    with open(SPEC) as f:
        return json.load(f)


def python_of(tools):
    return os.path.join(tools, WAY, "venv", "bin", "python")


def reference_file(tools, name):
    return os.path.join(tools, WAY, "references", name + ".jpg")


def fetch(tools, download, python_env):
    """Sets up the Python environment and downloads the photos. Returns False when a part failed."""
    good = True
    try:
        python_env(os.path.join(tools, WAY), REQUIREMENTS, *PYTHONS)
    except SystemExit as problem:
        print(problem)
        good = False
    except (OSError, subprocess.CalledProcessError):
        print("The desk's Python packages could not be installed.")
        good = False
    for name, ref in sorted(load_spec()["references"].items()):
        try:
            download(ref["url"], reference_file(tools, name), ref["sha256"])
        except SystemExit as problem:
            print(problem)
            good = False
    if good:
        print("The desk's photos and Python packages are in %s." % os.path.join(tools, WAY))
    else:
        print("The desk stays as made until the missing parts are there.")
    return good


def item_areas(spec, times):
    """Rectangles of the original screen that the drawn items read or change."""
    boxes = []
    for item in spec["faces"]:
        xs, ys = [p[0] for p in item["quad"]], [p[1] for p in item["quad"]]
        boxes.append((min(xs) - 3, min(ys) - 3, max(xs) + 3, max(ys) + 3))
    tins = spec["tins"]
    for t in tins["tins"].values():
        grow = tins["grow"]
        boxes.append((t["cx"] - t["rx"] - grow - 2, t["yc"] - t["ry"] - grow - 2, t["cx"] + t["rx"] + grow + 3,
                      t["yb"] + tins["grow_bottom"] + 3))
    return [(math.floor(x0 / times) - 1, math.floor(y0 / times) - 1, math.ceil(x1 / times) + 1, math.ceil(y1 / times) + 1)
            for x0, y0, x1, y1 in boxes]


def fingerprint(laid, originals, areas):
    """SHA-256 of the game's own pixels of every piece inside the areas."""
    digest = hashlib.sha256()
    for _, path, x, y in laid:
        width, height, pixels = originals[path]
        for ax0, ay0, ax1, ay1 in areas:
            x0, y0, x1, y1 = max(ax0, x), max(ay0, y), min(ax1, x + width), min(ay1, y + height)
            for row in range(y0, y1) if x0 < x1 else ():
                digest.update(pixels[((row - y) * width + x0 - x) * 4:((row - y) * width + x1 - x) * 4])
    return digest.hexdigest()


def draw(sources, made_of, fonts, tools, work, out, old, skip):
    """{path: (file, checksum, bytes, note)} for the pieces of the desk's screen that were drawn again.

    sources is {path: the game's data} of this run, made_of(path) gives (made
    file, its checksum), or None for a picture that was not made, fonts is
    {name: (file, checksum, None)} of tools/lettering.json, or (None, None,
    why) for a font that cannot be used, old is the previous manifest, skip
    the paths something else replaces. work is a folder for this run, out the
    folder of the set.
    """
    spec = load_spec()
    listed = menus.expanded(menus.load_spec()).get(spec["screen"])
    if not listed:
        return {}
    laid = [(None, path, x, y) for path, x, y in listed["pieces"]]
    laid += [(state, path, x, y) for state in spec["states"] for path, x, y in listed["states"][state]]
    if not all(path in sources for _, path, _, _ in laid):
        return {}

    def leave(why):
        print("  desk left as made: " + why)
        return {}

    made = {path: made_of(path) for _, path, _, _ in laid}
    if any(made[path] is None for path in made):
        return leave("a picture of the %s screen was not made" % spec["screen"])
    times = listed["times"]
    originals = {path: gti.to_rgba(gti.parse(sources[path]).best()) for _, path, _, _ in laid}
    if fingerprint(laid, originals, item_areas(spec, times)) != spec["fitted_sha256"]:
        return leave("the game's pixels under the boxes and tins are not the ones the desk was fitted to")
    python = python_of(tools)
    if not os.access(python, os.X_OK):
        return leave("its Python environment is missing; --fetch-desk sets it up")
    references = {}
    for name, ref in spec["references"].items():
        file = reference_file(tools, name)
        if not os.path.isfile(file):
            return leave("photo %s is missing; --fetch-desk fetches it" % name)
        if up.sha256_of(file) != ref["sha256"]:
            return leave("photo %s does not match its pinned checksum" % name)
        references[name] = file
    for name in spec["fonts"]:
        if fonts[name][0] is None:
            return leave(fonts[name][2])
    font_sums = {name: fonts[name][1] for name in spec["fonts"]}

    with open(SPEC, "rb") as f:
        spec_sum = hashlib.sha256(f.read()).hexdigest()
    key = hashlib.sha256(json.dumps({"spec": spec_sum, "draw": up.sha256_of(DRAW), "requirements": up.sha256_of(REQUIREMENTS),
                                     "python": python_version(python), "made": {path: made[path][1] for _, path, _, _ in laid},
                                     "references": {name: spec["references"][name]["sha256"] for name in references},
                                     "fonts": font_sums}, sort_keys=True).encode()).hexdigest()
    kept = kept_pieces(old, key, out)
    if kept is not None:
        return {path: done for path, done in kept.items() if path not in skip}

    folder = os.path.join(work, WAY)
    os.makedirs(folder, exist_ok=True)
    job = {"spec": SPEC, "times": times, "size": [side * times for side in listed["size"]], "references": references,
           "fonts": {name: fonts[name][0] for name in spec["fonts"]},
           "pieces": [], "states": {}}
    made_gti = {}
    for number, (state, path, x, y) in enumerate(laid):
        width, height, pixels = originals[path]
        with open(made[path][0], "rb") as f:
            made_gti[path] = gti.parse(f.read())
        big_w, big_h, big = gti.to_rgba(made_gti[path].best())
        if (big_w, big_h) != (width * times, height * times):
            return leave("%s was not made %d times as large" % (path, times))
        stem = os.path.join(folder, "%02d" % number)
        for ending, data in ((".made", big), (".original", pixels)):
            with open(stem + ending, "wb") as f:
                f.write(data)
        piece = {"path": path, "x": x * times, "y": y * times, "w": big_w, "h": big_h, "file": stem + ".made",
                 "original": stem + ".original", "out": stem + ".out"}
        (job["states"].setdefault(state, []) if state else job["pieces"]).append(piece)
    with open(os.path.join(folder, "job.json"), "w") as f:
        json.dump(job, f)
    said = subprocess.run([python, "-I", DRAW, os.path.join(folder, "job.json")], stdout=subprocess.PIPE, text=True)
    lines = [json.loads(line) for line in said.stdout.splitlines() if line.startswith("{")]
    if said.returncode or len(lines) != len(laid) + 1:
        return leave("tools/desk-draw.py stopped (exit %d)" % said.returncode)
    packages = lines.pop()
    scored = {line["path"]: line for line in lines}
    low = [path for path, line in scored.items() if line["changed"] and line["match"] < LIMIT]
    if low:
        return leave("%s scores %.1f dB, under %.1f" % (low[0], scored[low[0]]["match"], LIMIT))
    note = {"key": key, "spec_sha256": spec_sum, "references": {name: spec["references"][name]["sha256"] for name in references},
            "fonts": font_sums, "packages": packages}
    done = {}
    for piece in job["pieces"] + [piece for laid_in in job["states"].values() for piece in laid_in]:
        line = scored[piece["path"]]
        if not line["changed"] or piece["path"] in skip:
            continue
        with open(piece["out"], "rb") as f:
            result = gti.encode_like(made_gti[piece["path"]], piece["w"], piece["h"], f.read())
        target = os.path.join(folder, "out", *up.safe_parts(piece["path"]))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as f:
            f.write(result)
        done[piece["path"]] = (target, hashlib.sha256(result).hexdigest(), len(result),
                               dict(note, scores={"match": line["match"], "made_match": line["made_match"]}))
    print("  desk: %d pieces of the %s screen drawn again from photos" % (len(done), spec["screen"]))
    return done


def python_version(python):
    said = subprocess.run([python, "-I", "-c", "import sys; print(sys.version.split()[0])"], stdout=subprocess.PIPE, text=True)
    return said.stdout.strip()


def kept_pieces(old, key, out):
    """The pieces an earlier run drew with the same key, when every one of them is still in the set; else None."""
    found = {}
    for record in old.get("textures", []):
        if record.get("way") == WAY and record[WAY].get("key") == key:
            file = os.path.join(out, "cache", *up.safe_parts(record["path"]))
            if not (os.path.isfile(file) and up.sha256_of(file) == record["file_sha256"]):
                return None
            found[record["path"]] = (file, record["file_sha256"], record["bytes"], record[WAY])
    return found or None
