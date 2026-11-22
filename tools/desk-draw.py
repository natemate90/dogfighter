"""Draws the model kit boxes and paint tins of the main menu's desk again from photos, for tools/desk.py.

It runs in upscale-tools/desk/venv, which has numpy and Pillow, and takes one
argument: a job file that tools/desk.py writes. The job names tools/desk.json,
the downloaded photos and fonts, and the made 4x pictures of the main menu as
raw RGBA. tools/desk.py says what the spec holds.

How an item is drawn:
  - A face of a box (a lid, a long side, an end) is straightened out of a
    photo of a real box. Sides of kits without a photo of their own are laid
    out on the Typhoon's side or end, with the kit's title, words, number and
    a strip of its own box painting.
  - It is warped onto the face's four corners in the 4x menu.
  - Its colours are mapped onto the made picture's pixels there: the light
    paper to the game's paper, the darks half way to the game's darks, and
    the game's light falling across the face in place of the photo's.
  - A tin is drawn round its top and body from the tin on Humbrol's 1997
    "Colour System" binder, with the lid in the game's paint colour.
  - The edges are softened and laid over the made picture.

For each highlight in "states" the made highlight is laid over the screen,
all items are drawn again over that, and the highlight is cut out with its
own alpha.

It writes one raw RGBA file per piece and prints one JSON line per piece:
path, whether any pixel changed, and match and made_match, the PSNR in dB of
the new and of the made piece against the game's own picture after shrinking
by block average. Pixels the game's picture leaves invisible do not count.
The last line holds the versions of numpy and Pillow.
"""
import json
import sys

import numpy as np
import PIL
from PIL import Image, ImageDraw, ImageFilter, ImageFont

SS = 3


def homography(src, dst):
    a, b = [], []
    for (x, y), (u, v) in zip(src, dst):
        a.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        b.append(u)
        a.append([0, 0, 0, x, y, 1, -v * x, -v * y])
        b.append(v)
    h = np.linalg.solve(np.array(a, float), np.array(b, float))
    return np.append(h, 1).reshape(3, 3)


def bbox(quad, pad=3):
    xs = [p[0] for p in quad]
    ys = [p[1] for p in quad]
    return (int(np.floor(min(xs))) - pad, int(np.floor(min(ys))) - pad,
            int(np.ceil(max(xs))) + pad, int(np.ceil(max(ys))) + pad)


def warp_face(face, dst_quad):
    """(x0, y0, rgb, alpha) of face warped so its corners land on dst_quad, over the quad's bounding box."""
    w, h = face.size
    src_quad = [(0, 0), (w, 0), (w, h), (0, h)]
    x0, y0, x1, y1 = bbox(dst_quad)
    bw, bh = x1 - x0, y1 - y0
    dst_ss = [((x - x0) * SS, (y - y0) * SS) for x, y in dst_quad]
    matrix = homography(dst_ss, src_quad)
    big = face.transform((bw * SS, bh * SS), Image.PERSPECTIVE, tuple((matrix / matrix[2, 2]).flatten()[:8]), Image.BICUBIC)
    rgb = np.asarray(big.resize((bw, bh), Image.BOX)).astype(np.float32)
    mask = Image.new('L', (bw * SS, bh * SS), 0)
    ImageDraw.Draw(mask).polygon(dst_ss, fill=255)
    alpha = np.asarray(mask.resize((bw, bh), Image.BOX)).astype(np.float32) / 255
    return x0, y0, rgb, alpha


def feather(alpha, inset, blur):
    """Pulls the edge in by inset pixels and softens it, so the made picture's own edge pixels stay."""
    im = Image.fromarray((alpha * 255).astype(np.uint8))
    if inset > 0:
        im = im.filter(ImageFilter.GaussianBlur(inset))
        arr = np.asarray(im).astype(np.float32) / 255
        arr = np.clip((arr - 0.5) * 2 + 0.5 - inset * 0.4, 0, 1)
        im = Image.fromarray((arr * 255).astype(np.uint8))
    im = im.filter(ImageFilter.GaussianBlur(blur))
    return np.asarray(im).astype(np.float32) / 255


def lum(a):
    return a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114


