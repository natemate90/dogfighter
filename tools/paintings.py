"""Draws the plane paintings of the loading screens and the model window again from Airfix's box art, for tools/upscale-textures.py.

The pictures of the twelve planes with box art are the Airfix box paintings,
a few hundred pixels wide. The upscaler repaints their rivets, letters and
faces. So after the loading screens and the model window's plane pictures
are made 4x, each painting is drawn again from a picture of the real box art:
Airfix's own render where its shop has one, else a seller's photo of a box.
tools/paintings-draw.py does the drawing in the desk's Python environment
(tools/desk.py), which --fetch-tools, --fetch-desk and --fetch-paintings set
up. Nothing is drawn by AI.

tools/paintings.json
  references  each picture by name: its url, its SHA-256 and what it shows.
              --fetch-tools and --fetch-paintings put it in
              upscale-tools/paintings/references/<name><ending of the url>.
  areas       the part of a target that is drawn: a rounded rectangle in
              the target's own pixels, and how many pixels its edge fades.
              "loading" is the glass of the television on a loading screen,
              "model" the inside of the frame of a model window picture.
  colour      how the painting's colours are fitted to the game's picture:
              the window radius in the game's pixels, eps, and the range of
              the gain.
  layer       defaults for every layer: feather, the soft edge in the game's
              pixels.
  targets     drawn in this order. Each has a name, the screen of
              tools/menu-pictures.json or the picture it lies on, box (the
              part of it, in the game's pixels), its area, fitted_sha256 (the
              checksum of the game's own pixels in box, which the numbers
              were fitted to; the four languages of the disc have the same),
              and its layers, lowest first. A layer names its reference and
              holds corners (where the corners of box lie in the picture), a
              grid of displacements in the game's pixels that bends the box
              a little on top of that, painted (the corners of the printed
              painting in the picture, when it is not the whole picture) and
              keep: boxes in the game's pixels where the picture shows a
              title, a logo, a frame or other words the game's painting does
              not have. There the made picture stays.

A target is left as made, and the run says why in one line, when the game's
pixels in its box are not the fitted ones, a picture of it was not made 4x,
the Python environment or a reference is missing, or the drawn painting
scores under LIMIT: its PSNR in the area against the game's own picture,
after shrinking by block average. The drawn paintings score 22 to 28 dB, the
made ones above 50, because the box art has its own colours and detail where
the game's copy is blurred. The limit only catches a drawing gone wrong as a
whole.

A piece whose pixels change is listed in the manifest with way "painting".
The note under "painting" holds the target, the checksums of its pictures,
the package versions and the scores, and a key over everything the drawing
reads. A later run with the same key keeps the pieces as they are.
"""
import hashlib
import json
import os
import subprocess

import desk
import gti
import menus
import up

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = os.path.join(HERE, "paintings.json")
DRAW = os.path.join(HERE, "paintings-draw.py")
WAY = "painting"
FOLDER = "paintings"
LIMIT = 15.0
TIMES = 4


def load_spec():
    with open(SPEC) as f:
        return json.load(f)


def reference_file(tools, name, ref):
    return os.path.join(tools, FOLDER, "references", name + os.path.splitext(ref["url"])[1].lower())


def fetch(tools, download, python_env):
    """Sets up the desk's Python environment and downloads the box art. Returns False when a part failed."""
    good = True
    try:
        python_env(os.path.join(tools, desk.WAY), desk.REQUIREMENTS, *desk.PYTHONS)
    except SystemExit as problem:
        print(problem)
        good = False
    except (OSError, subprocess.CalledProcessError):
        print("The Python packages for the paintings could not be installed.")
        good = False
    for name, ref in sorted(load_spec()["references"].items()):
        try:
            download(ref["url"], reference_file(tools, name, ref), ref["sha256"])
        except SystemExit as problem:
            print(problem)
            good = False
    if good:
        print("The box art for the paintings is in %s." % os.path.join(tools, FOLDER))
    else:
        print("A painting whose box art is missing stays as made.")
    return good


def laid_out(target, screens, sources):
    """[(path, x, y)] of the pieces a target lies on, or None when this run does not hold them all."""
    if "screen" in target:
        listed = screens.get(target["screen"])
        if not listed or listed["times"] != TIMES or listed["states"]:
            return None
        pieces = [(path, x, y) for path, x, y in listed["pieces"]]
    else:
        pieces = [(target["picture"], 0, 0)]
    return pieces if all(path in sources for path, _, _ in pieces) else None


def composed(pieces, pictures, box, times):
    """RGBA bytes of box, at times its size, cut from the pieces laid next to each other."""
    x0, y0, x1, y1 = (side * times for side in box)
    width = x1 - x0
    canvas = bytearray(width * (y1 - y0) * 4)
    for path, x, y in pieces:
        w, h, pixels = pictures[path]
        px, py = x * times, y * times
        for row in range(max(y0, py), min(y1, py + h)):
            left, right = max(x0, px), min(x1, px + w)
            if left < right:
                at = ((row - y0) * width + left - x0) * 4
                canvas[at:at + (right - left) * 4] = pixels[((row - py) * w + left - px) * 4:((row - py) * w + right - px) * 4]
    return bytes(canvas)


def laid_back(pixels, box, times, path, x, y, picture):
    """The piece's RGBA with the part inside box taken from pixels, the drawn box."""
    w, h, own = picture
    out = bytearray(own)
    x0, y0, x1, y1 = (side * times for side in box)
    width = x1 - x0
    px, py = x * times, y * times
    for row in range(max(y0, py), min(y1, py + h)):
        left, right = max(x0, px), min(x1, px + w)
        if left < right:
            at = ((row - y0) * width + left - x0) * 4
            out[((row - py) * w + left - px) * 4:((row - py) * w + right - px) * 4] = pixels[at:at + (right - left) * 4]
    return bytes(out)


