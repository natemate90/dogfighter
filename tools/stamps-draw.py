"""Draws the ink stamps on the mission books again, for tools/stamps.py.

It runs in the desk's Python environment, upscale-tools/desk/venv, which has
numpy and Pillow, and takes one argument: a job file that tools/stamps.py
writes. The job names tools/stamps.json, the downloaded emblems, and for each
target the game's own pixels and the made 4x pixels of its box as raw RGBA.
tools/stamps.py says what the spec holds.

How a stamp is drawn:
  - The old ink is taken off the made picture: where the game's pixels in
    the stamp are darker or lighter than its paper, the made pixels are
    filled from the paper around them, with the made paper's grain. The
    paper is a plane fitted to the pixels around each one, so it follows the
    page's shading toward the spine. The new paper fades into the made
    picture before the stamp's reach ends and before the box's edges.
  - The stamp's shapes are drawn sharp at 16 times the game's pixels: rings
    as circles, and emblems from their SVG file, each colour of the drawing
    standing for full ink or for bare paper. The stamp's corners map the
    shapes onto the page, so they lean with it.
  - The ink is made uneven like a rubber stamp's: the edges are roughened,
    some patches print lighter, and a few small specks stay bare. The noise
    comes from a fixed seed, so two runs give the same pixels.
  - The ink darkens the paper by its colour, as ink on paper does.

It writes one raw RGBA file per target and prints one JSON line per target:
name, whether any pixel changed, match and made_match, the PSNR in dB of
the new and of the made picture against the game's own picture inside the
box, after shrinking by block average, and edges, the step in brightness
between the new and the made picture at each side of the box (see
edge_steps). A step over edge_step adds why, and the target stays as made.
The last line holds the versions of numpy and Pillow.
"""
import json
import re
import sys
import xml.etree.ElementTree as ET

import numpy as np
import PIL
from PIL import Image

FINE = 4
CURVE_STEPS = 12
NUMBER = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
COMMAND = re.compile(r"[MmLlHhVvCcSsQqTtZz]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
SVG = "{http://www.w3.org/2000/svg}"


def colour_of(value):
    value = value.strip().lower()
    if value == "none":
        return None
    if re.fullmatch(r"#[0-9a-f]{3}", value):
        value = "#" + "".join(c * 2 for c in value[1:])
    if not re.fullmatch(r"#[0-9a-f]{6}", value):
        raise ValueError("unsupported colour %r" % value)
    return value


def bezier(points, steps):
    t = np.linspace(0, 1, steps + 1)[1:, None]
    p = np.asarray(points, np.float64)
    if len(p) == 3:
        return (1 - t) ** 2 * p[0] + 2 * (1 - t) * t * p[1] + t ** 2 * p[2]
    return (1 - t) ** 3 * p[0] + 3 * (1 - t) ** 2 * t * p[1] + 3 * (1 - t) * t ** 2 * p[2] + t ** 3 * p[3]


def path_points(d):
    """The subpaths of an SVG path as lists of points, and whether each is closed."""
    tokens = COMMAND.findall(d)
    subpaths, current, start = [], None, (0.0, 0.0)
    x = y = 0.0
    last_control, last = None, None
    i, command = 0, None
    while i < len(tokens):
        if tokens[i].isalpha():
            command = tokens[i]
            i += 1
            if command in "Zz":
                if current:
                    subpaths.append((current, True))
                current = None
                x, y = start
                last_control, last = None, "Z"
                continue
        if command is None:
            raise ValueError("path data starts without a command")
        relative = command.islower()
        kind = command.upper()
        count = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "T": 2}[kind]
        values = [float(v) for v in tokens[i:i + count]]
        if len(values) != count:
            raise ValueError("path data ends inside a %s command" % command)
        i += count
        ox, oy = (x, y) if relative else (0.0, 0.0)
        if kind == "M":
            if current:
                subpaths.append((current, False))
            x, y = values[0] + ox, values[1] + oy
            current, start = [(x, y)], (x, y)
            command = "l" if relative else "L"
            last_control, last = None, "M"
            continue
        if current is None:
            current = [(x, y)]
        if kind == "H":
            x = values[0] + (x if relative else 0.0)
            current.append((x, y))
        elif kind == "V":
            y = values[0] + (y if relative else 0.0)
            current.append((x, y))
        elif kind == "L":
            x, y = values[0] + ox, values[1] + oy
            current.append((x, y))
        else:
            pairs = [(values[k] + ox, values[k + 1] + oy) for k in range(0, count, 2)]
            if kind in "ST":
                smooth = last in ("CS" if kind == "S" else "QT") and last_control is not None
                mirrored = (2 * x - last_control[0], 2 * y - last_control[1]) if smooth else (x, y)
                pairs = [mirrored] + pairs
            control = [(x, y)] + pairs
            current.extend(map(tuple, bezier(control, CURVE_STEPS)))
            last_control = control[-2]
            x, y = control[-1]
            last = kind
            continue
        last_control, last = None, kind
    if current:
        subpaths.append((current, False))
    return subpaths


