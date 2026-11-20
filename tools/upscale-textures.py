#!/usr/bin/env python3
"""Makes larger copies of the game's 3D textures for ./dogfighter --hd-textures.

It reads the textures from the packs in game/, resizes them 2x or 4x and
writes them as loose files to hd-textures/cache/<path in the pack>. The game
looks in a folder named cache before it looks in its packs, and the launcher
links game/cache to that folder. The packs are never changed.

Left out, because the game draws these at the size stored in the file. A
larger file would come out larger on the screen, or cut wrong:
  Graphics\\Fonts      letters are cut out of the picture by pixel position
  Graphics\\Frontend   menus, loading screens, windows, mouse cursor
  Graphics\\Ingame     the HUD and the maps
  User\\Save           pilot photos
Kept: Graphics\\Textures, Graphics\\Models, Graphics\\Backdrops and
Graphics\\Effects, which are only ever stretched over 3D shapes.

How a texture is resized:
  - Pixels with alpha 0 first get the colour of the nearest visible pixels,
    so their old colour (mostly black) is not pulled into the edge.
  - Each side gets a border of 16 pixels, cut off again afterwards, so the
    resizer sees sensible neighbours at the edge. Where the left and right
    edge (or top and bottom) match as well as two neighbouring columns do,
    the texture tiles and the border wraps around. Otherwise the border
    repeats the edge pixel.
  - Colour and alpha are resized apart. Alpha always goes through the plain
    filter. Alpha that was only ever 0 or 255 (a cut-out) is made 0 or 255
    again.
  - Mipmaps are made new, and only where the original had them.

Three ways to resize the colour, tried in this order:
  ai       Real-ESRGAN (model realesrgan-x4plus) run by upscayl-bin. It draws
           new detail. It always makes 4x; for 2x that is averaged down.
  waifu2x  waifu2x-ncnn-vulkan (model cunet, no denoising).
  plain    Lanczos from the Mac's own Accelerate framework. No new detail.
The first two need files that --fetch-tools downloads to upscale-tools/.
Their SHA-256 checksums are pinned below. Without them only plain is used.

After ai and waifu2x the result is pulled back to the original: it is shrunk
to the original size and the difference with the original is enlarged and
added. That is done twice with a smooth enlargement, then once block by
block, which makes the shrunk result equal to the original up to rounding.
So colours and shapes cannot drift.

Every result is then checked. It is shrunk to the original size (an average
of each 2x2 or 4x4 block) and compared with the original as PSNR in dB.
Border pixels and pixels with alpha 0 are not counted.
  drift   before the pull-back. Below LIMITS["drift"] the upscaler drew
          something else than the original.
  match   after the pull-back, the whole picture.
  worst   after the pull-back, the worst 8x8 block.
  seam    for a tiling texture: the mean difference between the two opposite
          edges. It may not pass twice the mean difference between
          neighbouring columns (or 4), unless the original's own seam was
          larger still.
A texture that fails goes to the next way. One that fails all three is not
written, and the game then uses its own.

hd-textures/manifest.json lists every texture: where it came from, which way
it took, its scores and the checksums of the tools.

Helpers, built with the Xcode Command Line Tools. Both read jobs on stdin as
fields that each end in a NUL byte, so a path may hold spaces.
  tools/vimage-scale.c    IN OUT WIDTH HEIGHT NEW_WIDTH NEW_HEIGHT, raw RGBA.
  tools/texture-refine.c  Prints one line per job, "ok ..." or "fail <why>".
      bleed IN OUT WIDTH HEIGHT
      refine ORIGINAL PLAIN DETAIL OUT WIDTH HEIGHT SCALE BORDER PASSES
        ORIGINAL and PLAIN are raw RGBA with the border. DETAIL is the
        upscaler's PNG, or empty for the plain way. OUT gets the colour of
        DETAIL after PASSES pull-backs and the alpha of PLAIN. The line holds
        drift, match, worst, then seam and neighbour difference across and
        down, then the original's seam across and down.
"""
import argparse
import hashlib
import json
import multiprocessing
import os
import shutil
import subprocess
import sys
import time
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gti  # noqa: E402
import up  # noqa: E402

