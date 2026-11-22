"""Draws the plane paintings of the loading screens and the model window again from Airfix's box art, for tools/paintings.py.

It runs in the desk's Python environment, upscale-tools/desk/venv, which has
numpy and Pillow, and takes one argument: a job file that tools/paintings.py
writes. The job names tools/paintings.json, the downloaded pictures, and for
each target the game's own pixels and the made 4x pixels of its box as raw
RGBA. tools/paintings.py says what the spec holds.

How a target is drawn:
  - Each layer samples its picture of the box art at the 4x pixels of the
    target, through the fitted homography (corners) and the small fitted
    displacement grid on top of it. A picture with more pixels than 4x is
    blurred first, so it is not sampled with gaps.
  - A layer covers the target where the mapped point lies inside its
    painted area, and not in its keep boxes: places where the box shows
    words or a logo that the game's picture does not have.
  - Its colours are fitted to the game's picture, per channel, in windows
    of the game's pixels: out = a * painting + b, with a and b from the game's
    pixels and the painting shrunk to the game's size. Where the painting is
    flat, a falls back to the gain fitted over the whole target. So the
    game's colours, its light and the dark edge of the screen stay, and the
    detail comes from the painting.
  - The result is laid over the made picture inside the target's area, with
    a soft edge, so the frame around the picture stays as made.

It writes one raw RGBA file per target and prints one JSON line per target:
name, whether any pixel changed, and match and made_match, the PSNR in dB of
the new and of the made picture against the game's own picture inside the
area, after shrinking by block average. The last line holds the versions of
numpy and Pillow.
"""
import json
import sys

import numpy as np
import PIL
from PIL import Image, ImageFilter


def homography(corners, w, h):
    src = [(0, 0), (w, 0), (w, h), (0, h)]
    a, b = [], []
    for (x, y), (u, v) in zip(src, corners):
        a.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        b.append(u)
        a.append([0, 0, 0, x, y, 1, -v * x, -v * y])
        b.append(v)
    return np.append(np.linalg.solve(np.array(a, float), np.array(b, float)), 1).reshape(3, 3)


def enlarge(values, width, height, how=Image.BICUBIC):
    """A small grid of numbers spread over width x height, each value at the centre of its cell."""
    return np.asarray(Image.fromarray(np.asarray(values, np.float32)).resize((width, height), how), np.float64)


def mapping(layer, w, h, times):
    """The point of the painting for each pixel of the target at times its size, in the painting's pixel indices."""
    H = homography(layer["corners"], w, h)
    W, Ht = w * times, h * times
    grid = np.asarray(layer["grid"], np.float64)
    yy, xx = np.mgrid[0:Ht, 0:W].astype(np.float64)
    x = (xx + 0.5) / times + enlarge(grid[0], W, Ht)
    y = (yy + 0.5) / times + enlarge(grid[1], W, Ht)
    den = H[2, 0] * x + H[2, 1] * y + H[2, 2]
    return (H[0, 0] * x + H[0, 1] * y + H[0, 2]) / den - 0.5, (H[1, 0] * x + H[1, 1] * y + H[1, 2]) / den - 0.5


def catmull_rom(t):
    t2, t3 = t * t, t * t * t
    return (-0.5 * t3 + t2 - 0.5 * t, 1.5 * t3 - 2.5 * t2 + 1, -1.5 * t3 + 2 * t2 + 0.5 * t, 0.5 * t3 - 0.5 * t2)


def sample(picture, mx, my):
    """Bicubic samples of an (h, w, 3) picture at the points mx, my."""
    h, w, _ = picture.shape
    x0, y0 = np.floor(mx).astype(np.int64), np.floor(my).astype(np.int64)
    wx, wy = catmull_rom(mx - x0), catmull_rom(my - y0)
    out = np.zeros(mx.shape + (3,), np.float64)
    for j in range(4):
        rows = np.clip(y0 + j - 1, 0, h - 1)
        for i in range(4):
            out += picture[rows, np.clip(x0 + i - 1, 0, w - 1)] * (wy[j] * wx[i])[..., None]
    return out


def edge_distance(polygon, mx, my):
    """How far inside a convex polygon each point lies, in the polygon's units; negative outside."""
    pts = np.asarray(polygon, np.float64)
    inside = np.full(mx.shape, np.inf)
    turn = np.sign(sum((pts[i - 1][0] - pts[i][0]) * (pts[i - 1][1] + pts[i][1]) for i in range(len(pts))))
    for i in range(len(pts)):
        (ax, ay), (bx, by) = pts[i], pts[(i + 1) % len(pts)]
        length = np.hypot(bx - ax, by - ay)
        inside = np.minimum(inside, turn * ((bx - ax) * (my - ay) - (by - ay) * (mx - ax)) / length)
    return inside


def rounded_inside(rect, radius, xx, yy):
    """How far inside a rounded rectangle each point lies; negative outside."""
    x0, y0, x1, y1 = rect
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    qx = np.abs(xx - cx) - ((x1 - x0) / 2 - radius)
    qy = np.abs(yy - cy) - ((y1 - y0) / 2 - radius)
    outside = np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - radius
    return -outside


def shrink(big, times):
    h, w = big.shape[0] // times, big.shape[1] // times
    return big.reshape(h, times, w, times, *big.shape[2:]).mean((1, 3))