def stroke_polygons(subpaths, width):
    """Rectangles along each segment, reaching half the width past inner corners, so right-angled joins are mitred."""
    polygons = []
    for points, closed in subpaths:
        p = np.asarray(points, np.float64)
        if closed:
            p = np.vstack([p, p[:1]])
        for k in range(len(p) - 1):
            a, b = p[k], p[k + 1]
            along = (b - a) / max(np.hypot(*(b - a)), 1e-12)
            if k > 0 or closed:
                a = a - along * width / 2
            if k < len(p) - 2 or closed:
                b = b + along * width / 2
            n = np.array([-along[1], along[0]]) * width / 2
            polygons.append(np.array([a + n, b + n, b - n, a - n]))
    return polygons


def svg_shapes(file):
    """[(colour, fill rule, [polygon])] of an SVG drawing, in its own units, lowest first."""
    shapes = []

    def walk(node, style):
        style = dict(style)
        for name in ("fill", "stroke", "stroke-width", "fill-rule"):
            if node.get(name) is not None:
                style[name] = node.get(name)
        if node.get("transform") is not None or node.get("style") is not None:
            raise ValueError("SVG transforms and style attributes are not supported")
        tag = node.tag.replace(SVG, "")
        if tag == "path":
            subpaths = path_points(node.get("d"))
        elif tag == "polygon":
            values = [float(v) for v in NUMBER.findall(node.get("points"))]
            subpaths = [(list(zip(values[0::2], values[1::2])), True)]
        elif tag in ("svg", "g"):
            for child in node:
                walk(child, style)
            return
        else:
            raise ValueError("SVG element %s is not supported" % tag)
        fill = colour_of(style.get("fill", "#000"))
        if fill:
            shapes.append((fill, style.get("fill-rule", "nonzero"), [np.asarray(points, np.float64) for points, _ in subpaths]))
        stroke = colour_of(style.get("stroke", "none"))
        if stroke:
            shapes.append((stroke, "nonzero", stroke_polygons(subpaths, float(style.get("stroke-width", "1")))))

    walk(ET.parse(file).getroot(), {})
    return shapes


def homography(src, dst):
    a, b = [], []
    for (x, y), (u, v) in zip(src, dst):
        a.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        b.append(u)
        a.append([0, 0, 0, x, y, 1, -v * x, -v * y])
        b.append(v)
    return np.append(np.linalg.solve(np.array(a, float), np.array(b, float)), 1).reshape(3, 3)


def apply(H, points):
    p = np.asarray(points, np.float64)
    q = np.einsum("ij,nj->ni", H, np.c_[p, np.ones(len(p))])
    return q[:, :2] / q[:, 2:]


def page_of(corners):
    """The homography from the stamp's own square, -1 to 1 each way, to the picture's pixels."""
    return homography([(-1, -1), (1, -1), (1, 1), (-1, 1)], corners)