KEPT = ("graphics\\textures\\", "graphics\\models\\", "graphics\\backdrops\\", "graphics\\effects\\")
BORDER = 16
MARKER = "texture-limit"
MANIFEST = "manifest.json"
WORK = ".upscale-work"
PIPELINE = 1
BATCH = 48
PASSES = 2
MODEL = "realesrgan-x4plus"
MODEL_SCALE = 4
TILE = 512
WAIFU2X_MODEL = "models-cunet"
WAIFU2X_TILE = 400
LIMITS = {"drift": 20.0, "match": 40.0, "worst": 30.0, "plain": 20.0}
WAYS = ("ai", "waifu2x", "plain")

ARCHIVES = (
    {
        "folder": "upscayl",
        "file": "upscayl-bin-20251207-174704-macos.zip",
        "url": "https://github.com/upscayl/upscayl-ncnn/releases/download/20251207-174704/upscayl-bin-20251207-174704-macos.zip",
        "sha256": "277419791281a56eae0c739c70120b974d7267cf7c2de8e86dc09798d4b314db",
        "members": {"upscayl-bin-20251207-174704-macos/upscayl-bin": "upscayl-bin"},
    },
    {
        "folder": "realesrgan-models",
        "file": "realesrgan-ncnn-vulkan-20220424-macos.zip",
        "url": "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesrgan-ncnn-vulkan-20220424-macos.zip",
        "sha256": "e0ad05580abfeb25f8d8fb55aaf7bedf552c375b5b4d9bd3c8d59764d2cc333a",
        "members": {
            "models/realesrgan-x4plus.bin": "realesrgan-x4plus.bin",
            "models/realesrgan-x4plus.param": "realesrgan-x4plus.param",
        },
    },
    {
        "folder": "waifu2x",
        "file": "waifu2x-ncnn-vulkan-20250915-macos.zip",
        "url": "https://github.com/nihui/waifu2x-ncnn-vulkan/releases/download/20250915/waifu2x-ncnn-vulkan-20250915-macos.zip",
        "sha256": "a5b58b239eb3aa030db5464f6759637fe412d8c07891a4346ea57f708b514d42",
        "members": {
            "waifu2x-ncnn-vulkan-20250915-macos/waifu2x-ncnn-vulkan": "waifu2x-ncnn-vulkan",
            "waifu2x-ncnn-vulkan-20250915-macos/models-cunet/scale2.0x_model.bin": "models-cunet/scale2.0x_model.bin",
            "waifu2x-ncnn-vulkan-20250915-macos/models-cunet/scale2.0x_model.param": "models-cunet/scale2.0x_model.param",
        },
    },
)
PINNED = {
    "upscayl/upscayl-bin": "b7f54f362fc10d5f334e587fb90917e95a5557ec1cfefbddce78657dd3fee055",
    "realesrgan-models/realesrgan-x4plus.bin": "713ee713b0353afaa27976f0563a64a5043bd70b9bd8936c2e26e25ebcdbcddf",
    "realesrgan-models/realesrgan-x4plus.param": "35330ececcea33b6c397a72548e788d5d53becee4734c50b7fada36e89f10a86",
    "waifu2x/waifu2x-ncnn-vulkan": "1be8cd5976ac5fbda399b1b87a9f711e430689936bdd9d6514c49fca47507005",
    "waifu2x/models-cunet/scale2.0x_model.bin": "d82ed30207fd07e1c16726a9ca838ce44e6e25a105b0278c7ca681516ee0e18e",
    "waifu2x/models-cunet/scale2.0x_model.param": "ccc3b2f1c9fad829ecdda40cac8dc853fcddf14917170efba888b256fbf9074a",
}


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def tool_checksums(tools):
    found = {}
    for name in PINNED:
        path = os.path.join(tools, *name.split("/"))
        found[name] = sha256_of(path) if os.path.isfile(path) else None
    return found


