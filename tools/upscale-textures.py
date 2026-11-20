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
  - Each side gets a border of 8 pixels first, cut off again afterwards, so
    the resize filter sees sensible neighbours at the edge. Where the left
    and right edge (or top and bottom) match as well as two neighbouring
    columns do, the texture tiles and the border wraps around. Otherwise the
    border repeats the edge pixel.
  - Colour and alpha are resized as separate channels. Colour under
    transparent pixels is kept as it was.
  - Alpha that was only ever 0 or 255 (a cut-out) is made 0 or 255 again.
  - Mipmaps are made new, and only where the original had them.

Resizers:
  vimage      Lanczos from the Mac's own Accelerate framework. Smooth edges,
              no new detail. Built from tools/vimage-scale.c with the Xcode
              Command Line Tools. Jobs go to it on stdin, one per line:
              IN OUT WIDTH HEIGHT NEW_WIDTH NEW_HEIGHT, raw RGBA bytes.
  realesrgan  realesrgan-ncnn-vulkan, if it is on the PATH. It draws new
              detail. It is never downloaded. Alpha still goes through vimage.
"""
import argparse
import multiprocessing
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gti  # noqa: E402
import up  # noqa: E402

KEPT = ("graphics\\textures\\", "graphics\\models\\", "graphics\\backdrops\\", "graphics\\effects\\")
BORDER = 8
MARKER = "texture-limit"
ESRGAN = "realesrgan-ncnn-vulkan"
ESRGAN_SCALE = 4


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
    full = (width + 2 * edge) * (height + 2 * edge) * 4
    with open(job["scaled"], "rb") as f:
        pixels = bytearray(f.read())
    if len(pixels) != full:
        raise ValueError("%s: resized picture has the wrong size" % job["path"])
    if job.get("detail"):
        with open(job["detail"], "rb") as f:
            w, h, rgba, _ = gti.read_png(f.read())
        for _ in range(ESRGAN_SCALE // scale // 2):
            w, h, rgba = gti.halve(w, h, rgba, 4)
        if len(rgba) != full:
            raise ValueError("%s: %s made a picture of the wrong size" % (job["path"], ESRGAN))
        pixels[0::4], pixels[1::4], pixels[2::4] = rgba[0::4], rgba[1::4], rgba[2::4]
    if job["cutout"]:
        pixels[3::4] = pixels[3::4].translate(bytes(255 if i >= 128 else 0 for i in range(256)))
    pixels = without_border(bytes(pixels), width, height, edge)
    data = gti.encode(width, height, pixels, job["alpha"], None if job["mipmaps"] else 1)
    os.makedirs(os.path.dirname(job["target"]), exist_ok=True)
    with open(job["target"], "wb") as f:
        f.write(data)
    return len(data)


def build_helper(work):
    helper = os.path.join(work, "vimage-scale")
    try:
        subprocess.run(["/usr/bin/cc", "-O2", "-o", helper, os.path.join(HERE, "vimage-scale.c"),
                        "-framework", "Accelerate"], check=True)
    except (OSError, subprocess.CalledProcessError):
        sys.exit("Could not build tools/vimage-scale.c. Install the Xcode Command Line Tools: xcode-select --install")
    return helper


def main():
    root = os.path.dirname(HERE)
    parser = argparse.ArgumentParser(description="Make larger textures for ./dogfighter --hd-textures.")
    parser.add_argument("--scale", type=int, choices=(2, 4), default=2, help="2 (default) or 4")
    parser.add_argument("--upscaler", choices=("auto", "vimage", "realesrgan"), default="auto",
                        help="auto (default) uses %s if it is installed, else the Mac's own vimage" % ESRGAN)
    parser.add_argument("--model", default="realesrgan-x4plus", help="model name for %s" % ESRGAN)
    parser.add_argument("--game", default=os.path.join(root, "game"), help="the installed game (default: game/)")
    parser.add_argument("--out", default=os.path.join(root, "hd-textures"), help="output folder (default: hd-textures/)")
    parser.add_argument("--only", default="", help="only textures whose path contains this text")
    parser.add_argument("--jobs", type=int, default=os.cpu_count() or 4, help="worker processes")
    parser.add_argument("--list", action="store_true", help="show what would be resized, then stop")
    args = parser.parse_args()

    packs = sorted(os.path.join(args.game, name) for name in os.listdir(args.game) if name.lower().endswith(".up"))
    if not packs:
        sys.exit("No .up packs in %s. Run ./setup.sh first." % args.game)
    esrgan = shutil.which(ESRGAN)
    if args.upscaler == "realesrgan" and not esrgan:
        sys.exit("%s is not on the PATH." % ESRGAN)
    use_esrgan = bool(esrgan) and args.upscaler != "vimage"

    chosen, left_out = [], {}
    for path in packs:
        pack = up.Pack(path)
        for entry in pack.entries:
            if not entry.name.lower().endswith(".gti"):
                continue
            if not entry.path.lower().startswith(KEPT):
                folder = "\\".join(entry.folder.split("\\")[:2])
                left_out[folder] = left_out.get(folder, 0) + 1
            elif args.only.lower() in entry.path.lower():
                chosen.append((pack, entry))
    print("%d textures to resize %dx with %s." % (len(chosen), args.scale, ESRGAN if use_esrgan else "vimage"))
    for folder in sorted(left_out):
        print("  left out: %4d in %s" % (left_out[folder], folder))
    if args.list:
        for _, entry in chosen:
            print(entry.path)
        return
    if not chosen:
        sys.exit("Nothing to do.")

    cache = os.path.join(args.out, "cache")
    work = os.path.join(args.out, ".upscale-work")
    if os.path.exists(cache) and not os.path.exists(os.path.join(args.out, MARKER)):
        sys.exit("%s exists and was not made by this tool. Move it away first." % cache)
    for folder in (cache, work):
        shutil.rmtree(folder, ignore_errors=True)
    os.makedirs(os.path.join(work, "colour"))
    helper = build_helper(work)

    started = time.time()
    jobs, lines, largest = [], [], 0
    for number, (pack, entry) in enumerate(chosen):
        best = gti.parse(pack.read(entry)).best()
        width, height, pixels = gti.to_rgba(best)
        if width * args.scale > 1024 or height * args.scale > 1024:
            print("  skipped, would pass 1024 pixels: " + entry.path)
            continue
        wrap_x = tiles_across(pixels, width)
        wrap_y = tiles_across(turned(pixels, width, height), height)
        bordered = with_border(pixels, width, height, wrap_x, wrap_y)
        full_w, full_h = width + 2 * BORDER, height + 2 * BORDER
        job = {
            "path": entry.path, "scale": args.scale, "width": width, "height": height,
            "alpha": best.alpha, "mipmaps": len(best.levels) > 1,
            "cutout": best.alpha and set(pixels[3::4]) <= {0, 255},
            "scaled": os.path.join(work, "%05d.out" % number),
            "target": os.path.join(cache, *entry.path.split("\\")),
        }
        source = os.path.join(work, "%05d.in" % number)
        with open(source, "wb") as f:
            f.write(bordered)
        lines.append("%s %s %d %d %d %d" % (source, job["scaled"], full_w, full_h, full_w * args.scale, full_h * args.scale))
        if use_esrgan:
            with open(os.path.join(work, "colour", "%05d.png" % number), "wb") as f:
                f.write(gti.write_png(full_w, full_h, bordered, False))
            job["detail"] = os.path.join(work, "detail", "%05d.png" % number)
        jobs.append(job)
        largest = max(largest, width * args.scale, height * args.scale)

    subprocess.run([helper], input="\n".join(lines).encode(), check=True)
    if use_esrgan:
        os.makedirs(os.path.join(work, "detail"))
        subprocess.run([esrgan, "-i", os.path.join(work, "colour"), "-o", os.path.join(work, "detail"),
                        "-n", args.model, "-s", str(ESRGAN_SCALE), "-f", "png"], check=True)

    with multiprocessing.Pool(max(1, args.jobs)) as pool:
        written = sum(pool.imap_unordered(finish, jobs, 8))
    shutil.rmtree(work, ignore_errors=True)
    limit = 512 if largest <= 512 else 1024
    with open(os.path.join(args.out, MARKER), "w") as f:
        f.write("%d\n" % limit)
    print("%d textures, %.0f MB, in %s. Took %.0f seconds." % (len(jobs), written / 1e6, cache, time.time() - started))
    print("Largest side: %d pixels. Play with: ./dogfighter --hd-textures" % largest)


if __name__ == "__main__":
    main()