def box_mean(values, weights, radius):
    """The weighted mean of values in a square window of 2 * radius + 1 pixels round each pixel."""
    def window(a):
        padded = np.pad(a, ((radius + 1, radius), (radius + 1, radius)))
        s = padded.cumsum(0).cumsum(1)
        n = 2 * radius + 1
        return s[n:, n:] - s[:-n, n:] - s[n:, :-n] + s[:-n, :-n]
    return window(values * weights) / np.maximum(window(weights), 1e-6)


def layer_picture(layer, files, w, h, times):
    """(RGB, cover) of one layer at times the target's size."""
    photo = Image.open(files[layer["reference"]]).convert('RGB')
    mx, my = mapping(layer, w, h, times)
    step = np.sqrt(abs(np.gradient(mx, axis=1) * np.gradient(my, axis=0) - np.gradient(mx, axis=0) * np.gradient(my, axis=1)))
    spread = float(np.median(step))
    if spread > 1:
        photo = photo.filter(ImageFilter.GaussianBlur(0.5 * np.sqrt(spread * spread - 1)))
    rgb = np.clip(sample(np.asarray(photo, np.float64), mx, my), 0, 255)
    per_pixel = spread * times
    painted = layer.get("painted") or [[0, 0], [photo.width - 1, 0], [photo.width - 1, photo.height - 1], [0, photo.height - 1]]
    cover = np.clip(edge_distance(painted, mx, my) / per_pixel / layer["feather"], 0, 1)
    yy, xx = np.mgrid[0:h * times, 0:w * times].astype(np.float64)
    x, y = (xx + 0.5) / times, (yy + 0.5) / times
    for x0, y0, x1, y1 in layer.get("keep", []):
        outside = np.maximum(np.maximum(x0 - x, x - x1), np.maximum(y0 - y, y - y1))
        cover *= np.clip(outside / layer["feather"], 0, 1)
    return rgb, cover


def draw(target, spec, files, made, original, times):
    h, w = original.shape[:2]
    painting = np.zeros((h * times, w * times, 3))
    cover = np.zeros((h * times, w * times))
    for layer in target["layers"]:
        rgb, c = layer_picture(dict(spec["layer"], **layer), files, w, h, times)
        painting = painting * (1 - c[..., None]) + rgb * c[..., None]
        cover = cover * (1 - c) + c
    painting /= np.maximum(cover, 1e-6)[..., None]

    area = spec["areas"][target["area"]]
    yy, xx = np.mgrid[0:h * times, 0:w * times].astype(np.float64)
    inside = rounded_inside(area["rect"], area["radius"], (xx + 0.5) / times, (yy + 0.5) / times)
    blend = np.clip(inside / area["feather"], 0, 1) * cover
    small_blend = shrink(blend, times)

    fit = spec["colour"]
    small = shrink(painting, times)
    game = original[..., :3].astype(np.float64)
    weights = shrink(cover, times) * (shrink(inside, times) > 0)
    out = np.empty_like(painting)
    for c in range(3):
        guide, wanted = small[..., c], game[..., c]
        sel = weights > 0.5
        mean_g, mean_w = guide[sel].mean(), wanted[sel].mean()
        gain = np.clip(((guide[sel] - mean_g) * (wanted[sel] - mean_w)).mean() / max(((guide[sel] - mean_g) ** 2).mean(), 1e-6), *fit["gain"])
        r, eps = fit["radius"], fit["eps"]
        m_g, m_w = box_mean(guide, weights, r), box_mean(wanted, weights, r)
        cov = box_mean(guide * wanted, weights, r) - m_g * m_w
        var = box_mean(guide * guide, weights, r) - m_g * m_g
        a = np.clip((cov + eps * gain) / (var + eps), *fit["gain"])
        b = m_w - a * m_g
        a, b = box_mean(a, weights, r), box_mean(b, weights, r)
        out[..., c] = enlarge(a, w * times, h * times, Image.BILINEAR) * painting[..., c] + enlarge(b, w * times, h * times, Image.BILINEAR)
    result = made.astype(np.float64).copy()
    result[..., :3] = made[..., :3] * (1 - blend[..., None]) + np.clip(out, 0, 255) * blend[..., None]
    result = np.round(result).astype(np.uint8)

    def psnr(big):
        diff = (shrink(big[..., :3].astype(np.float64), times) - game)[(small_blend > 0.5) & (original[..., 3] > 0)]
        mse = float((diff ** 2).mean()) if diff.size else 0.0
        return 99.0 if mse == 0 else round(10 * np.log10(255 * 255 / mse), 2)
    return result, psnr(result), psnr(made)


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
    for item in job["targets"]:
        w, h = item["w"], item["h"]
        made, original = read(item["made"], w * times, h * times), read(item["original"], w, h)
        result, match, made_match = draw(targets[item["name"]], spec, job["references"], made, original, times)
        with open(item["out"], "wb") as f:
            f.write(result.tobytes())
        print(json.dumps({"name": item["name"], "changed": bool((result != made).any()), "match": match, "made_match": made_match}), flush=True)
    print(json.dumps({"numpy": np.__version__, "pillow": PIL.__version__}), flush=True)


if __name__ == "__main__":
    main()