def fetch_tools(root, tools):
    """Downloads the pinned archives and unpacks only the files named in ARCHIVES, each under a name chosen here."""
    downloads = os.path.join(root, "downloads", "upscale")
    os.makedirs(downloads, exist_ok=True)
    for archive in ARCHIVES:
        path = os.path.join(downloads, archive["file"])
        if not (os.path.isfile(path) and sha256_of(path) == archive["sha256"]):
            print("Downloading " + archive["file"])
            part = path + ".part"
            done = subprocess.run(["/usr/bin/curl", "-fL", "--retry", "3", "--progress-bar", "-o", part, archive["url"]])
            if done.returncode:
                sys.exit("Download failed: " + archive["url"])
            if sha256_of(part) != archive["sha256"]:
                os.remove(part)
                sys.exit("%s does not match its pinned SHA-256 checksum. Nothing was unpacked." % archive["file"])
            os.replace(part, path)
        folder = os.path.join(tools, archive["folder"])
        shutil.rmtree(folder, ignore_errors=True)
        with zipfile.ZipFile(path) as packed:
            for member, name in archive["members"].items():
                target = os.path.join(folder, *name.split("/"))
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with open(target, "wb") as f:
                    f.write(packed.read(member))
                if "." not in os.path.basename(name):
                    os.chmod(target, 0o755)
    wrong = [name for name, found in tool_checksums(tools).items() if found != PINNED[name]]
    if wrong:
        sys.exit("These unpacked files do not match their pinned checksums: " + ", ".join(wrong))
    print("The upscalers are in %s. Their checksums match." % tools)


def column(pixels, width, x):
    return pixels[x * 4::width * 4], pixels[x * 4 + 1::width * 4], pixels[x * 4 + 2::width * 4], pixels[x * 4 + 3::width * 4]


def difference(a, b):
    return sum(abs(p - q) for one, two in zip(a, b) for p, q in zip(one, two)) / max(1, len(a[0]) * 4)


