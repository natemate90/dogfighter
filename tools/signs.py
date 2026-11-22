"""Draws the hand lettering of the menu signs and paper headings again, for tools/upscale-textures.py.

The upscaler draws shapes of its own into small lettering: on the main menu
it turned the G of CAMPAIGN into a spiral, and on the briefing papers it
gave the stencil headings light edges and stripes. So after the menus are
made 4x, the letters in each listed box are drawn again from the game's own
pixels alone, by tools/signs-draw.py (it says how) in the desk's Python
environment, which --fetch-tools and --fetch-desk set up. Nothing is drawn by
AI and no font is used.

tools/signs.json
  look     the numbers of the drawing, the same for every box: the lighter
           share of the box whose median is its paper (paper_share), how far
           a colour may lie from that paper to count as the sheet
           (paper_distance, in levels), the share of the box's pixels that
           set the ink colour (ink_share), how much ink a game pixel must
           hold to count as lettering (found), to have made pixels round it
           cleared (near_found, within near game pixels) and how much a made
           pixel must hold to be cleared (removed), the reach of the paper
           fill in game pixels (spread), the softness of the cut (soft, in
           ink share) and of the cleared area (clear_soft, in made pixels),
           and the least ink a box must hold (least_ink, in game pixels).
  targets  each with a name, the screen of tools/menu-pictures.json it lies
           on, box (x0 y0 x1 y1 in the screen's game pixels), ink (about the
           colour of its letters), other (inks in the box that are not
           redrawn, such as a sign's black frame), states (the screen's
           states it is drawn in; "" is the screen itself, and a state such
           as a highlight is the screen with that state's pictures laid on)
           and fitted_sha256: per state, the checksum of the game's pixels
           in the box.

For each target and state, the box is cut from the game's pictures and from
the made 4x pictures, put together as the game lays them, drawn again, and
put back into the pictures of that state only: the screen's own pictures for
"", the state's pictures for a state.

A target is left as made in a state, and the run says why in one line, when
the game's pixels in its box are not the fitted ones, a picture of it was not
made 4x, the Python environment is missing, the drawing script says why, or
the drawn box scores under LIMIT: its PSNR against the game's own pixels
after shrinking by block average.

A piece whose pixels change is listed in the manifest with way "sign" and a
note with the targets drawn in it. The desk, the paintings and the stamps are
drawn over these pieces, so a piece they change keeps the new letters and
is listed with their way, with the sign note beside it.
"""
import hashlib
import json
import os
import subprocess

import desk
import gti
import menus
import paintings
import up

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = os.path.join(HERE, "signs.json")
DRAW = os.path.join(HERE, "signs-draw.py")
WAY = "sign"
LIMIT = 18.0
TIMES = 4


def load_spec():
    with open(SPEC) as f:
        return json.load(f)


def laid_out(target, state, screens, sources):
    """([(path, x, y)] laid in this state, [the paths that get the drawn box]) or None when this run lacks a picture."""
    screen = screens.get(target["screen"])
    if not screen or screen["times"] != TIMES or (state and state not in screen["states"]):
        return None
    own = [tuple(piece) for piece in screen["pieces"]]
    over = [tuple(piece) for piece in screen["states"][state]] if state else []
    pieces = own + over
    if not all(path in sources for path, _, _ in pieces):
        return None
    return pieces, [path for path, _, _ in (over if state else own)]


