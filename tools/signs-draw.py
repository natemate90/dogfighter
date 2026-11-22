"""Draws the hand lettering of the menu signs and paper headings again, for tools/signs.py.

It runs in the desk's Python environment, upscale-tools/desk/venv, which has
numpy and Pillow, and takes one argument: a job file that tools/signs.py
writes. For each item the job names the game's own pixels and the made 4x
pixels of a box as raw RGBA, and the target's ink and other inks.

How a box is drawn, from the game's pixels alone:
  - The paper is the median colour of the lighter part of the box. The ink
    is the mean colour of the few percent of the pixels that lean most from
    the paper to the target's ink, among the pictures the box is drawn into.
    So a highlight, which the game draws lighter, gets its own lighter ink.
  - The sheet is found first: the largest patch of joined paper-coloured
    pixels, and everything inside its convex hull.
    Wood, cork or desk round a sign is not touched.
  - Each game pixel is split into paper and inks: how much of the lettering's
    ink and of each other ink (a black frame, say) it holds. The paper under
    the lettering is filled from the paper around it, then the split is made
    again against that paper.
  - The lettering's share is enlarged 4x the smooth way and cut at a level
    with a soft edge. The level is the one that keeps the amount of ink, so
    the strokes keep the original's weight. The shapes are the game's own:
    nothing is guessed.
  - The made picture keeps its pixels, except where it shows the lettering's
    ink within a few game pixels of the game's letters: there it gets the
    game's paper, enlarged smoothly. Then the new letters are laid over.

It writes one raw RGBA file per item and prints one JSON line per item:
name, state, whether any pixel changed, match and made_match, the PSNR in dB
of the new and of the made picture against the game's own pixels in the box
after shrinking by block average, and why when the item stays as made: too
little lettering in the box, or lettering that touches the box's edge. The
last line holds the versions of numpy and Pillow.
"""
import json
import sys

import numpy as np
import PIL
from PIL import Image, ImageDraw


def blur(values, sigma):
    radius = int(3 * sigma + 1)
    kernel = np.exp(-0.5 * (np.arange(-radius, radius + 1) / sigma) ** 2)
    kernel /= kernel.sum()
    padded = np.pad(values, radius, mode="edge")
    padded = np.apply_along_axis(lambda line: np.convolve(line, kernel, "valid"), 0, padded)
    return np.apply_along_axis(lambda line: np.convolve(line, kernel, "valid"), 1, padded)


def enlarge(values, times):
    """Each channel enlarged times the smooth (bicubic) way."""
    h, w = values.shape[:2]
    planes = values.reshape(h, w, -1)
    out = [np.asarray(Image.fromarray(planes[..., c].astype(np.float32)).resize((w * times, h * times), Image.BICUBIC), np.float64)
           for c in range(planes.shape[2])]
    return np.stack(out, -1).reshape((h * times, w * times) + values.shape[2:])


def shrink(big, times):
    h, w = big.shape[0] // times, big.shape[1] // times
    return big.reshape(h, times, w, times, *big.shape[2:]).mean((1, 3))


def split(pixels, paper, inks):
    """How much of each ink each pixel holds, from 0 to 1, by least squares against the paper."""
    paper = np.broadcast_to(paper, pixels.shape)
    towards = np.stack([np.asarray(ink, np.float64) - paper for ink in inks], -1)
    normal = np.einsum("hwck,hwcl->hwkl", towards, towards) + 1e-3 * np.eye(len(inks))
    right = np.einsum("hwck,hwc->hwk", towards, pixels - paper)
    return np.clip(np.linalg.solve(normal, right[..., None])[..., 0], 0, 1)


def paper_under(pixels, hidden, sigma):
    """The pixels, with the hidden ones filled from the mean of the others around them."""
    seen = (~hidden).astype(np.float64)
    filled = pixels.copy()
    for spread in (sigma, 2 * sigma, 4 * sigma, 8 * sigma):
        weight = blur(seen, spread)
        mean = np.stack([blur(pixels[..., c] * seen, spread) for c in range(3)], -1) / np.maximum(weight, 1e-9)[..., None]
        fill = hidden & (weight > 0.05)
        filled[fill] = mean[fill]
        hidden = hidden & ~fill
        if not hidden.any():
            break
    return filled


def dilate(mask, radius):
    grown = mask.copy()
    padded = np.pad(mask, radius)
    h, w = mask.shape
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dx * dx + dy * dy <= radius * radius:
                grown |= padded[radius + dy:radius + dy + h, radius + dx:radius + dx + w]
    return grown