def tiles_across(pixels, width):
    """True when the right edge continues into the left edge as smoothly as the inside does."""
    if width < 4:
        return True
    step = max(1, width // 9)
    inside = [difference(column(pixels, width, x), column(pixels, width, x + 1)) for x in range(step, width - 1, step)]
    seam = difference(column(pixels, width, 0), column(pixels, width, width - 1))
    return seam <= max(4.0, 2.0 * sum(inside) / max(1, len(inside)))


def turned(pixels, width, height):
    """Rows become columns, so the test for left and right also answers top and bottom."""
    out = bytearray(len(pixels))
    for x in range(width):
        for c in range(4):
            out[x * height * 4 + c:(x + 1) * height * 4:4] = pixels[x * 4 + c::width * 4]
    return bytes(out)


def with_border(pixels, width, height, wrap_x, wrap_y):
    rows = []
    for y in range(height):
        row = pixels[y * width * 4:(y + 1) * width * 4]
        if wrap_x:
            many = row * (BORDER // width + 1)
            rows.append(many[-BORDER * 4:] + row + many[:BORDER * 4])
        else:
            rows.append(row[:4] * BORDER + row + row[-4:] * BORDER)
    if wrap_y:
        many = rows * (BORDER // height + 1)
        rows = many[-BORDER:] + rows + many[:BORDER]
    else:
        rows = rows[:1] * BORDER + rows + rows[-1:] * BORDER
    return b"".join(rows)


def without_border(pixels, width, height, edge):
    full = width + 2 * edge
    return b"".join(pixels[((y + edge) * full + edge) * 4:((y + edge) * full + edge + width) * 4] for y in range(height))


def finish(job):
    """Runs in a worker: cut the border off, tidy alpha, write the .gti."""
    scale, edge = job["scale"], BORDER * job["scale"]
    width, height = job["width"] * scale, job["height"] * scale
    with open(job["scaled"], "rb") as f:
        pixels = bytearray(f.read())
    if len(pixels) != (width + 2 * edge) * (height + 2 * edge) * 4:
        raise ValueError("%s: resized picture has the wrong size" % job["path"])
    if job["kind"] == "cutout":
        pixels[3::4] = pixels[3::4].translate(bytes(255 if i >= 128 else 0 for i in range(256)))
    pixels = without_border(bytes(pixels), width, height, edge)
    data = gti.encode(width, height, pixels, job["alpha"], None if job["mipmaps"] else 1)
    os.makedirs(os.path.dirname(job["target"]), exist_ok=True)
    with open(job["target"], "wb") as f:
        f.write(data)
    return job["path"], len(data), hashlib.sha256(data).hexdigest()


def build_helpers(work):
    built = {}
    for name, frameworks in (("vimage-scale", ("Accelerate",)), ("texture-refine", ("ImageIO", "CoreGraphics", "CoreFoundation"))):
        built[name] = os.path.join(work, name)
        command = ["/usr/bin/cc", "-O2", "-o", built[name], os.path.join(HERE, name + ".c")]
        for framework in frameworks:
            command += ["-framework", framework]
        try:
            subprocess.run(command, check=True)
        except (OSError, subprocess.CalledProcessError):
            sys.exit("Could not build tools/%s.c. Install the Xcode Command Line Tools: xcode-select --install" % name)
    return built


def run_jobs(helper, fields, lines=False):
    done = subprocess.run([helper], input=b"".join(os.fsencode(str(field)) + b"\0" for field in fields),
                          stdout=subprocess.PIPE if lines else None, check=True)
    return done.stdout.decode().splitlines() if lines else []


def run_upscaler(way, tools, source, target, scale, work):
    if way == "ai":
        command = [os.path.join(tools, "upscayl", "upscayl-bin"), "-i", source, "-o", target,
                   "-m", os.path.join(tools, "realesrgan-models"), "-n", MODEL,
                   "-z", str(MODEL_SCALE), "-s", str(MODEL_SCALE), "-t", str(TILE), "-f", "png"]
    else:
        command = [os.path.join(tools, "waifu2x", "waifu2x-ncnn-vulkan"), "-i", source, "-o", target,
                   "-m", os.path.join(tools, "waifu2x", WAIFU2X_MODEL), "-n", "-1",
                   "-s", str(scale), "-t", str(WAIFU2X_TILE), "-f", "png"]
    done = subprocess.run(command, cwd=work, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if not os.listdir(target):
        said = done.stderr.decode(errors="replace").strip().splitlines()[-6:]
        sys.exit("%s made no pictures (exit %d). Nothing was replaced.\n%s" % (command[0], done.returncode, "\n".join(said)))


def verdict(way, scores, wrap_x, wrap_y):
    """None when the result may be written, else the reason it may not."""
    if way == "plain":
        if scores["match"] < LIMITS["plain"]:
            return "match %.1f dB is under %.1f" % (scores["match"], LIMITS["plain"])
    else:
        for name in ("drift", "match", "worst"):
            if scores[name] < LIMITS[name]:
                return "%s %.1f dB is under %.1f" % (name, scores[name], LIMITS[name])
    for wraps, axis in ((wrap_x, "x"), (wrap_y, "y")):
        seam, inside, before = scores["seam_" + axis], scores["inside_" + axis], scores["original_seam_" + axis]
        if wraps and seam > max(4.0, 2.0 * inside, before):
            return "seam %s %.1f against %.1f inside" % (axis, seam, inside)
    return None


def prepare(number, pack, entry, data, scale, folder, fresh):
    best = gti.parse(data).best()
    width, height, pixels = gti.to_rgba(best)
    record = {"path": entry.path, "pack": os.path.basename(pack.path), "source_sha256": hashlib.sha256(data).hexdigest(),
              "size": [width, height]}
    if width * scale > 1024 or height * scale > 1024:
        record.update(way="none", why="would pass 1024 pixels")
        return None, record
    alphas = set(pixels[3::4]) if best.alpha else {255}
    wrap_x = tiles_across(pixels, width)
    wrap_y = tiles_across(turned(pixels, width, height), height)
    kind = "opaque" if not best.alpha else "cutout" if alphas <= {0, 255} else "alpha"
    record.update(kind=kind, tiles=[wrap_x, wrap_y])
    stem = os.path.join(folder, "%05d" % number)
    job = {
        "path": entry.path, "number": number, "scale": scale, "width": width, "height": height,
        "alpha": best.alpha, "mipmaps": len(best.levels) > 1, "kind": kind,
        "wrap_x": wrap_x, "wrap_y": wrap_y, "bleed": 0 in alphas and len(alphas) > 1,
        "source": stem + ".in", "plain": stem + ".plain", "stem": stem,
        "target": os.path.join(fresh, *up.safe_parts(entry.path)),
    }
    with open(job["source"], "wb") as f:
        f.write(with_border(pixels, width, height, wrap_x, wrap_y))
    return job, record


def run_batch(setup, items, fresh, pool):
    """Takes a list of (number, pack, entry, data) all the way to .gti files. Returns one record per texture."""
    scale, helpers = setup["scale"], setup["helpers"]
    folder = os.path.join(setup["work"], "batch")
    shutil.rmtree(folder, ignore_errors=True)
    os.makedirs(folder)
    jobs, records = [], {}
    for number, pack, entry, data in items:
        job, record = prepare(number, pack, entry, data, scale, folder, fresh)
        records[entry.path] = record
        if job:
            jobs.append(job)

    fields = []
    for job in jobs:
        if job["bleed"]:
            fields += ["bleed", job["source"], job["source"], job["width"] + 2 * BORDER, job["height"] + 2 * BORDER]
    if "fail" in [line.split()[0] for line in run_jobs(helpers["texture-refine"], fields, True)]:
        sys.exit("tools/texture-refine.c could not prepare a texture. Nothing was replaced.")
    fields = []
    for job in jobs:
        full_w, full_h = job["width"] + 2 * BORDER, job["height"] + 2 * BORDER
        fields += [job["source"], job["plain"], full_w, full_h, full_w * scale, full_h * scale]
    run_jobs(helpers["vimage-scale"], fields)

    waiting = jobs
    for way in setup["ways"]:
        if not waiting:
            break
        if way != "plain":
            source, target = os.path.join(folder, way + "-in"), os.path.join(folder, way + "-out")
            os.makedirs(source)
            os.makedirs(target)
            for job in waiting:
                with open(job["source"], "rb") as f:
                    bordered = f.read()
                with open(os.path.join(source, "%05d.png" % job["number"]), "wb") as f:
                    f.write(gti.write_png(job["width"] + 2 * BORDER, job["height"] + 2 * BORDER, bordered, False))
            run_upscaler(way, setup["tools"], source, target, scale, setup["work"])
        fields = []
        for job in waiting:
            detail = os.path.join(folder, way + "-out", "%05d.png" % job["number"]) if way != "plain" else ""
            fields += ["refine", job["source"], job["plain"], detail, "%s.%s" % (job["stem"], way),
                       job["width"] + 2 * BORDER, job["height"] + 2 * BORDER, scale, BORDER, 0 if way == "plain" else PASSES]
        lines = run_jobs(helpers["texture-refine"], fields, True)
        if len(lines) != len(waiting):
            sys.exit("tools/texture-refine.c answered %d of %d jobs. Nothing was replaced." % (len(lines), len(waiting)))
        still = []
        for job, line in zip(waiting, lines):
            record = records[job["path"]]
            if line.startswith("ok "):
                names = ("drift", "match", "worst", "seam_x", "inside_x", "seam_y", "inside_y", "original_seam_x", "original_seam_y")
                scores = dict(zip(names, (float(value) for value in line.split()[1:])))
                why = verdict(way, scores, job["wrap_x"], job["wrap_y"])
            else:
                scores, why = None, line[5:]
            if why is None:
                job["scaled"] = "%s.%s" % (job["stem"], way)
                record.update(way=way, scores=scores)
            else:
                record.setdefault("failed", []).append({"way": way, "why": why, "scores": scores})
                still.append(job)
        waiting = still
    for job in waiting:
        records[job["path"]].update(way="none", why="failed every check")

    written = [job for job in jobs if "scaled" in job]
    for path, size, digest in pool.imap_unordered(finish, written, 8):
        records[path].update(out=[records[path]["size"][0] * scale, records[path]["size"][1] * scale], bytes=size, file_sha256=digest)
    shutil.rmtree(folder, ignore_errors=True)
    return [records[entry.path] for _, _, entry, _ in items]


def spread(values):
    values = sorted(values)
    return "lowest %.1f, 5%% under %.1f, middle %.1f" % (values[0], values[len(values) // 20], values[len(values) // 2])


def summary(records):
    counts = {way: sum(1 for record in records if record["way"] == way) for way in WAYS + ("none",)}
    print("Ways: %d ai, %d waifu2x, %d plain, %d not written." % tuple(counts[way] for way in WAYS + ("none",)))
    for way in WAYS:
        scored = [record["scores"] for record in records if record["way"] == way]
        if scored:
            print("  %-8s match dB: %s" % (way, spread([s["match"] for s in scored])))
            if way != "plain":
                print("  %-8s drift dB: %s" % (way, spread([s["drift"] for s in scored])))
                print("  %-8s worst dB: %s" % (way, spread([s["worst"] for s in scored])))
    for record in records:
        if record["way"] == "none":
            print("  not written: %s (%s)" % (record["path"], record["why"]))
    return counts


def main():
    root = os.path.dirname(HERE)
    parser = argparse.ArgumentParser(description="Make larger textures for ./dogfighter --hd-textures.")
    parser.add_argument("--scale", type=int, choices=(2, 4), default=2, help="2 (default) or 4")
    parser.add_argument("--upscaler", choices=("auto", "ai", "vimage"), default="auto",
                        help="auto (default) uses the fetched upscalers if they are there, else the Mac's own vimage")
    parser.add_argument("--fetch-tools", action="store_true", help="download the pinned upscalers to upscale-tools/, then stop")
    parser.add_argument("--tools", default=os.path.join(root, "upscale-tools"), help="folder with the upscalers (default: upscale-tools/)")
    parser.add_argument("--allow-other-tools", action="store_true", help="run upscalers whose checksums are not the pinned ones")
    parser.add_argument("--game", default=os.path.join(root, "game"), help="the installed game (default: game/)")
    parser.add_argument("--out", default=os.path.join(root, "hd-textures"), help="output folder (default: hd-textures/)")
    parser.add_argument("--only", default="", help="only textures whose path contains this text")
    parser.add_argument("--jobs", type=int, default=os.cpu_count() or 4, help="worker processes")
    parser.add_argument("--repeat", type=int, default=8, help="textures to make a second time, to see that the result is the same (default 8)")
    parser.add_argument("--sheets", default="", help="folder for PNG sheets that put the plain filter next to the set")
    parser.add_argument("--list", action="store_true", help="show what would be resized, then stop")
    args = parser.parse_args()
    tools = os.path.abspath(args.tools)

    if args.fetch_tools:
        fetch_tools(root, tools)
        return
    packs = sorted(os.path.join(args.game, name) for name in os.listdir(args.game) if name.lower().endswith(".up"))
    if not packs:
        sys.exit("No .up packs in %s. Run ./setup.sh first." % args.game)

    checksums = tool_checksums(tools)
    ways = ("plain",)
    if args.upscaler != "vimage":
        missing = [name for name, found in checksums.items() if found is None]
        wrong = [name for name, found in checksums.items() if found not in (None, PINNED[name])]
        if missing and args.upscaler == "ai":
            sys.exit("Not in %s: %s. Fetch them with: python3 tools/upscale-textures.py --fetch-tools" % (tools, ", ".join(missing)))
        if missing:
            print("The upscalers are not in %s, so only the plain filter is used." % tools)
        elif wrong and not args.allow_other_tools:
            sys.exit("These files do not match their pinned checksums: %s.\n"
                     "Fetch them again with --fetch-tools, or pass --allow-other-tools to run them anyway." % ", ".join(wrong))
        else:
            ways = WAYS

    chosen, left_out = [], {}
    for path in packs:
        pack = up.Pack(path)
        pack.path = path
        for entry in pack.entries:
            if not entry.name.lower().endswith(".gti"):
                continue
            try:
                up.safe_parts(entry.path)
            except ValueError as problem:
                sys.exit("%s: %s. Nothing was written." % (path, problem))
            if not entry.path.lower().startswith(KEPT):
                folder = "\\".join(entry.folder.split("\\")[:2])
                left_out[folder] = left_out.get(folder, 0) + 1
            elif args.only.lower() in entry.path.lower():
                chosen.append((pack, entry))
    print("%d textures to resize %dx. Ways: %s." % (len(chosen), args.scale, ", then ".join(ways)))
    for folder in sorted(left_out):
        print("  left out: %4d in %s" % (left_out[folder], folder))
    if args.list:
        for _, entry in chosen:
            print(entry.path)
        return
    if not chosen:
        sys.exit("Nothing to do.")

    settings = {"pipeline": PIPELINE, "scale": args.scale, "border": BORDER, "ways": list(ways), "limits": LIMITS}
    if len(ways) > 1:
        settings.update(passes=PASSES, model=MODEL, model_scale=MODEL_SCALE, tile=TILE,
                        waifu2x_model=WAIFU2X_MODEL, waifu2x_tile=WAIFU2X_TILE, tools=checksums)
    key = hashlib.sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest()

    cache = os.path.join(args.out, "cache")
    if os.path.exists(cache) and not os.path.exists(os.path.join(args.out, MARKER)):
        sys.exit("%s exists and was not made by this tool. Move it away first." % cache)
    os.makedirs(args.out, exist_ok=True)
    work = os.path.join(args.out, "%s-%s" % (WORK, key[:16]))
    for name in os.listdir(args.out):
        if name.startswith(WORK) and os.path.join(args.out, name) != work:
            shutil.rmtree(os.path.join(args.out, name), ignore_errors=True)
    os.makedirs(work, exist_ok=True)
    setup = {"scale": args.scale, "ways": ways, "tools": tools, "work": work, "helpers": build_helpers(work)}
    sources = [(pack, entry, pack.read(entry)) for pack, entry in chosen]
    if not complete(args.out, key, sources):
        build(args, setup, settings, key, sources, cache)
    shutil.rmtree(work, ignore_errors=True)
    if args.sheets:
        sheets(args, setup["scale"], sources, cache)


def complete(out, key, sources):
    """True when the set in out was made with these settings from these very textures."""
    try:
        with open(os.path.join(out, MANIFEST)) as f:
            manifest = json.load(f)
    except (OSError, ValueError):
        return False
    known = {record["path"]: record for record in manifest.get("textures", [])}
    if manifest.get("key") != key or len(known) != len(sources):
        return False
    for _, entry, data in sources:
        record = known.get(entry.path)
        if not record or record["source_sha256"] != hashlib.sha256(data).hexdigest():
            return False
        if record["way"] != "none" and not os.path.isfile(os.path.join(out, "cache", *up.safe_parts(entry.path))):
            return False
    print("The set in %s is already complete with these settings. Nothing to do." % out)
    summary(manifest["textures"])
    return True


def build(args, setup, settings, key, sources, cache):
    """Makes the whole set in work/cache. The old set is replaced only when every texture is done."""
    work = setup["work"]
    fresh = os.path.join(work, "cache")
    log = os.path.join(work, "done.jsonl")
    started = time.time()

    done = {}
    if os.path.exists(log):
        with open(log) as f:
            for line in f:
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                done[record["path"]] = record
    todo, records = [], {}
    for number, (pack, entry, data) in enumerate(sources):
        record = done.get(entry.path)
        target = os.path.join(fresh, *up.safe_parts(entry.path))
        if record and record["source_sha256"] == hashlib.sha256(data).hexdigest() and (
                record["way"] == "none" or (os.path.isfile(target) and sha256_of(target) == record["file_sha256"])):
            records[entry.path] = record
        else:
            todo.append((number, pack, entry, data))
    if records:
        print("%d textures were already done in an earlier run that stopped." % len(records))

    with multiprocessing.Pool(max(1, args.jobs)) as pool:
        for at in range(0, len(todo), BATCH):
            made = run_batch(setup, todo[at:at + BATCH], fresh, pool)
            with open(log, "a") as f:
                for record in made:
                    records[record["path"]] = record
                    f.write(json.dumps(record, sort_keys=True) + "\n")
            print("  %d of %d, %.0f seconds" % (min(at + BATCH, len(todo)), len(todo), time.time() - started), flush=True)

        ordered = [records[entry.path] for _, entry, _ in sources]
        again = [item for item in enumerate(sources) if records[item[1][1].path]["way"] != "none"]
        again = again[::max(1, len(again) // max(1, args.repeat))][:args.repeat] if args.repeat > 0 else []
        repeat = None
        if again:
            second = run_batch(setup, [(number, pack, entry, data) for number, (pack, entry, data) in again],
                               os.path.join(work, "repeat"), pool)
            same = sum(1 for record in second if record.get("file_sha256") == records[record["path"]]["file_sha256"])
            repeat = {"textures": len(second), "identical": same}
            print("Made %d textures a second time: %d came out byte for byte the same." % (len(second), same))
            if same != len(second):
                print("WARNING: the upscaler does not give the same result twice on this Mac.")

    took = time.time() - started
    counts = summary(ordered)
    if counts["none"] == len(ordered):
        sys.exit("No texture passed its checks. Nothing was replaced.")
    largest = max(max(record["out"]) for record in ordered if record["way"] != "none")
    limit = 512 if largest <= 512 else 1024
    manifest = {"key": key, "settings": settings, "tools_are_the_pinned_ones": settings.get("tools", PINNED) == PINNED,
                "counts": counts, "repeat": repeat, "seconds": round(took), "textures": ordered}
    with open(os.path.join(work, MANIFEST), "w") as f:
        json.dump(manifest, f, indent=1, sort_keys=True)
    old = os.path.join(work, "old")
    if os.path.exists(cache):
        os.rename(cache, old)
    os.rename(fresh, cache)
    os.replace(os.path.join(work, MANIFEST), os.path.join(args.out, MANIFEST))
    with open(os.path.join(args.out, MARKER), "w") as f:
        f.write("%d\n" % limit)
    written = sum(record.get("bytes", 0) for record in ordered)
    print("%d textures, %.0f MB, in %s. Took %.0f seconds." % (len(ordered) - counts["none"], written / 1e6, cache, took))
    print("Largest side: %d pixels. Play with: ./dogfighter --hd-textures" % largest)


def on_squares(pixels, width, height):
    """RGB bytes of an RGBA picture laid over grey squares, so alpha can be seen."""
    out = bytearray(width * height * 3)
    for y in range(height):
        for x in range(width):
            r, g, b, a = pixels[(y * width + x) * 4:(y * width + x) * 4 + 4]
            under = 150 if (x // 8 + y // 8) % 2 else 100
            at = (y * width + x) * 3
            out[at], out[at + 1], out[at + 2] = ((r * a + under * (255 - a)) // 255, (g * a + under * (255 - a)) // 255,
                                                 (b * a + under * (255 - a)) // 255)
    return bytes(out)


def sheets(args, scale, sources, cache):
    """One PNG per texture: the plain filter on the left, the set on the right. A tiling texture is laid out 2x2."""
    with open(os.path.join(args.out, MANIFEST)) as f:
        records = [record for record in json.load(f)["textures"] if record["way"] != "none"]
    groups = (
        ("tiling", 3, lambda r: all(r["tiles"]) and r["kind"] == "opaque" and r["path"].lower().startswith(KEPT[0])),
        ("cutout", 2, lambda r: r["kind"] == "cutout"),
        ("alpha", 3, lambda r: r["kind"] == "alpha" and "\\effects\\" not in r["path"].lower()),
        ("model", 2, lambda r: r["kind"] == "opaque" and "\\models\\" in r["path"].lower() and not all(r["tiles"])),
        ("effect", 1, lambda r: "\\effects\\" in r["path"].lower()),
        ("backdrop", 1, lambda r: "\\backdrops\\" in r["path"].lower()),
    )
    picked = []
    for label, count, test in groups:
        fitting = sorted((r for r in records if test(r) and r not in [p[1] for p in picked]),
                         key=lambda r: (r["way"] != "ai", -min(r["size"]), r["path"]))
        picked += [(label, record) for record in fitting[::max(1, len(fitting) // (4 * count))][:count]]
    by_path = {entry.path: data for _, entry, data in sources}
    os.makedirs(args.sheets, exist_ok=True)
    work = os.path.join(args.out, WORK + "-sheets")
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    helper = build_helpers(work)["vimage-scale"]
    for number, (label, record) in enumerate(picked):
        width, height, pixels = gti.to_rgba(gti.parse(by_path[record["path"]]).best())
        with open(os.path.join(work, "in"), "wb") as f:
            f.write(pixels)
        run_jobs(helper, [os.path.join(work, "in"), os.path.join(work, "out"), width, height, width * scale, height * scale])
        with open(os.path.join(work, "out"), "rb") as f:
            plain = f.read()
        with open(os.path.join(cache, *up.safe_parts(record["path"])), "rb") as f:
            _, _, made = gti.to_rgba(gti.parse(f.read()).best())
        width, height = width * scale, height * scale
        times = 2 if all(record["tiles"]) and label == "tiling" else 1
        zoom = max(1, 512 // (max(width, height) * times))
        halves = []
        for picture in (plain, made):
            rgb = on_squares(picture, width, height)
            rows = []
            for y in range(height):
                row = rgb[y * width * 3:(y + 1) * width * 3]
                wide = b"".join(row[x * 3:x * 3 + 3] * zoom for x in range(width)) * times
                rows += [wide] * zoom
            halves.append(rows * times)
        gap = b"\xff\x00\xff" * 8
        rgb = b"".join(left + gap + right for left, right in zip(*halves))
        full_w = 2 * width * zoom * times + 8
        rgba = bytearray(len(rgb) // 3 * 4)
        rgba[0::4], rgba[1::4], rgba[2::4] = rgb[0::3], rgb[1::3], rgb[2::3]
        name = "%02d-%s-%s-%s.png" % (number + 1, label, record["way"], os.path.splitext(record["path"].split("\\")[-1])[0])
        with open(os.path.join(args.sheets, name), "wb") as f:
            f.write(gti.write_png(full_w, height * zoom * times, bytes(rgba), False))
        print("  sheet: %s  (%s, drift %.1f dB)" % (name, record["path"], record["scores"]["drift"]))
    shutil.rmtree(work, ignore_errors=True)
    print("%d sheets in %s: plain filter left, the set right." % (len(picked), args.sheets))


if __name__ == "__main__":
    main()