def plane_fit(val, mask):
    h, w = val.shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    sel = mask > 0.9
    a = np.stack([np.ones(sel.sum()), xx[sel], yy[sel]], 1)
    coef, *_ = np.linalg.lstsq(a, val[sel], rcond=None)
    return coef[0] + coef[1] * xx + coef[2] * yy


def colour_fit(rgb, game, mask, fit, paper=None):
    sel = mask > 0.9
    out = rgb.copy()
    for c in range(3):
        r, g = rgb[..., c][sel], game[..., c][sel]
        rh, rl = np.percentile(r, fit["hi"]), np.percentile(r, fit["lo"])
        gh, gl = np.percentile(g, fit["hi"]), np.percentile(g, fit["lo"])
        if paper is not None:
            gh = np.percentile(paper[0][..., c][paper[1] > 0.9], fit["hi"])
        target_lo = fit["lo_mix"] * gl + (1 - fit["lo_mix"]) * rl
        gain = np.clip((gh - target_lo) / max(rh - rl, 1), *fit["gain"])
        out[..., c] = (rgb[..., c] - rh) * gain + gh
    game_light, own_light = plane_fit(lum(game), mask), plane_fit(lum(out), mask)
    ratio = (game_light / game_light[sel].mean()) / (own_light / own_light[sel].mean())
    out = out * (1 + (ratio - 1) * fit["shade"])[..., None]
    return np.clip(out, 0, 255)


def soften(rgb, radius):
    im = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8))
    return np.asarray(im.filter(ImageFilter.GaussianBlur(radius))).astype(np.float32)


def paste(canvas, x0, y0, rgb, alpha):
    h, w = alpha.shape
    region = canvas[y0:y0 + h, x0:x0 + w]
    region[:] = region * (1 - alpha[..., None]) + rgb * alpha[..., None]