def reach(corners, box, scale):
    """How far from the stamp's centre each pixel of the box at scale times its size lies, in the stamp's units."""
    x0, y0, x1, y1 = box
    yy, xx = np.mgrid[0:(y1 - y0) * scale, 0:(x1 - x0) * scale]
    points = np.c_[(xx.ravel() + 0.5) / scale + x0, (yy.ravel() + 0.5) / scale + y0]
    uv = apply(np.linalg.inv(page_of(corners)), points)
    return np.hypot(uv[:, 0], uv[:, 1]).reshape(xx.shape)


def inside(polygons, rule, width, height):
    """Which pixel centres of a width x height grid lie inside the polygons, by the fill rule."""
    crossings = np.zeros((height, width + 1), np.int32)
    for polygon in polygons:
        if len(polygon) < 3:
            continue
        a, b = polygon, np.roll(polygon, -1, 0)
        low, high = np.minimum(a[:, 1], b[:, 1]), np.maximum(a[:, 1], b[:, 1])
        first = np.clip(np.ceil(low - 0.5), 0, height).astype(np.int64)
        last = np.clip(np.ceil(high - 0.5), 0, height).astype(np.int64)
        rows = last - first
        keep = rows > 0
        if not keep.any():
            continue
        a, b, first, rows = a[keep], b[keep], first[keep], rows[keep]
        edge = np.repeat(np.arange(len(a)), rows)
        row = first[edge] + np.arange(rows.sum()) - np.repeat(np.cumsum(rows) - rows, rows)
        t = (row + 0.5 - a[edge, 1]) / (b[edge, 1] - a[edge, 1])
        x = a[edge, 0] + t * (b[edge, 0] - a[edge, 0])
        column = np.clip(np.ceil(x - 0.5), 0, width).astype(np.int64)
        np.add.at(crossings, (row, column), np.where(b[edge, 1] > a[edge, 1], 1, -1))
    winding = np.cumsum(crossings, 1)[:, :width]
    return (winding % 2 == 1) if rule == "evenodd" else winding != 0


def circle(radius, steps=720):
    angle = np.linspace(0, 2 * np.pi, steps, endpoint=False)
    return np.c_[radius * np.cos(angle), radius * np.sin(angle)]


def blur(values, sigma):
    """Gaussian blur of a 2D array, with the edges mirrored."""
    if sigma <= 0:
        return values
    pad = int(np.ceil(3 * sigma))
    padded = np.pad(values, pad, mode="reflect")
    h, w = padded.shape
    fy, fx = np.fft.fftfreq(h)[:, None], np.fft.rfftfreq(w)[None, :]
    gain = np.exp(-2 * (np.pi * sigma) ** 2 * (fy ** 2 + fx ** 2))
    return np.fft.irfft2(np.fft.rfft2(padded) * gain, s=(h, w))[pad:-pad, pad:-pad]


def noise(rng, shape, sigma):
    """Smooth noise with a standard deviation of 1."""
    n = blur(rng.standard_normal(shape), sigma)
    return n / max(n.std(), 1e-9)


def shrink(big, times):
    h, w = big.shape[0] // times, big.shape[1] // times
    return big.reshape(h, times, w, times, *big.shape[2:]).mean((1, 3))


def dilate(mask, radius):
    out = mask.copy()
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dx * dx + dy * dy <= radius * radius:
                out |= np.roll(np.roll(mask, dy, 0), dx, 1)
    return out


def plane(values, weight, sigma):
    """Each pixel's value on a plane fitted to the weighted pixels around it in a Gaussian window, and the window's share of weight.

    A plane, not an average, so the estimate follows the page's shading up to
    the box's edges instead of being pulled toward the brighter side.
    """
    pad = int(np.ceil(3 * sigma))
    h, w = weight.shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)

    def mean(v):
        return blur(np.pad(weight * v, pad), sigma)[pad:-pad, pad:-pad] / np.maximum(share, 1e-9)
    share = blur(np.pad(weight, pad), sigma)[pad:-pad, pad:-pad]
    mx, my = mean(xx), mean(yy)
    ridge = 0.05 * sigma * sigma
    cxx, cxy, cyy = mean(xx * xx) - mx * mx + ridge, mean(xx * yy) - mx * my, mean(yy * yy) - my * my + ridge
    det = cxx * cyy - cxy * cxy
    out = []
    for c in range(values.shape[2]):
        v = values[..., c]
        mv = mean(v)
        cxv, cyv = mean(xx * v) - mx * mv, mean(yy * v) - my * mv
        out.append(mv + ((cyy * cxv - cxy * cyv) * (xx - mx) + (cxx * cyv - cxy * cxv) * (yy - my)) / det)
    return np.stack(out, -1), share