def draw(sources, made_of, tools, work, out, old, skip):
    """{path: (file, checksum, bytes, note)} for the pieces whose painting was drawn again.

    sources is {path: the game's data} of this run, made_of(path) gives (made
    file, its checksum), or None for a picture that was not made, old is the
    previous manifest, skip the paths something else replaces. work is a
    folder for this run, out the folder of the set.
    """
    spec = load_spec()
    screens = menus.expanded(menus.load_spec())
    wanted = [(target, laid_out(target, screens, sources)) for target in spec["targets"]]
    wanted = [(target, pieces) for target, pieces in wanted if pieces]
    if not wanted:
        return {}

    def leave(why):
        print("  paintings left as made: " + why)
        return {}

    python = desk.python_of(tools)
    if not os.access(python, os.X_OK):
        return leave("the Python environment is missing; --fetch-paintings sets it up")
    references = {}
    for name, ref in spec["references"].items():
        file = reference_file(tools, name, ref)
        if not os.path.isfile(file):
            return leave("picture %s is missing; --fetch-paintings fetches it" % name)
        if up.sha256_of(file) != ref["sha256"]:
            return leave("picture %s does not match its pinned checksum" % name)
        references[name] = file

    originals, made, made_gti, ready = {}, {}, {}, []
    for target, pieces in wanted:
        if any(made_of(path) is None for path, _, _ in pieces):
            print("  painting %s left as made: a picture of it was not made" % target["name"])
            continue
        for path, _, _ in pieces:
            if path not in originals:
                originals[path] = gti.to_rgba(gti.parse(sources[path]).best())
                made[path] = made_of(path)
                with open(made[path][0], "rb") as f:
                    made_gti[path] = gti.parse(f.read())
        own = composed(pieces, originals, target["box"], 1)
        if hashlib.sha256(own).hexdigest() != target["fitted_sha256"]:
            print("  painting %s left as made: the game's pixels are not the ones it was fitted to" % target["name"])
            continue
        if any(gti.to_rgba(made_gti[path].best())[:2] != (originals[path][0] * TIMES, originals[path][1] * TIMES)
               for path, _, _ in pieces):
            print("  painting %s left as made: it was not made %d times as large" % (target["name"], TIMES))
            continue
        ready.append((target, pieces, own))
    if not ready:
        return {}

    with open(SPEC, "rb") as f:
        spec_sum = hashlib.sha256(f.read()).hexdigest()
    key = hashlib.sha256(json.dumps({"spec": spec_sum, "draw": up.sha256_of(DRAW), "requirements": up.sha256_of(desk.REQUIREMENTS),
                                     "python": desk.python_version(python),
                                     "made": {path: made[path][1] for _, pieces, _ in ready for path, _, _ in pieces},
                                     "references": {name: ref["sha256"] for name, ref in spec["references"].items()}},
                                    sort_keys=True).encode()).hexdigest()
    kept = desk.kept_pieces(old, key, out, WAY)
    if kept is not None:
        return {path: done for path, done in kept.items() if path not in skip}

    folder = os.path.join(work, WAY)
    os.makedirs(folder, exist_ok=True)
    big = {path: gti.to_rgba(made_gti[path].best()) for path in made_gti}
    job = {"spec": SPEC, "times": TIMES, "references": references, "targets": []}
    for number, (target, pieces, own) in enumerate(ready):
        x0, y0, x1, y1 = target["box"]
        stem = os.path.join(folder, "%02d" % number)
        for ending, data in ((".made", composed(pieces, big, target["box"], TIMES)), (".original", own)):
            with open(stem + ending, "wb") as f:
                f.write(data)
        job["targets"].append({"name": target["name"], "w": x1 - x0, "h": y1 - y0, "made": stem + ".made",
                               "original": stem + ".original", "out": stem + ".out"})
    with open(os.path.join(folder, "job.json"), "w") as f:
        json.dump(job, f)
    said = subprocess.run([python, "-I", DRAW, os.path.join(folder, "job.json")], stdout=subprocess.PIPE, text=True)
    lines = [json.loads(line) for line in said.stdout.splitlines() if line.startswith("{")]
    if said.returncode or len(lines) != len(ready) + 1:
        return leave("tools/paintings-draw.py stopped (exit %d)" % said.returncode)
    packages = lines.pop()
    done = {}
    for (target, pieces, _), item, line in zip(ready, job["targets"], lines):
        if line["match"] < LIMIT:
            print("  painting %s left as made: it scores %.1f dB, under %.1f" % (target["name"], line["match"], LIMIT))
            continue
        if not line["changed"]:
            continue
        with open(item["out"], "rb") as f:
            drawn = f.read()
        note = {"key": key, "target": target["name"], "spec_sha256": spec_sum, "packages": packages,
                "references": {layer["reference"]: spec["references"][layer["reference"]]["sha256"] for layer in target["layers"]},
                "scores": {"match": line["match"], "made_match": line["made_match"]}}
        for path, x, y in pieces:
            w, h, pixels = big[path]
            result = laid_back(drawn, target["box"], TIMES, path, x, y, big[path])
            if result == pixels or path in skip:
                continue
            data = gti.encode_like(made_gti[path], w, h, result)
            file = os.path.join(folder, "out", *up.safe_parts(path))
            os.makedirs(os.path.dirname(file), exist_ok=True)
            with open(file, "wb") as f:
                f.write(data)
            done[path] = (file, hashlib.sha256(data).hexdigest(), len(data), note)
    print("  paintings: %d of %d drawn again from box art, %d pieces" % (len({done[path][3]["target"] for path in done}), len(ready), len(done)))
    return done