def draw(sources, made_of, tools, work, skip):
    """{path: (file, checksum, bytes, note)} for the pieces whose lettering was drawn again.

    sources is {path: the game's data} of this run, made_of(path) gives (made
    file, its checksum), or None for a picture that was not made, skip the
    paths something else replaces.
    """
    spec = load_spec()
    screens = menus.expanded(menus.load_spec())
    wanted = []
    for target in spec["targets"]:
        for state in target["states"]:
            laid = laid_out(target, state, screens, sources)
            if laid:
                wanted.append((target, state) + laid)
    if not wanted:
        return {}
    python = desk.python_of(tools)
    if not os.access(python, os.X_OK):
        print("  signs left as made: the Python environment is missing; --fetch-desk sets it up")
        return {}

    originals, big, made_gti, ready = {}, {}, {}, []
    for target, state, pieces, into in wanted:
        label = "%s%s" % (target["name"], " (%s)" % state if state else "")
        if any(made_of(path) is None for path, _, _ in pieces):
            print("  sign %s left as made: a picture of it was not made" % label)
            continue
        for path, _, _ in pieces:
            if path not in originals:
                originals[path] = gti.to_rgba(gti.parse(sources[path]).best())
                with open(made_of(path)[0], "rb") as f:
                    made_gti[path] = gti.parse(f.read())
                big[path] = gti.to_rgba(made_gti[path].best())
        own = paintings.composed(pieces, originals, target["box"], 1)
        if hashlib.sha256(own).hexdigest() != target["fitted_sha256"].get(state):
            print("  sign %s left as made: the game's pixels are not the ones it was fitted to" % label)
            continue
        if any(big[path][:2] != (originals[path][0] * TIMES, originals[path][1] * TIMES) for path, _, _ in pieces):
            print("  sign %s left as made: it was not made %d times as large" % (label, TIMES))
            continue
        ready.append((target, state, pieces, into, own))
    if not ready:
        return {}

    folder = os.path.join(work, WAY)
    os.makedirs(folder, exist_ok=True)
    job = {"spec": SPEC, "times": TIMES, "items": []}
    for number, (target, state, pieces, into, own) in enumerate(ready):
        x0, y0, x1, y1 = target["box"]
        stem = os.path.join(folder, "%02d" % number)
        for ending, data in ((".made", paintings.composed(pieces, big, target["box"], TIMES)), (".original", own)):
            with open(stem + ending, "wb") as f:
                f.write(data)
        lies = [[x - x0, y - y0, x + originals[path][0] - x0, y + originals[path][1] - y0] for path, x, y in pieces if path in into]
        job["items"].append({"name": target["name"], "state": state, "w": x1 - x0, "h": y1 - y0, "into": lies,
                             "made": stem + ".made", "original": stem + ".original", "out": stem + ".out"})
    with open(os.path.join(folder, "job.json"), "w") as f:
        json.dump(job, f)
    said = subprocess.run([python, "-I", DRAW, os.path.join(folder, "job.json")], stdout=subprocess.PIPE, text=True)
    lines = [json.loads(line) for line in said.stdout.splitlines() if line.startswith("{")]
    if said.returncode or len(lines) != len(ready) + 1:
        print("  signs left as made: tools/signs-draw.py stopped (exit %d)" % said.returncode)
        return {}
    packages = lines.pop()
    with open(SPEC, "rb") as f:
        spec_sum = hashlib.sha256(f.read()).hexdigest()
    current = {path: bytearray(pixels) for path, (_, _, pixels) in big.items()}
    drawn_in, applied = {}, 0
    for (target, state, _, into, _), item, line in zip(ready, job["items"], lines):
        label = "%s%s" % (target["name"], " (%s)" % state if state else "")
        if line.get("why"):
            print("  sign %s left as made: %s" % (label, line["why"]))
            continue
        if line["match"] < LIMIT:
            print("  sign %s left as made: it scores %.1f dB, under %.1f" % (label, line["match"], LIMIT))
            continue
        if not line["changed"]:
            continue
        with open(item["out"], "rb") as f:
            box = f.read()
        applied += 1
        for path, x, y in [(path, x, y) for path, x, y in screens[target["screen"]]["pieces"] + sum(screens[target["screen"]]["states"].values(), [])
                           if path in into]:
            w, h, _ = big[path]
            current[path] = bytearray(paintings.laid_back(box, target["box"], TIMES, path, x, y, (w, h, bytes(current[path]))))
            drawn_in.setdefault(path, []).append({"target": target["name"], "state": state, "match": line["match"],
                                                   "made_match": line["made_match"]})
    done = {}
    for path, targets in sorted(drawn_in.items()):
        w, h, pixels = big[path]
        if bytes(current[path]) == pixels or path in skip:
            continue
        data = gti.encode_like(made_gti[path], w, h, bytes(current[path]))
        file = os.path.join(folder, "out", *up.safe_parts(path))
        os.makedirs(os.path.dirname(file), exist_ok=True)
        with open(file, "wb") as f:
            f.write(data)
        note = {"spec_sha256": spec_sum, "packages": packages, "made_sha256": made_of(path)[1], "targets": targets}
        done[path] = (file, hashlib.sha256(data).hexdigest(), len(data), note)
    print("  signs: %d of %d boxes drawn again from the game's pixels, %d pieces"
          % (applied, len(ready), len(done)))
    return done