def paper_of(game, near, stamp, look):
    """Which of the game's pixels are ink: those of the stamp off the paper fitted around them."""
    keep = near
    for _ in range(4):
        paper, _ = plane(game, keep.astype(np.float64), look["shade_sigma"])
        ink = stamp & (np.abs(game - paper).max(2) >= look["ink_step"])
        keep = near & ~ink
    return ink


def enlarge(values, times):
    return np.stack([np.asarray(Image.fromarray(values[..., c].astype(np.float32)).resize(
        (values.shape[1] * times, values.shape[0] * times), Image.BICUBIC), np.float64) for c in range(values.shape[2])], -1)


def clean(made, game, corners, box, times, look, rng):
    """The made pixels with the paper near the stamp drawn again from the game's paper, without its ink, and where the game has ink."""
    small = reach(corners, box, 1)
    ink = paper_of(game, small <= look["paper_reach"], small <= look["clean_reach"], look)
    keep = (~dilate(ink, 1)).astype(np.float64)
    sigma = look["paper_sigma"]
    paper, near = plane(game, keep, sigma)
    for wider in (2 * sigma, 4 * sigma, 8 * sigma):
        thin = near < 0.2
        if not thin.any():
            break
        paper[thin], near[thin] = (part[thin] for part in plane(game, keep, wider))
    paper = enlarge(paper, times)
    rgb = made[..., :3].astype(np.float64)
    outside = reach(corners, box, times) > look["clean_reach"] + 0.1
    grain = rgb - np.stack([blur(rgb[..., c], look["grain_sigma"]) for c in range(3)], -1)
    spread = grain[outside].std(0) if outside.any() else np.zeros(3)
    paper += noise(rng, paper.shape[:2], look["grain_sigma"] / 2)[..., None] * spread
    h, w = paper.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    edge = np.minimum(np.minimum(xx, w - 1 - xx), np.minimum(yy, h - 1 - yy)) / (look["edge_feather"] * times)
    soft = np.minimum(np.clip((look["clean_reach"] - reach(corners, box, times)) / look["clean_feather"], 0, 1), np.clip(edge, 0, 1))
    return rgb * (1 - soft[..., None]) + paper * soft[..., None], ink


def ink_cover(stamp, corners, box, times, files, look, rng):
    """How much ink each pixel of the box gets at times its size, 0 to 1."""
    x0, y0, x1, y1 = box
    scale = times * FINE
    width, height = (x1 - x0) * scale, (y1 - y0) * scale
    to_fine = np.einsum("ij,jk->ik", np.array([[scale, 0, -x0 * scale], [0, scale, -y0 * scale], [0, 0, 1]], np.float64), page_of(corners))
    cover = np.zeros((height, width))
    for layer in stamp["layers"]:
        if "ring" in layer:
            outer, inner = layer["ring"]
            shapes = [(1.0, "evenodd", [circle(outer), circle(inner)])]
            into = np.eye(3)
        else:
            fx0, fy0, fx1, fy1 = layer["from"]
            tx0, ty0, tx1, ty1 = layer["to"]
            into = np.array([[(tx1 - tx0) / (fx1 - fx0), 0, tx0 - fx0 * (tx1 - tx0) / (fx1 - fx0)],
                             [0, (ty1 - ty0) / (fy1 - fy0), ty0 - fy0 * (ty1 - ty0) / (fy1 - fy0)], [0, 0, 1]])
            shapes = [(layer["inks"][colour], rule, polygons) for colour, rule, polygons in svg_shapes(files[layer["reference"]])]
        H = np.einsum("ij,jk->ik", to_fine, into)
        own = np.zeros((height, width))
        for value, rule, polygons in shapes:
            own[inside([apply(H, p) for p in polygons], rule, width, height)] = value * layer.get("strength", 1.0)
        cover = np.maximum(cover, own)
    rough = look["rough"]
    shape = (cover > 0).astype(np.float64)
    near = blur(shape, rough["soften"] * FINE)
    printed = near + noise(rng, cover.shape, rough["size"] * FINE) * rough["amount"] > 0.5
    cover = shrink(printed * blur(cover, rough["soften"] * FINE) / np.maximum(near, 1e-6), FINE)
    patchy = 1.0
    for patches in look["patches"]:
        patchy = patchy * (1 - patches["amount"] * np.clip(noise(rng, cover.shape, patches["size"]), 0, None))
    specks = noise(rng, cover.shape, look["specks"]["size"]) < -look["specks"]["above"]
    return np.clip(cover * patchy * (1 - specks), 0, 1)


