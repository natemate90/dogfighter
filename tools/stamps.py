"""Draws the ink stamps on the mission books again, for tools/upscale-textures.py.

The Axis and the US Airforce pages of the mission book carry a round ink
stamp, about 60 pixels wide, which the upscaler turns to mush. So after the
book pictures are made 4x, each stamp is drawn again sharp, as ink on the
page: rings, and an emblem drawn from a public-domain SVG file.
tools/stamps-draw.py does the drawing in the desk's Python environment
(tools/desk.py), which --fetch-tools and --fetch-stamps set up. Nothing is
drawn by AI.

The Axis stamp shows the Reichsadler on a wreathed swastika, as the game's
picture does. The US stamp shows the "Hap Arnold" winged star of the US Army
Air Forces in place of the game's seal of 1947, which is too late for the
war. The words in the rings cannot be read in the game, so the rings are
drawn plain. The Allies page's RAF eagle stays as made: drawn again from the
game's 66 by 20 pixels it came out blotchier than the made picture, and no
public-domain drawing of that badge in the game's pose was found.

tools/stamps.json
  references  each emblem by name: its url, its SHA-256 and what it shows.
              --fetch-tools and --fetch-stamps put it in
              upscale-tools/stamps/references/<name>.svg.
  look        how the stamps are printed: the seed of the noise, how the
              game's ink is found and the paper under it drawn again (in the
              game's pixels and the stamp's units), how far from the box's
              edges the new paper fades out and the largest step in
              brightness allowed there (in levels of 255), how rough the ink's
              edges, how patchy and how specked it is (sizes in the made
              picture's pixels).
  stamps      each stamp: the colour of its ink on white paper, and its
              layers. A ring is two radii in the stamp's units, where 1 is
              the outer edge. An emblem names its reference, the part of the
              drawing (from, in its own units), where that part goes (to, in
              the stamp's units), and inks: how much ink each colour of the
              drawing stands for, 1 full and 0 bare paper. strength is how
              strongly a layer prints.
  targets     each picture with a stamp: its name, the picture, box (the
              part of it that is drawn, in the game's pixels), the stamp,
              corners (where the corners of the stamp's square, -1 to 1 each
              way, lie in the game's pixels) and fitted_sha256 (the
              checksums of the game's own pixels in box, one for each
              language whose pixels differ there).

A target is left as made, and the run says why in one line, when the game's
pixels in its box are not the fitted ones, its picture was not made 4x, the
Python environment or an emblem is missing, the drawn stamp scores under
LIMIT: its PSNR in the box against the game's own picture, after shrinking by
block average, or its paper steps in brightness against the made picture
near an edge of the box by more than edge_step.

A piece whose pixels change is listed in the manifest with way "stamp", with
a note as tools/paintings.py describes.
"""
import json
import os

import desk
import paintings

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = os.path.join(HERE, "stamps.json")
DRAW = os.path.join(HERE, "stamps-draw.py")
WAY = "stamp"
FOLDER = "stamps"
LIMIT = 14.0


def load_spec():
    with open(SPEC) as f:
        return json.load(f)


def reference_file(tools, name, ref):
    return os.path.join(tools, FOLDER, "references", name + ".svg")


def references(target, spec):
    return [layer["reference"] for layer in spec["stamps"][target["stamp"]]["layers"] if "reference" in layer]


def fetch(tools, download, python_env):
    """Sets up the desk's Python environment and downloads the emblems. Returns False when a part failed."""
    good = desk.fetch_pictures(tools, download, python_env, load_spec()["references"],
                               lambda name, ref: reference_file(tools, name, ref))
    if good:
        print("The emblems for the stamps are in %s." % os.path.join(tools, FOLDER))
    else:
        print("A stamp whose emblem is missing stays as made.")
    return good


def draw(sources, made_of, tools, work, out, old, skip):
    """{path: (file, checksum, bytes, note)} for the pieces whose stamp was drawn again; see paintings.draw_targets."""
    spec = load_spec()
    step = {"spec": SPEC, "draw": DRAW, "way": WAY, "limit": LIMIT, "word": "stamp", "flag": "--fetch-stamps",
            "from": "as ink", "file": reference_file, "references": lambda target: references(target, spec)}
    return paintings.draw_targets(step, sources, made_of, tools, work, out, old, skip)