class Faces:
    """Builds each flat, straightened face from the photos."""

    def __init__(self, spec, references, fonts):
        self.spec, self.references, self.fonts = spec, references, fonts

    def photo(self, name):
        return Image.open(self.references[name]).convert('RGB')

    def font(self, name, size):
        return ImageFont.truetype(self.fonts[name], size)

    def rectify(self, source):
        w, h = source["size"]
        matrix = homography([(0, 0), (w, 0), (w, h), (0, h)], source["quad"])
        return self.photo(source["reference"]).transform((w, h), Image.PERSPECTIVE, tuple((matrix / matrix[2, 2]).flatten()[:8]),
                                                          Image.BICUBIC)

    def fiat_lid(self, kit):
        spec = self.spec["fiat_lid"]
        face = self.rectify(spec)
        token = spec["token"]
        piece = self.photo(token["reference"]).crop(token["crop"]).rotate(token["rotate"], expand=True)
        w, h = face.size
        u0, v0, u1, v1 = token["place"]
        piece = piece.resize((int((u1 - u0) * w), int((v1 - v0) * h)), Image.LANCZOS)
        face.paste(piece, (int(u0 * w), int(v0 * h)))
        return face

    def spitfire_lid(self, kit):
        return self.rectify(self.spec["spitfire_lid"])

    def title_run(self, parts, size, max_w, squeeze=0.82, weight=560):
        """One title line in coloured parts, squeezed, and narrowed to max_w when wider, as the box titles are."""
        title = self.spec["title"]
        f = self.font(title["font"], size)
        try:
            f.set_variation_by_axes([weight])
        except Exception:
            pass
        widths = [f.getbbox(text)[2] for text, _ in parts]
        im = Image.new('RGBA', (sum(widths) + 8, int(size * 1.45)), (0, 0, 0, 0))
        draw = ImageDraw.Draw(im)
        x = 4
        for (text, colour), width in zip(parts, widths):
            outline = dict(stroke_width=2, stroke_fill=tuple(title["outline"])) if colour == title["yellow"] else {}
            draw.text((x, 0), text, fill=tuple(colour), font=f, **outline)
            x += width
        im = im.crop(im.getbbox())
        im = im.resize((int(im.width * squeeze), im.height), Image.LANCZOS)
        if im.width > max_w:
            im = im.resize((max_w, im.height), Image.LANCZOS)
        return im

    @staticmethod
    def paper_fill(face, box, margin=40):
        """Fills box with the paper: a plane fitted to the light pixels around it."""
        a = np.asarray(face).astype(np.float32)
        light = a.mean(2)
        h, w = light.shape
        yy, xx = np.mgrid[0:h, 0:w]
        x0, y0, x1, y1 = box
        ring = (xx >= x0 - margin) & (xx < x1 + margin) & (yy >= max(y0 - margin, 0)) & (yy < min(y1 + margin, h))
        ring &= ~((xx >= x0) & (xx < x1) & (yy >= y0) & (yy < y1))
        sel = ring & (light > np.percentile(light[ring], 55))
        m = np.stack([np.ones(sel.sum()), xx[sel], yy[sel]], 1)
        out = a.copy()
        for c in range(3):
            coef, *_ = np.linalg.lstsq(m, a[..., c][sel], rcond=None)
            out[y0:y1, x0:x1, c] = coef[0] + coef[1] * xx[y0:y1, x0:x1] + coef[2] * yy[y0:y1, x0:x1]
        return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))

    @staticmethod
    def blue_fill(face, poly, margin=50):
        """Fills a polygon with the end panel's blue: a plane fitted to the blue pixels around it."""
        a = np.asarray(face).astype(np.float32)
        h, w, _ = a.shape
        yy, xx = np.mgrid[0:h, 0:w]
        m = Image.new('L', (w, h), 0)
        ImageDraw.Draw(m).polygon([tuple(p) for p in poly], fill=255)
        inside = np.asarray(m) > 0
        near = np.asarray(m.filter(ImageFilter.MaxFilter(2 * (margin // 2) + 1))) > 0
        sel = near & ~inside & (a[..., 2] > a[..., 0] + 50)
        fit = np.stack([np.ones(sel.sum()), xx[sel], yy[sel]], 1)
        for c in range(3):
            coef, *_ = np.linalg.lstsq(fit, a[..., c][sel], rcond=None)
            a[..., c] = np.where(inside, coef[0] + coef[1] * xx + coef[2] * yy, a[..., c])
        return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))

    def strip_paste(self, face, reference, crop, poly):
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        bx0, by0, bx1, by1 = min(xs), min(ys), max(xs), max(ys)
        painting = self.photo(reference).crop(crop).resize((bx1 - bx0, by1 - by0), Image.LANCZOS)
        m = Image.new('L', face.size, 0)
        ImageDraw.Draw(m).polygon([tuple(p) for p in poly], fill=255)
        layer = Image.new('RGB', face.size)
        layer.paste(painting, (bx0, by0))
        face.paste(layer, (0, 0), m)

    def type11_side(self, kit):
        spec = self.spec["type11_side"]
        face = self.rectify(spec)
        k = spec["kits"].get(kit)
        if k is None:
            return face
        face = self.paper_fill(face, spec["clear"])
        face = self.paper_fill(face, spec["number_box"])
        self.strip_paste(face, k["lid"], k["crop"], spec["strip"])
        layout = spec["layout"]
        centre = layout["centre"]
        for line, (size, top) in (("line1", layout["line1"]), ("line2", layout["line2"])):
            run = self.title_run(k[line], size, layout["title_width"])
            face.paste(run, (centre - run.width // 2, top), run)
        draw = ImageDraw.Draw(face)
        words = layout["words"]
        f = self.font(words["font"], words["size"])
        for i, line in enumerate(k["words"]):
            draw.text((centre, words["top"] + i * words["step"]), line, fill=tuple(words["colour"]), font=f, anchor='mt')
        number = layout["number"]
        draw.text(tuple(number["at"]), k["number"], fill=tuple(number["colour"]), font=self.font(number["font"], number["size"]), anchor='mm')
        return face

    @staticmethod
    def neutral_paper(face):
        """Scales the channels so the paper, the lightest quarter of the pixels, is grey and not blue from the wrap."""
        a = np.asarray(face).astype(np.float32)
        light = a.mean(2)
        paper = a[light > np.percentile(light, 75)].mean(0)
        a = a * (paper.mean() / paper)[None, None, :]
        return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))

    def type10_side(self, kit):
        spec = self.spec["type10_side"]
        face = self.paper_fill(self.neutral_paper(self.rectify(spec)), spec["clear"])
        k = spec["kits"][kit]
        layout = spec["layout"]
        title = layout["title"]
        f = self.font(title["font"], title["size"])
        widths = [f.getbbox(text)[2] for text, _ in k["title"]]
        im = Image.new('RGBA', (sum(widths) + 10, 110), (0, 0, 0, 0))
        draw = ImageDraw.Draw(im)
        x = 4
        for (text, colour), width in zip(k["title"], widths):
            draw.text((x, 0), text, fill=tuple(colour), font=f)
            x += width
        im = im.crop(im.getbbox())
        if im.width > title["width"]:
            im = im.resize((title["width"], im.height), Image.LANCZOS)
        face.paste(im, tuple(title["at"]), im)
        draw = ImageDraw.Draw(face)
        words = layout["words"]
        f = self.font(words["font"], words["size"])
        for i, line in enumerate(k["words"]):
            draw.text((words["left"], words["top"] + i * words["step"]), line, fill=tuple(words["colour"]), font=f)
        x0, y0, x1, y1 = k["place"]
        painting = self.photo(k["painting"]).crop(k["crop"]).resize((x1 - x0, y1 - y0), Image.LANCZOS)
        m = Image.new('L', (x1 - x0, y1 - y0), 0)
        ImageDraw.Draw(m).ellipse([10, 8, x1 - x0 - 10, y1 - y0 - 8], fill=255)
        face.paste(painting, (x0, y0), m.filter(ImageFilter.GaussianBlur(layout["painting_blur"])))
        return face

    def type11_end(self, kit):
        spec = self.spec["type11_end"]
        face = self.rectify(spec)
        k = spec["kits"][kit]
        face = self.blue_fill(face, spec["wing"])
        self.strip_paste(face, k["painting"], k["crop"], spec["strip"])
        layout = spec["layout"]
        title = self.title_run(k["title"], layout["title_size"], layout["title_width"], squeeze=layout["title_squeeze"])
        face.paste(title, (layout["title_right"] - title.width, layout["title_top"]), title)
        x0, y0, x1, y1 = spec["number_box"]
        face = self.blue_fill(face, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)])
        draw = ImageDraw.Draw(face)
        sx0, sy0, sx1, sy1 = spec["series_box"]
        navy = tuple(int(v) for v in np.median(np.asarray(face)[sy0 + 4:sy1 - 4, sx0:sx0 + 8].reshape(-1, 3), 0))
        draw.rectangle(spec["series_box"], fill=navy)
        series, number = layout["series"], layout["number"]
        draw.text(((sx0 + sx1) // 2, (sy0 + sy1) // 2), k["series"], fill=tuple(series["colour"]),
                  font=self.font(series["font"], series["size"]), anchor='mm')
        draw.text(((x0 + x1) // 2, (y0 + y1) // 2), k["number"], fill=tuple(number["colour"]),
                  font=self.font(number["font"], number["size"]), anchor='mm')
        return face


def shade_top(face, top, foot):
    """The box above darkens the top of a side, and a crease darkens its bottom edge."""
    a = np.asarray(face).astype(np.float32)
    y = np.arange(a.shape[0], dtype=np.float32)[:, None, None]
    a = a * (1 - top[0] * np.exp(-y / top[1]))
    a = a * (1 - foot[0] * np.exp(-(a.shape[0] - 1 - y) / foot[1]))
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def bilinear(img, xs, ys):
    h, w, _ = img.shape
    xs = np.clip(xs, 0, w - 1.001)
    ys = np.clip(ys, 0, h - 1.001)
    x0, y0 = xs.astype(int), ys.astype(int)
    fx, fy = (xs - x0)[..., None], (ys - y0)[..., None]
    a, b, c, d = img[y0, x0], img[y0, x0 + 1], img[y0 + 1, x0], img[y0 + 1, x0 + 1]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def paint_colour(game, t):
    """The median colour of the inner half of the made picture's top ellipse."""
    x0, x1 = int(t["cx"] - t["rx"]) - 1, int(t["cx"] + t["rx"]) + 2
    y0, y1 = int(t["yc"] - t["ry"]) - 1, int(t["yc"] + t["ry"]) + 2
    yy, xx = np.mgrid[y0:y1, x0:x1]
    sel = ((xx - t["cx"]) / (t["rx"] * 0.5)) ** 2 + ((yy - t["yc"]) / (t["ry"] * 0.5)) ** 2 <= 1
    return np.median(game[y0:y1, x0:x1][sel], axis=0)


def render_tin(t, paint, drawing, spec):
    """(x0, y0, rgb, alpha) of one tin in the 4x menu.

    The drawn tin is unrolled round the game's cylinder. The label keeps the
    height-to-width ratio of the drawing, stretched at most label_stretch.
    Height the game's tin has beyond the label goes to label paper above it
    (label_from_top) and to bare silver tin below it.
    """
    d, lid, ss = spec["drawn"], spec["lid"], spec["supersample"]
    grow = spec["grow"]
    cx, rx, yc, ry, yb = t["cx"], t["rx"] + grow, t["yc"], t["ry"] + grow * 0.5, t["yb"] + spec["grow_bottom"]
    x0, x1 = int(cx - rx) - 2, int(cx + rx) + 3
    y0, y1 = int(yc - ry) - 2, int(yb) + 3
    ys, xs = np.mgrid[y0 * ss:y1 * ss, x0 * ss:x1 * ss].astype(np.float32)
    xs, ys = (xs + 0.5) / ss, (ys + 0.5) / ss
    u = (xs - cx) / rx
    inside = np.abs(u) <= 1
    arc = np.sqrt(np.clip(1 - u * u, 0, 1))
    top = u * u + ((ys - yc) / ry) ** 2 <= 1
    yc_bot = yb - ry
    body = inside & (ys >= yc) & (ys <= yc_bot + ry * arc)
    tx, ty = d["cx"] + u * d["rx"], d["yc"] + (ys - yc) / ry * d["ry"]
    game_h, drawn_h = yc_bot - yc, (d["ybot"] - d["ry"]) - d["yc"]
    k_nat = d["rx"] / rx
    stretch = min(max(game_h * k_nat / drawn_h, 1.0), spec["label_stretch"])
    k = k_nat / stretch
    off = max((game_h - drawn_h / k) * spec["label_from_top"], 0)
    hd = (ys - (yc + ry * arc) - off) * k
    below = hd > drawn_h
    hd = np.where(hd < 0, spec["label_paper"], np.minimum(hd, drawn_h - 1))
    sx = np.where(top, tx, d["cx"] + u * d["rx"])
    sy = np.where(top, ty, d["yc"] + d["ry"] * arc + hd)
    rgb = bilinear(drawing, sx, sy)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    red = np.clip((r - np.maximum(g, b) - 22) / 40, 0, 1) * top
    light = (0.299 * r + 0.587 * g + 0.114 * b)[..., None]
    recoloured = np.clip(paint[None, None, :] * (light / spec["lid_red_luminance"]), 0, 255)
    rgb = rgb * (1 - red[..., None]) + recoloured * red[..., None]
    rr = np.sqrt(u * u + ((ys - yc) / ry) ** 2)
    on_lid = top & (rr < lid["rim"])
    shade = 1 + lid["back_light"] * (-(ys - yc) / ry)
    shade = np.where((rr > lid["groove"][0]) & (rr < lid["groove"][1]), shade * lid["groove_dark"], shade)
    rgb = np.where(on_lid[..., None], np.clip(paint[None, None, :] * shade[..., None] * lid["paint_light"], 0, 255), rgb)
    silver = np.array(spec["silver"], np.float32)
    rgb = np.where((below & body & ~top)[..., None], silver * (0.75 + 0.35 * arc[..., None]), rgb)
    rgb = rgb * np.where(body & ~top, spec["side_dark"] + (1 - spec["side_dark"]) * arc ** 0.7, 1.0)[..., None]
    alpha = (top | body).astype(np.float32)
    h, w = y1 - y0, x1 - x0
    return x0, y0, rgb.reshape(h, ss, w, ss, 3).mean((1, 3)), alpha.reshape(h, ss, w, ss).mean((1, 3))


def build(game, spec, made_faces, drawing):
    canvas = game.copy()
    for item in spec["faces"]:
        face = made_faces[item["name"]]
        x0, y0, rgb, a = warp_face(face, item["quad"])
        g = game[y0:y0 + a.shape[0], x0:x0 + a.shape[1]]
        paper = None
        if "paper_from" in item:
            quad = next(other["quad"] for other in spec["faces"] if other["name"] == item["paper_from"])
            ox, oy, _, oa = warp_face(face, quad)
            paper = (game[oy:oy + oa.shape[0], ox:ox + oa.shape[1]], oa)
        rgb = soften(colour_fit(rgb, g, a, spec["colour_fit"], paper), spec["soften"])
        paste(canvas, x0, y0, rgb, feather(a, *spec["feather"]))
    tins = spec["tins"]
    for name in tins["order"]:
        t = tins["tins"][name]
        x0, y0, rgb, a = render_tin(t, paint_colour(game, t), drawing, tins)
        g = game[y0:y0 + a.shape[0], x0:x0 + a.shape[1]]
        rgb = soften(colour_fit(rgb, g, a, tins["colour_fit"]), tins["soften"])
        paste(canvas, x0, y0, rgb, feather(a, *tins["feather"]))
    return canvas


def read_rgba(piece):
    with open(piece["file"], "rb") as f:
        return np.frombuffer(f.read(), np.uint8).reshape(piece["h"], piece["w"], 4)


def psnr(big, original, times):
    h, w = original.shape[:2]
    small = big.astype(np.float64).reshape(h, times, w, times, 4).mean((1, 3))
    seen = original[..., 3] > 0
    diff = (small[..., :3] - original[..., :3])[seen]
    mse = float((diff ** 2).mean()) if diff.size else 0.0
    return 99.0 if mse == 0 else round(10 * np.log10(255 * 255 / mse), 2)


def main():
    with open(sys.argv[1]) as f:
        job = json.load(f)
    with open(job["spec"]) as f:
        spec = json.load(f)
    times = job["times"]
    faces = Faces(spec, job["references"], job["fonts"])
    shade = spec["side_shade"]
    made_faces = {}
    for item in spec["faces"]:
        face = getattr(faces, item["make"])(item.get("kit"))
        made_faces[item["name"]] = shade_top(face, shade["top"], shade["foot"]) if item.get("shade_top") else face
    drawing = np.asarray(Image.open(job["references"][spec["tins"]["drawing"]]).convert('RGB')).astype(np.float32)
    full_w, full_h = job["size"]
    base = Image.new('RGBA', (full_w, full_h))
    for piece in job["pieces"]:
        base.paste(Image.fromarray(read_rgba(piece)), (piece["x"], piece["y"]))
    runs = [(None, base, job["pieces"])] + [(state, base, laid) for state, laid in sorted(job["states"].items())]
    for state, screen, laid in runs:
        if state:
            screen = screen.copy()
            for piece in laid:
                screen.alpha_composite(Image.fromarray(read_rgba(piece)), (piece["x"], piece["y"]))
        game = np.asarray(screen.convert('RGB')).astype(np.float32)
        drawn = Image.fromarray(np.round(build(game, spec, made_faces, drawing)).astype(np.uint8))
        for piece in laid:
            made = read_rgba(piece)
            cut = np.asarray(drawn.crop((piece["x"], piece["y"], piece["x"] + piece["w"], piece["y"] + piece["h"])).convert('RGBA')).copy()
            cut[..., 3] = made[..., 3]
            with open(piece["out"], "wb") as f:
                f.write(cut.tobytes())
            with open(piece["original"], "rb") as f:
                original = np.frombuffer(f.read(), np.uint8).reshape(piece["h"] // times, piece["w"] // times, 4).astype(np.float64)
            print(json.dumps({"path": piece["path"], "changed": bool((cut != made).any()),
                              "match": psnr(cut, original, times), "made_match": psnr(made, original, times)}), flush=True)
    print(json.dumps({"numpy": np.__version__, "pillow": PIL.__version__}), flush=True)


if __name__ == "__main__":
    main()