SIDES = ("left", "top", "right", "bottom")


def edge_steps(result, made, bare, times, look):
    """The largest step in mean brightness, in levels of 255, between the drawn and the made picture near each side of the box.

    Outside the box the picture stays as made, so this is the step a viewer
    sees across the box's edge. It is measured in windows of one by four of
    the game's pixels on bare paper, in the outer edge_feather + 1 pixels, in
    the order of SIDES.
    """
    diff = (result[..., :3].astype(np.float64) - made[..., :3]) @ [0.299, 0.587, 0.114]
    steps = []
    for turns in (-1, 0, 1, 2):
        d, ok = np.rot90(diff, turns), np.rot90(bare, turns)
        step = 0.0
        for row in range(0, (look["edge_feather"] + 1) * times, times):
            for col in range(0, d.shape[1] - 4 * times + 1, 4 * times):
                window = (slice(row, row + times), slice(col, col + 4 * times))
                if ok[window].mean() >= 0.5:
                    step = max(step, abs(float(d[window][ok[window]].mean())))
        steps.append(round(step, 2))
    return steps


def draw(target, spec, files, made, original, times):
    """The drawn pixels, and what main prints about them besides the name."""
    stamp = spec["stamps"][target["stamp"]]
    look = dict(spec["look"], **stamp.get("look", {}))
    rng = np.random.default_rng(look["seed"])
    game = original[..., :3].astype(np.float64)
    paper, ink = clean(made, game, target["corners"], target["box"], times, look, rng)
    cover = ink_cover(stamp, target["corners"], target["box"], times, files, look, rng)
    tint = np.asarray(stamp["ink"], np.float64) / 255
    result = made.astype(np.float64).copy()
    result[..., :3] = paper * (1 - cover[..., None] * (1 - tint))
    result = np.round(np.clip(result, 0, 255)).astype(np.uint8)

    def psnr(big):
        diff = (shrink(big[..., :3].astype(np.float64), times) - game)[original[..., 3] > 0]
        mse = float((diff ** 2).mean()) if diff.size else 0.0
        return 99.0 if mse == 0 else round(10 * np.log10(255 * 255 / mse), 2)
    bare = ~np.kron(dilate(ink, 1), np.ones((times, times), bool)) & (cover == 0)
    edges = edge_steps(result, made, bare, times, look)
    said = {"changed": bool((result != made).any()), "match": psnr(result), "made_match": psnr(made), "edges": edges}
    worst = int(np.argmax(edges))
    if edges[worst] > look["edge_step"]:
        said["why"] = "its paper steps %.1f levels in brightness at the %s edge of its box, over %.1f" % (
            edges[worst], SIDES[worst], look["edge_step"])
    return result, said


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
        result, said = draw(targets[item["name"]], spec, job["references"], made, original, times)
        with open(item["out"], "wb") as f:
            f.write(result.tobytes())
        print(json.dumps(dict(name=item["name"], **said)), flush=True)
    print(json.dumps({"numpy": np.__version__, "pillow": PIL.__version__}), flush=True)


if __name__ == "__main__":
    main()