def hull(points):
    """The convex hull of points (x, y), anticlockwise."""
    points = sorted(set(points))
    if len(points) < 3:
        return points

    def turn(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower, upper = [], []
    for p in points:
        while len(lower) >= 2 and turn(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(points):
        while len(upper) >= 2 and turn(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def sheet(game, paper, look, times):
    """Where the sheet the letters are written on lies, in game pixels and in made pixels.

    The sheet is the largest patch of joined paper-coloured pixels, with
    everything inside its convex hull: the letters, and not the wood, cork or
    desk round a sign.
    """
    h, w = game.shape[:2]
    close = np.sqrt(((game - paper) ** 2).sum(-1)) < look["paper_distance"]
    ys, xs = np.nonzero(close)
    if not len(xs):
        return np.zeros((h, w), bool), np.zeros((h * times, w * times), bool)
    marks = Image.fromarray(np.where(close, 255, 0).astype(np.uint8)).copy()
    largest = None
    while True:
        left = np.argwhere(np.asarray(marks) == 255)
        if not len(left):
            break
        ImageDraw.floodfill(marks, (int(left[0][1]), int(left[0][0])), 128)
        found = np.asarray(marks) == 128
        if largest is None or found.sum() > largest.sum():
            largest = found
        marks.paste(64, mask=Image.fromarray(np.where(found, 255, 0).astype(np.uint8)))
    ys, xs = np.nonzero(largest)
    corners = hull([(x + dx, y + dy) for x, y in zip(xs.tolist(), ys.tolist()) for dx in (0, 1) for dy in (0, 1)])
    masks = []
    for scale in (1, times):
        plane = Image.new("L", (w * scale, h * scale), 0)
        ImageDraw.Draw(plane).polygon([(x * scale - 0.5, y * scale - 0.5) for x, y in corners], fill=255)
        masks.append(np.asarray(plane) > 0)
    return masks


def draw(target, look, made, original, times, into):
    game = original[..., :3].astype(np.float64)
    big = made[..., :3].astype(np.float64)
    light = game.sum(-1)
    paper = np.median(game[light >= np.quantile(light, look["paper_share"])], 0)
    on, on_big = sheet(game, paper, look, times)
    others = [np.asarray(other, np.float64) for other in target.get("other", [])]
    guess = split(game, paper, [np.asarray(target["ink"], np.float64)] + others)[..., 0] * on
    lies = np.zeros(guess.shape, bool)
    for x0, y0, x1, y1 in into:
        lies[max(0, y0):max(0, y1), max(0, x0):max(0, x1)] = True
    seen = guess[lies] if lies.any() else guess.ravel()
    darkest = (guess >= max(np.quantile(seen, 1 - look["ink_share"]), 0.5)) & (lies if lies.any() else True)
    said = {"changed": False}
    if darkest.sum() < 3:
        return made, dict(said, why="no lettering in its box")
    ink = game[darkest].mean(0)
    inks = [ink] + others
    share = split(game, paper, inks)
    for _ in range(2):
        under = paper_under(game, share[..., 0] > look["found"], look["spread"])
        share = split(game, under, inks)
    letters = share[..., 0] * on
    if letters.sum() < look["least_ink"]:
        return made, dict(said, why="too little lettering in its box")

    smooth = enlarge(letters, times)
    wanted = letters.sum() * times * times
    low, high = -1.0, 2.0
    for _ in range(50):
        level = (low + high) / 2
        if np.clip((smooth - level) / look["soft"] + 0.5, 0, 1).sum() > wanted:
            low = level
        else:
            high = level
    cover = np.clip((smooth - level) / look["soft"] + 0.5, 0, 1) * on_big
    rim = np.ones(cover.shape, bool)
    rim[2:-2, 2:-2] = False
    if (cover[rim] > 0.05).any():
        return made, dict(said, why="its lettering touches the edge of its box")

    paper_big = enlarge(under, times)
    near = np.kron(dilate(letters > look["near_found"], look["near"]), np.ones((times, times), bool))
    old = (split(big, paper_big, inks)[..., 0] > look["removed"]) & near & on_big
    clear = np.maximum(np.clip(blur(old.astype(np.float64), look["clear_soft"]) * 3, 0, 1), old)
    clear[rim] = 0
    result = big * (1 - clear[..., None]) + paper_big * clear[..., None]
    result = result * (1 - cover[..., None]) + ink * cover[..., None]
    out = made.copy()
    out[..., :3] = np.round(np.clip(result, 0, 255)).astype(np.uint8)

    def psnr(pixels):
        diff = shrink(pixels[..., :3].astype(np.float64), times) - game
        mse = float((diff ** 2).mean())
        return 99.0 if mse == 0 else round(10 * np.log10(255 * 255 / mse), 2)
    return out, {"changed": bool((out != made).any()), "match": psnr(out), "made_match": psnr(made),
                 "ink": [round(float(v), 1) for v in ink]}


def read(path, w, h):
    with open(path, "rb") as f:
        return np.frombuffer(f.read(), np.uint8).reshape(h, w, 4)


def main():
    with open(sys.argv[1]) as f:
        job = json.load(f)
    with open(job["spec"]) as f:
        spec = json.load(f)
    times = job["times"]
    targets = {target["name"]: target for target in spec["targets"]}
    for item in job["items"]:
        w, h = item["w"], item["h"]
        made, original = read(item["made"], w * times, h * times), read(item["original"], w, h)
        result, said = draw(targets[item["name"]], spec["look"], made, original, times, item["into"])
        with open(item["out"], "wb") as f:
            f.write(result.tobytes())
        print(json.dumps(dict(name=item["name"], state=item["state"], **said)), flush=True)
    print(json.dumps({"numpy": np.__version__, "pillow": PIL.__version__}), flush=True)


if __name__ == "__main__":
    main()
