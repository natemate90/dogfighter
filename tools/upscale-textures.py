#!/usr/bin/env python3
"""Makes larger copies of the game's 3D textures for ./dogfighter, which uses them by default.

It reads the textures from the packs in game/, resizes them 2x or 4x and
writes them as loose files to hd-textures/cache/<path in the pack>. The game
looks in a folder named cache before it looks in its packs, and the launcher
links game/cache to that folder. The packs are never changed.

Kept: Graphics\\Textures, Graphics\\Models, Graphics\\Backdrops and
Graphics\\Effects, which are only ever stretched over 3D shapes.

The game draws the pictures of the menus, the loading screens and the HUD at
the size stored in the file. Those listed in tools/menu-pictures.json are made
2x or 4x, whatever --scale says, each with an empty file <name>.2x or
<name>.4x next to it; the launcher's helper draws a picture with that marker
at its old size. tools/menus.py says how the list is read. A screen made of
tiles is put together, resized as one picture and cut again. --no-menus
leaves them all out. --menus-only adds them to a complete set and keeps that
set's settings. The rest of Graphics\\Frontend and Graphics\\Ingame is left
out.

The font pictures in Graphics\\Fonts are made 2x as well, never 4x. Next to
each goes an empty file <name>.gti.2x. The launcher's helper draws a picture
with that marker at its old size, so letters keep their place and size.
  - The letter shapes are the picture's alpha. They go to the upscaler as a
    grey picture, are pulled back and checked like a colour picture. The
    colour itself goes through the plain filter.
  - waifu2x is tried first, then the plain filter. On sheets of all eleven
    pictures waifu2x gave the cleanest letters; Real-ESRGAN left grey smears.
  - A pixel that was empty in the original is empty in the result, so no
    letter grows into its neighbour. The manifest holds two scores for it:
    spill, the largest alpha the resizer had put on such a pixel outside
    every glyph box of the .fnt tables, and outside_glyph_boxes, the number
    of such pixels left after emptying. That number is 0.

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

A fourth way, generative, is used only for the textures listed in
tools/generative-surfaces.json, and only when --fetch-tools --generative has
set it up in upscale-tools/generative/. It starts from the texture's faithful
result and redraws it 4x with Stable Diffusion 1.5 and the ControlNet 1.1 tile
model, in tools/generative-upscale.py, run by that folder's own Python. Its
checks and limits are in that file and in GENERATIVE_SETTINGS below. A texture
that fails them keeps its faithful result. The manifest records the prompt,
strength, seed and model checksums under "asked"; when any of them changes, the
texture is made again. The list is checked by eye: the model can draw things
that are not in the original and still pass every check.

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

Your own textures: every .gti under texture-overrides/, at the same path as in
hd-textures/cache/, takes the place of the made texture. It must have the
size, the pixel format and the number of mipmap levels of the made one, and
gets no other check. The manifest lists it with way "override" and its
checksum. The made texture waits in hd-textures/replaced/ and comes back when
the override is gone.

Lettering: the textures in tools/lettering.json get their short words set
again with real fonts, over the made texture, by tools/lettering.py. The
manifest lists such a texture with way "lettering", its scores and the fonts'
checksums. An override in texture-overrides/ wins over it, and --no-lettering
leaves every texture as made. The fonts that are not on every Mac come with
--fetch-tools or --fetch-fonts; without them those textures stay as made.
--lettering-only redraws just the lettering of a complete set, with the
settings stored in its manifest, so a set made with --scale 4 or the plain
filter alone is not made again.

A run makes only what is missing or changed. With --only the rest of the set
stays as it is. Files reach the set one by one, each by a rename, and the
manifest is written last. So a run that stops leaves a set the game can load,
and the next run finishes it.

Helpers, built with the Xcode Command Line Tools. Both read jobs on stdin as
fields that each end in a NUL byte, so a path may hold spaces.
  tools/vimage-scale.c    IN OUT WIDTH HEIGHT NEW_WIDTH NEW_HEIGHT, raw RGBA.
  tools/texture-refine.c  Prints one line per job, "ok ..." or "fail <why>".
      bleed IN OUT WIDTH HEIGHT
      refine ORIGINAL PLAIN DETAIL OUT WIDTH HEIGHT SCALE BORDER PASSES
      glyphs, with the same fields, is refine for letter shapes: the last
        pull-back is repeated until values cut off at 0 or 255 no longer
        keep a block from its original.
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
import re
import shutil
import struct
import subprocess
import sys
import time
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gti  # noqa: E402
import lettering  # noqa: E402
import menus  # noqa: E402
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
ASIDE = "replaced"
FONTS = "graphics\\fonts\\"
TWICE = ".2x"
SCREEN_NUMBERS = 100000
FONT_WAY = "waifu2x"
OWN = ("way", "why", "scores", "failed", "bytes", "file_sha256")
GENERATIVE = "generative"
REPLACING = ("override", lettering.WAY)
COUNTED = WAYS + (GENERATIVE,) + REPLACING + ("none",)
GENERATIVE_LIST = os.path.join(HERE, "generative-surfaces.json")
GENERATIVE_SCALE = 4
GENERATIVE_SETTINGS = {
    "seed": 1234, "steps": 20, "guidance": 5.0, "control": 1.0, "cutoff": 2,
    "limits": {"drift": 18.0, "match": 26.0}, "stop_free": 15, "abort_free": 10,
    "style": "photo-real material texture, flat even lighting, highly detailed, sharp focus, seen straight on",
    "negative": "text, letters, logo, watermark, signature, objects, people, face, frame, border, perspective, "
                "shadows, vignette, blurry, lowres, jpeg artifacts, cartoon, painting, oversaturated",
}
HF = "https://huggingface.co/"
SD15 = HF + "stable-diffusion-v1-5/stable-diffusion-v1-5/resolve/451f4fe16113bff5a5d2269ed5ad43b0592e9a14/"
CN_TILE = HF + "lllyasviel/control_v11f1e_sd15_tile/resolve/3f877705c37010b7221c3d10743307d6b5b6efac/"
GENERATIVE_MODELS = {
    "sd15/v1-5-pruned-emaonly.safetensors": "6ce0161689b3853acaa03779ec93eafe75a02f4ced659bee03f50797806fa2fa",
    "sd15/model_index.json": "e2f6f22e274374010aec30c79eb2d6e53fff4a36ac0225523a92cb2d41a83347",
    "sd15/scheduler/scheduler_config.json": "699cce92eb7c122e2eb7dfdea78e6187fda76a5ed4a8e42319b85610e620e091",
    "sd15/text_encoder/config.json": "845df614cb9327ae7bbea027316246fae917827407da6df13572e41b5f93b4cc",
    "sd15/unet/config.json": "78f474de6bab3d893868f37be97b636ae65c0df3073ed3256ca458ff599b5f96",
    "sd15/vae/config.json": "786a7d21647ddea6a04b9675c03d3cb45e90a2f3c6da5fbda2c54ade040036de",
    "sd15/tokenizer/merges.txt": "9fd691f7c8039210e0fced15865466c65820d09b63988b0174bfe25de299051a",
    "sd15/tokenizer/vocab.json": "e089ad92ba36837a0d31433e555c8f45fe601ab5c221d4f607ded32d9f7a4349",
    "sd15/tokenizer/special_tokens_map.json": "c4864a9376a8401918425bed71fc14fc0e81f9b59ec45c1cf96cccb2df508eac",
    "sd15/tokenizer/tokenizer_config.json": "00439066fcba73de57644cf41e4e3b9f2dbb09d7f3fc2005898ba52399045882",
    "cn-tile/config.json": "c6488d01fc339c83d777b6d71df4f5bc36c035b2c977f987e8a5c0a54c79b706",
    "cn-tile/diffusion_pytorch_model.safetensors": "92ef6ffc6056db572a86b996f4427c39089bb7ec878a7e06a01c649ddef9e165",
}
CN_TILE_PICKLE = ("diffusion_pytorch_model.bin", "eb05b4c3665bd76dad70a90652014a9b3aab391abd8a5bb484e860330f9492fb")
GENERATIVE_PYTHON = (3, 12)

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


def fetch_fonts(tools):
    """Downloads the pinned lettering fonts and their licences. One that fails costs only its textures their lettering."""
    good = True
    for name, font in sorted(lettering.load_spec()["fonts"].items()):
        if "url" not in font:
            continue
        folder = os.path.join(tools, "fonts", font["folder"])
        for target, url, digest in ((os.path.join(folder, name), font["url"], font["sha256"]),
                                    (os.path.join(folder, font["licence"]["file"]), font["licence"]["url"], font["licence"]["sha256"])):
            try:
                download(url, target, digest)
            except SystemExit as problem:
                print(problem)
                good = False
    if good:
        print("The lettering fonts are in %s. Their checksums match." % os.path.join(tools, "fonts"))
    else:
        print("The labels that need a missing font stay as made.")


def lettering_fonts(tools):
    """{name: (file, checksum, None)} for each font of tools/lettering.json that can be used, else (None, None, why)."""
    found = {}
    for name, font in lettering.load_spec()["fonts"].items():
        path = font["system"] if "system" in font else os.path.join(tools, "fonts", font["folder"], name)
        digest = sha256_of(path) if os.path.isfile(path) else None
        if digest is None:
            why = "font %s is not on this Mac" % name if "system" in font else "font %s is missing; --fetch-fonts fetches it" % name
            found[name] = (None, None, why)
        elif "system" not in font and digest != font["sha256"]:
            found[name] = (None, None, "font %s does not match its pinned checksum" % name)
        else:
            found[name] = (path, digest, None)
    return found


def generative_stack(tools, log):
    """Where the generative way's Python and models are, or None when it is not set up."""
    folder = os.path.join(tools, GENERATIVE)
    python = os.path.join(folder, "venv", "bin", "python")
    models = os.path.join(folder, "models")
    if not os.access(python, os.X_OK) or not all(os.path.isfile(os.path.join(models, *name.split("/"))) for name in GENERATIVE_MODELS):
        return None
    return {"python": python, "models": models, "log": log}


def check_generative_models(setup):
    """Refuses the generative way for this run when a model file is not the pinned one."""
    stack = setup["generative_stack"]
    wrong = [name for name, digest in GENERATIVE_MODELS.items() if sha256_of(os.path.join(stack["models"], *name.split("/"))) != digest]
    if wrong and not setup["allow_other_tools"]:
        stack["refused"] = "model files differ from the pinned ones: " + ", ".join(wrong)
        print("The generative way is off for this run: %s. Fetch them again with --fetch-tools --generative." % stack["refused"])


def generative_python():
    """A Python of at least GENERATIVE_PYTHON: the one running this tool, else one from Homebrew or python.org."""
    if sys.version_info[:2] >= GENERATIVE_PYTHON:
        return sys.executable
    for minor in range(20, GENERATIVE_PYTHON[1] - 1, -1):
        name = "python3.%d" % minor
        for found in (shutil.which(name), "/opt/homebrew/bin/" + name, "/usr/local/bin/" + name,
                      "/Library/Frameworks/Python.framework/Versions/3.%d/bin/%s" % (minor, name)):
            if found and os.access(found, os.X_OK):
                return found
    return None


def download(url, target, digest):
    """Fetches url to target unless a file with that checksum is there. Stops the tool on a wrong checksum."""
    if os.path.isfile(target) and sha256_of(target) == digest:
        return
    os.makedirs(os.path.dirname(target), exist_ok=True)
    print("Downloading " + url)
    part = target + ".part"
    if subprocess.run(["/usr/bin/curl", "-fL", "--retry", "3", "--progress-bar", "-C", "-", "-o", part, url]).returncode:
        sys.exit("Download failed: " + url)
    if sha256_of(part) != digest:
        os.remove(part)
        sys.exit("%s does not match its pinned SHA-256 checksum. It was deleted." % url)
    os.replace(part, target)


def fetch_generative(tools):
    """Sets up upscale-tools/generative: a Python environment with the pinned packages, and the two pinned models.

    The tile ControlNet is published only as a pickle file. It is read once with
    torch's weights-only loader, which cannot run code, and saved as safetensors.
    """
    folder = os.path.join(tools, GENERATIVE)
    models = os.path.join(folder, "models")
    venv = os.path.join(folder, "venv")
    python = os.path.join(venv, "bin", "python")
    requirements = os.path.join(HERE, "generative-requirements.txt")
    if shutil.disk_usage(tools if os.path.isdir(tools) else os.path.dirname(tools)).free < 9e9 and not generative_stack(tools, ""):
        sys.exit("The generative way needs about 9 GB of free disk space while it is set up, 6.6 GB after.")
    if not os.access(python, os.X_OK):
        base = generative_python()
        if not base:
            sys.exit("The generative way needs Python %d.%d or later; the Xcode Command Line Tools have 3.9. "
                     "Install one, for example with 'brew install python', then run this again." % GENERATIVE_PYTHON)
        print("Making a Python environment in %s with %s" % (venv, base))
        subprocess.run([base, "-m", "venv", venv], check=True)
    env = dict(os.environ, PIP_CACHE_DIR=os.path.join(folder, "cache", "pip"), PIP_DISABLE_PIP_VERSION_CHECK="1")
    with open(requirements) as f:
        wanted = sorted(line.strip().lower() for line in f if line.strip() and not line.startswith("#"))
    have = subprocess.run([python, "-I", "-m", "pip", "freeze"], env=env, capture_output=True, text=True).stdout
    if sorted(line.strip().lower() for line in have.splitlines() if line.strip()) != wanted:
        subprocess.run([python, "-I", "-m", "pip", "install", "--only-binary", ":all:", "--no-deps", "-r", requirements],
                       env=env, check=True)
        subprocess.run([python, "-I", "-m", "pip", "check"], env=env, check=True)
    for name, digest in GENERATIVE_MODELS.items():
        target = os.path.join(models, *name.split("/"))
        if name.endswith("diffusion_pytorch_model.safetensors"):
            if os.path.isfile(target) and sha256_of(target) == digest:
                continue
            pickle = os.path.join(os.path.dirname(target), CN_TILE_PICKLE[0])
            download(CN_TILE + CN_TILE_PICKLE[0], pickle, CN_TILE_PICKLE[1])
            print("Converting the tile ControlNet to safetensors with the weights-only loader")
            subprocess.run([python, "-I", "-c", "import sys, torch, safetensors.torch as st; "
                            "st.save_file(torch.load(sys.argv[1], map_location='cpu', weights_only=True), sys.argv[2])",
                            pickle, target + ".part"], check=True)
            if sha256_of(target + ".part") != digest:
                os.remove(target + ".part")
                sys.exit("The converted tile ControlNet does not match its pinned checksum. The pickle is kept in " + pickle)
            os.replace(target + ".part", target)
            os.remove(pickle)
        else:
            base = SD15 if name.startswith("sd15/") else CN_TILE
            download(base + name.split("/", 1)[1], target, digest)
    print("The generative way is set up in %s. Its models match their pinned checksums." % folder)


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
    """Runs in a worker: cut the border off, tidy alpha, write the .gti, or one for each piece of a screen."""
    scale, edge = job["scale"], job.get("edge", BORDER * job["scale"])
    width, height = job["width"] * scale, job["height"] * scale
    with open(job["scaled"], "rb") as f:
        pixels = bytearray(f.read())
    if len(pixels) != (width + 2 * edge) * (height + 2 * edge) * 4:
        raise ValueError("%s: resized picture has the wrong size" % job["path"])
    if job["kind"] == "cutout":
        pixels[3::4] = pixels[3::4].translate(bytes(255 if i >= 128 else 0 for i in range(256)))
    extra = {}
    if job["kind"] == "font":
        with open(job["colour"] + ".plain", "rb") as f:
            colour = f.read()
        pixels[3::4] = pixels[0::4]
        pixels[0::4], pixels[1::4], pixels[2::4] = colour[0::4], colour[1::4], colour[2::4]
    pixels = without_border(bytes(pixels), width, height, edge)
    if job["kind"] == "font":
        pixels, extra = fenced(job, pixels)
    parts = [] if "cut" in job else [(job["path"], job["target"], width, height, job["alpha"], pixels)]
    if "cut" in job:
        for path, target, x, y, w, h, alpha, cutout in job["cut"]:
            part = menus.cut(pixels, width, x * scale, y * scale, w * scale, h * scale)
            if cutout:
                part = bytearray(part)
                part[3::4] = part[3::4].translate(bytes(255 if i >= 128 else 0 for i in range(256)))
            parts.append((path, target, w * scale, h * scale, alpha, bytes(part)))
    written = []
    for path, target, width, height, alpha, pixels in parts:
        if target.lower().endswith(".tga"):
            data = menus.write_tga(width, height, pixels, alpha)
        else:
            data = gti.encode(width, height, pixels, alpha, None if job["mipmaps"] else 1)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as f:
            f.write(data)
        written.append((path, len(data), hashlib.sha256(data).hexdigest(), extra))
    return written


def fenced(job, pixels):
    """Empties every pixel of a font picture whose original pixel was empty, so no letter grows into its neighbour.

    Also says how much the resizer had put outside all glyph boxes on such
    pixels (spill, the largest alpha), and counts what is left there: 0.
    """
    scale, width, height = job["scale"], job["width"], job["height"]
    with open(job["source"], "rb") as f:
        ink = without_border(f.read(), width, height, BORDER)[0::4]
    boxed = bytearray(width * height)
    for x, y, w, h in job["boxes"]:
        for row in range(y, min(height, y + h)):
            boxed[row * width + x:row * width + min(width, x + w)] = b"\1" * (min(width, x + w) - x)
    keep, free = bytearray(), bytearray()
    for row in range(height):
        at = slice(row * width, (row + 1) * width)
        keep += b"".join(bytes([255 if value else 0]) * scale for value in ink[at]) * scale
        free += b"".join(bytes([0 if value or inside else 255]) * scale for value, inside in zip(ink[at], boxed[at])) * scale
    count = len(keep)
    alpha = int.from_bytes(pixels[3::4], "big")
    spill = max((alpha & int.from_bytes(free, "big")).to_bytes(count, "big"))
    alpha &= int.from_bytes(keep, "big")
    left = count - (alpha & int.from_bytes(free, "big")).to_bytes(count, "big").count(0)
    pixels = bytearray(pixels)
    pixels[3::4] = alpha.to_bytes(count, "big")
    return bytes(pixels), {"spill": spill, "outside_glyph_boxes": left}


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


def picture_of(name, data):
    """(width, height, RGBA, has alpha, has mipmaps) of a .gti or a .tga."""
    if name.lower().endswith(".tga"):
        return menus.read_tga(data) + (False,)
    best = gti.parse(data).best()
    return gti.to_rgba(best) + (best.alpha, len(best.levels) > 1)


def kind_of(pixels, has_alpha):
    alphas = set(pixels[3::4]) if has_alpha else {255}
    return "opaque" if not has_alpha else "cutout" if alphas <= {0, 255} else "alpha", alphas


def menu_ways(setup, plan):
    return tuple(way for way in plan["ways"] if way in setup["ways"]) or ("plain",)


def prepare(number, pack, entry, data, setup, folder, fresh):
    plan = setup["menu"].get(entry.path)
    scale = plan["times"] if plan else setup["scale"]
    width, height, pixels, has_alpha, mipmaps = picture_of(entry.name, data)
    record = {"path": entry.path, "pack": os.path.basename(pack.path), "source_sha256": hashlib.sha256(data).hexdigest(),
              "size": [width, height]}
    font = entry.path.lower().startswith(FONTS)
    if font:
        record.update(asked=font_way(setup))
    if plan:
        record.update(asked=menus.asked(plan), marked=scale)
    if width * scale > 1024 or height * scale > 1024:
        record.update(way="none", why="would pass 1024 pixels")
        return None, record
    kind, alphas = kind_of(pixels, has_alpha)
    wrap_x = tiles_across(pixels, width)
    wrap_y = tiles_across(turned(pixels, width, height), height)
    if font:
        kind, wrap_x, wrap_y = "font", False, False
    record.update(kind=kind, tiles=[wrap_x, wrap_y])
    stem = os.path.join(folder, "%05d" % number)
    job = {
        "path": entry.path, "number": number, "scale": scale, "width": width, "height": height,
        "alpha": has_alpha, "mipmaps": mipmaps, "kind": kind,
        "wrap_x": wrap_x, "wrap_y": wrap_y, "bleed": 0 in alphas and len(alphas) > 1,
        "source": stem + ".in", "plain": stem + ".plain", "stem": stem,
        "target": os.path.join(fresh, *up.safe_parts(entry.path)),
    }
    if plan:
        job["ways"] = menu_ways(setup, plan)
    if font:
        boxes = setup["glyphs"].get(os.path.splitext(entry.name)[0].lower(), [])
        record.update(glyphs=len(boxes))
        job.update(alpha=True, boxes=boxes, colour=stem + ".rgb", ways=(record["asked"], "plain"))
        with open(job["colour"], "wb") as f:
            f.write(with_border(pixels, width, height, False, False))
        shape = bytearray(pixels)
        shape[0::4] = shape[1::4] = shape[2::4] = pixels[3::4]
        shape[3::4] = b"\xff" * (width * height)
        pixels = bytes(shape)
    with open(job["source"], "wb") as f:
        f.write(with_border(pixels, width, height, wrap_x, wrap_y))
    return job, record


def prepare_screen(number, name, members, setup, folder, fresh):
    """One job for a screen and one for each of its states. Returns the jobs and a record for every piece."""
    screen = setup["screens"][name]
    scale = screen["times"]
    full_w, full_h = screen["size"]
    pieces, records = {}, []
    for pack, entry, data in members:
        plan = setup["menu"][entry.path]
        width, height, pixels, has_alpha, _ = picture_of(entry.name, data)
        kind, _ = kind_of(pixels, has_alpha)
        pieces.setdefault(plan["state"], []).append((entry.path, plan["at"], width, height, pixels, has_alpha, kind))
        records.append({"path": entry.path, "pack": os.path.basename(pack.path), "source_sha256": hashlib.sha256(data).hexdigest(),
                        "size": [width, height], "kind": kind, "tiles": [False, False], "asked": menus.asked(plan), "marked": scale,
                        "screen": name})
    jobs = []
    base = [(x, y, width, height, pixels) for _, (x, y), width, height, pixels, _, _ in pieces[None]]
    for count, state in enumerate(sorted(pieces, key=lambda state: state or "")):
        laid = pieces[state]
        canvas = menus.composed((full_w, full_h), base + [(x, y, width, height, pixels) for _, (x, y), width, height, pixels, _, _ in laid if state])
        kind, alphas = kind_of(canvas, any(has_alpha for _, _, _, _, _, has_alpha, _ in pieces[None] + laid))
        stem = os.path.join(folder, "%06d" % (SCREEN_NUMBERS + number * 256 + count))
        job = {
            "path": "screen %s%s" % (name, " with " + state if state else ""), "paths": [path for path, _, _, _, _, _, _ in laid],
            "number": SCREEN_NUMBERS + number * 256 + count, "scale": scale, "width": full_w, "height": full_h,
            "alpha": kind != "opaque", "mipmaps": False, "kind": "opaque" if kind == "opaque" else "alpha",
            "wrap_x": False, "wrap_y": False, "bleed": 0 in alphas and len(alphas) > 1,
            "source": stem + ".in", "plain": stem + ".plain", "stem": stem, "ways": menu_ways(setup, screen),
            "cut": [(path, os.path.join(fresh, *up.safe_parts(path)), x, y, width, height, has_alpha, piece_kind == "cutout")
                    for path, (x, y), width, height, _, has_alpha, piece_kind in laid],
        }
        with open(job["source"], "wb") as f:
            f.write(with_border(bytes(canvas), full_w, full_h, False, False))
        jobs.append(job)
    return jobs, records


def touched(job, records):
    """The records of the files a job writes: one, or every piece of a screen."""
    return [records[path] for path in job.get("paths", (job["path"],))]


def font_way(setup):
    """The way a font picture tries first; the plain filter is its only other one."""
    way = setup["font_way"] or FONT_WAY
    return way if way in setup["ways"] else "plain"


def glyph_boxes(packs):
    """{font picture: [(x, y, width, height)]} from the .fnt tables, whose lines read 'A' = X Y WIDTH HEIGHT PICTURE."""
    boxes = {}
    for pack in packs:
        for entry in pack.entries:
            if entry.path.lower().startswith(FONTS) and entry.name.lower().endswith(".fnt"):
                for line in pack.read(entry).decode("latin-1").splitlines():
                    found = re.match(r"\s*'.+'\s*=\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\S+)\s*$", line)
                    if found:
                        boxes.setdefault(found.group(5).lower(), []).append(tuple(int(found.group(i)) for i in range(1, 5)))
    return boxes


def run_batch(setup, items, fresh, pool):
    """Takes a list of (number, pack, entry, data) all the way to .gti files. Returns one record per texture."""
    helpers = setup["helpers"]
    folder = os.path.join(setup["work"], "batch")
    shutil.rmtree(folder, ignore_errors=True)
    os.makedirs(folder)
    jobs, records = [], {}
    for item in items:
        if len(item) == 3:
            made, listed = prepare_screen(*item, setup, folder, fresh)
        else:
            job, record = prepare(*item, setup, folder, fresh)
            made, listed = [job] if job else [], [record]
        jobs += made
        records.update((record["path"], record) for record in listed)

    fields = []
    for job in jobs:
        if job["bleed"]:
            picture = job.get("colour", job["source"])
            fields += ["bleed", picture, picture, job["width"] + 2 * BORDER, job["height"] + 2 * BORDER]
    if "fail" in [line.split()[0] for line in run_jobs(helpers["texture-refine"], fields, True)]:
        sys.exit("tools/texture-refine.c could not prepare a texture. Nothing was replaced.")
    fields = []
    for job in jobs:
        full_w, full_h = job["width"] + 2 * BORDER, job["height"] + 2 * BORDER
        fields += [job["source"], job["plain"], full_w, full_h, full_w * job["scale"], full_h * job["scale"]]
        if "colour" in job:
            fields += [job["colour"], job["colour"] + ".plain", full_w, full_h, full_w * job["scale"], full_h * job["scale"]]
    run_jobs(helpers["vimage-scale"], fields)

    left = jobs
    for way in setup["ways"]:
        waiting = [job for job in left if way in job.get("ways", setup["ways"])]
        left = [job for job in left if job not in waiting]
        if not waiting:
            continue
        for times in sorted({job["scale"] for job in waiting} if way == "waifu2x" else {0} if way == "ai" else ()):
            source, target = os.path.join(folder, "%s-in-%d" % (way, times)), os.path.join(folder, "%s-out-%d" % (way, times))
            os.makedirs(source)
            os.makedirs(target)
            for job in waiting:
                if times not in (0, job["scale"]):
                    continue
                with open(job["source"], "rb") as f:
                    bordered = f.read()
                with open(os.path.join(source, "%05d.png" % job["number"]), "wb") as f:
                    f.write(gti.write_png(job["width"] + 2 * BORDER, job["height"] + 2 * BORDER, bordered, False))
            run_upscaler(way, setup["tools"], source, target, times, setup["work"])
        fields = []
        for job in waiting:
            detail = os.path.join(folder, "%s-out-%d" % (way, job["scale"] if way == "waifu2x" else 0), "%05d.png" % job["number"]) if way != "plain" else ""
            fields += ["glyphs" if job["kind"] == "font" else "refine", job["source"], job["plain"], detail, "%s.%s" % (job["stem"], way),
                       job["width"] + 2 * BORDER, job["height"] + 2 * BORDER, job["scale"], BORDER,
                       PASSES if way != "plain" or job["kind"] == "font" else 0]
        lines = run_jobs(helpers["texture-refine"], fields, True)
        if len(lines) != len(waiting):
            sys.exit("tools/texture-refine.c answered %d of %d jobs. Nothing was replaced." % (len(lines), len(waiting)))
        for job, line in zip(waiting, lines):
            if line.startswith("ok "):
                names = ("drift", "match", "worst", "seam_x", "inside_x", "seam_y", "inside_y", "original_seam_x", "original_seam_y")
                scores = dict(zip(names, (float(value) for value in line.split()[1:])))
                why = verdict(way, scores, job["wrap_x"], job["wrap_y"])
            else:
                scores, why = None, line[5:]
            if why is None:
                job["scaled"] = "%s.%s" % (job["stem"], way)
            else:
                left.append(job)
            for record in touched(job, records):
                if why is None:
                    record.update(way=way, scores=dict(scores))
                else:
                    record.setdefault("failed", []).append({"way": way, "why": why, "scores": scores})
    for job in left:
        for record in touched(job, records):
            record.update(way="none", why="failed every check")
    listed = [job for job in jobs if "scaled" in job and job["path"] in setup["generative"]]
    if listed:
        redraw(setup, listed, records, folder)

    written = [job for job in jobs if "scaled" in job]
    scales = {path: job["scale"] for job in written for path in job.get("paths", (job["path"],))}
    for files in pool.imap_unordered(finish, written, 8):
        for path, size, digest, extra in files:
            records[path].update(out=[side * scales[path] for side in records[path]["size"]], bytes=size, file_sha256=digest)
            records[path]["scores"].update(extra)
    shutil.rmtree(folder, ignore_errors=True)
    return list(records.values())


def generative_asked(setup, path):
    """What a listed texture asks of the generative way; a texture is made again when this changes."""
    entry = setup["generative"][path]
    settings = GENERATIVE_SETTINGS
    tiling = "seamless tileable " if any(entry["tiles"]) else ""
    return {"way": GENERATIVE, "prompt": "%s%s, %s" % (tiling, entry["prompt"], settings["style"]), "negative": settings["negative"],
            "strength": entry["strength"], "tiles": entry["tiles"], "seed": settings["seed"], "steps": settings["steps"],
            "guidance": settings["guidance"], "control": settings["control"], "cutoff": settings["cutoff"],
            "limits": settings["limits"], "models": GENERATIVE_MODELS}


def redraw(setup, jobs, records, folder):
    """Runs the generative way on listed textures that already passed a faithful way, whose result is the start picture.

    A texture that passes is written 4x from the helper's picture. One that
    fails keeps its faithful result. A failure that is no fault of the texture
    (memory, a stopped helper) leaves "asked" out, so the next run tries again.
    """
    stack = setup["generative_stack"]
    task = {"models": stack["models"], "log": stack["log"], "settings": dict(GENERATIVE_SETTINGS), "jobs": []}
    for job in jobs:
        record = records[job["path"]]
        asked = generative_asked(setup, job["path"])
        if job["kind"] != "opaque" or max(job["width"], job["height"]) * GENERATIVE_SCALE > 1024:
            why = "has alpha" if job["kind"] != "opaque" else "would pass 1024 pixels"
            record.update(asked=asked)
            record.setdefault("failed", []).insert(0, {"way": GENERATIVE, "why": why, "scores": None})
            continue
        if stack.get("refused"):
            record.setdefault("failed", []).insert(0, {"way": GENERATIVE, "why": stack["refused"], "scores": None})
            continue
        width, height, scale = job["width"], job["height"], job["scale"]
        with open(job["source"], "rb") as f:
            original = without_border(f.read(), width, height, BORDER)
        with open(job["scaled"], "rb") as f:
            faithful = without_border(f.read(), width * scale, height * scale, BORDER * scale)
        for name, size, pixels in (("original", 1, original), ("faithful", scale, faithful)):
            with open("%s.%s.png" % (job["stem"], name), "wb") as f:
                f.write(gti.write_png(width * size, height * size, pixels, False))
        task["jobs"].append({"id": job["number"], "name": job["path"], "original": job["stem"] + ".original.png",
                             "faithful": job["stem"] + ".faithful.png", "faithful_scale": scale, "out": job["stem"] + ".generative.png",
                             "prompt": asked["prompt"], "strength": asked["strength"], "seed": asked["seed"], "tiles": asked["tiles"]})
    if not task["jobs"]:
        return
    with open(os.path.join(folder, "generative.json"), "w") as f:
        json.dump(task, f)
    by_number = {job["number"]: job for job in jobs}
    answered = set()
    helper = subprocess.Popen([stack["python"], "-I", os.path.join(HERE, "generative-upscale.py"), os.path.join(folder, "generative.json")],
                              stdout=subprocess.PIPE, text=True)
    for line in helper.stdout:
        try:
            said = json.loads(line)
            job = by_number[said["id"]]
        except (ValueError, KeyError, TypeError):
            continue
        answered.add(job["number"])
        record, why = records[job["path"]], said.get("why")
        scores = said.get("scores")
        print("  %s %s: %s%s" % (GENERATIVE, job["path"], why or "ok", ", %.1f s" % scores["seconds"] if scores else ""), flush=True)
        if not said.get("retry"):
            record.update(asked=generative_asked(setup, job["path"]))
        if why:
            record.setdefault("failed", []).insert(0, {"way": GENERATIVE, "why": why, "scores": scores})
            continue
        with open(job["stem"] + ".generative.png", "rb") as f:
            width, height, pixels, _ = gti.read_png(f.read())
        if (width, height) != (job["width"] * GENERATIVE_SCALE, job["height"] * GENERATIVE_SCALE):
            record.setdefault("failed", []).insert(0, {"way": GENERATIVE, "why": "the picture has the wrong size", "scores": scores})
            continue
        with open(job["stem"] + "." + GENERATIVE, "wb") as f:
            f.write(pixels)
        job.update(scale=GENERATIVE_SCALE, edge=0, scaled=job["stem"] + "." + GENERATIVE)
        record.update(way=GENERATIVE, scores=scores)
    code = helper.wait()
    for number in set(task_job["id"] for task_job in task["jobs"]) - answered:
        records[by_number[number]["path"]].setdefault("failed", []).insert(
            0, {"way": GENERATIVE, "why": "the generative helper stopped (exit %d)" % code, "scores": None})


def spread(values):
    values = sorted(values)
    return "lowest %.1f, 5%% under %.1f, middle %.1f" % (values[0], values[len(values) // 20], values[len(values) // 2])


def summary(records):
    counts = {way: sum(1 for record in records if record["way"] == way) for way in COUNTED}
    print("Ways: %d ai, %d waifu2x, %d plain, %d generative, %d override, %d lettering, %d not written." % tuple(
        counts[way] for way in COUNTED))
    for way in WAYS + (GENERATIVE,):
        scored = [record["scores"] for record in records if record["way"] == way]
        if scored:
            print("  %-8s match dB: %s" % (way, spread([s["match"] for s in scored])))
            if way != "plain":
                print("  %-8s drift dB: %s" % (way, spread([s["drift"] for s in scored])))
            if way in ("ai", "waifu2x"):
                print("  %-8s worst dB: %s" % (way, spread([s["worst"] for s in scored])))
    marked = [record.get("marked") for record in records if record["way"] != "none"]
    if marked.count(2) + marked.count(4):
        print("  menu, loading screen and HUD pictures: %d with 2 times the pixels a side, %d with 4 times" % (marked.count(2), marked.count(4)))
    fonts = [generated(record) for record in records if record.get("kind") == "font"]
    if fonts:
        print("  font pictures: " + ", ".join("%s %s" % (os.path.splitext(record["path"].split("\\")[-1])[0], record["way"])
                                                for record in fonts))
    for record in records:
        if record["way"] == "none":
            print("  not written: %s (%s)" % (record["path"], record["why"]))
    return counts


def main():
    root = os.path.dirname(HERE)
    parser = argparse.ArgumentParser(description="Make larger textures for ./dogfighter, which uses them by default.")
    parser.add_argument("--scale", type=int, choices=(2, 4), default=2, help="2 (default) or 4")
    parser.add_argument("--upscaler", choices=("auto", "ai", "vimage"), default="auto",
                        help="auto (default) uses the fetched upscalers if they are there, else the Mac's own vimage")
    parser.add_argument("--fetch-tools", action="store_true", help="download the pinned upscalers to upscale-tools/, then stop")
    parser.add_argument("--generative", action="store_true",
                        help="with --fetch-tools: also set up the generative way in upscale-tools/generative/ (about 6.6 GB)")
    parser.add_argument("--no-generative", action="store_true", help="do not use the generative way even when it is set up")
    parser.add_argument("--generative-log", default="", help="log of the generative way (default: generative.log in the output folder)")
    parser.add_argument("--tools", default=os.path.join(root, "upscale-tools"), help="folder with the upscalers (default: upscale-tools/)")
    parser.add_argument("--allow-other-tools", action="store_true", help="run upscalers whose checksums are not the pinned ones")
    parser.add_argument("--game", default=os.path.join(root, "game"), help="the installed game (default: game/)")
    parser.add_argument("--out", default=os.path.join(root, "hd-textures"), help="output folder (default: hd-textures/)")
    parser.add_argument("--overrides", default=os.path.join(root, "texture-overrides"),
                        help="folder with your own textures, which take the place of the made ones (default: texture-overrides/)")
    parser.add_argument("--only", default="", help="only textures whose path contains this text; the rest of the set stays as it is")
    parser.add_argument("--no-lettering", action="store_true", help="leave the textures of tools/lettering.json as made")
    parser.add_argument("--fetch-fonts", action="store_true", help="download the pinned lettering fonts to upscale-tools/fonts/, then stop")
    parser.add_argument("--lettering-only", action="store_true",
                        help="redraw only the lettering of the complete set in the output folder, keeping the settings that made it")
    parser.add_argument("--no-menus", action="store_true",
                        help="leave the menus, the loading screens and the HUD as the game has them")
    parser.add_argument("--menus-only", action="store_true",
                        help="make only the menu, loading screen and HUD pictures for the complete set in the output folder; the rest stays")
    parser.add_argument("--font-way", choices=WAYS, default="",
                        help="the way the font pictures try first (default: %s)" % FONT_WAY)
    parser.add_argument("--jobs", type=int, default=os.cpu_count() or 4, help="worker processes")
    parser.add_argument("--repeat", type=int, default=8, help="textures to make a second time, to see that the result is the same (default 8)")
    parser.add_argument("--sheets", default="", help="folder for PNG sheets that put the plain filter next to the set")
    parser.add_argument("--list", action="store_true", help="show what would be resized, then stop")
    parser.add_argument("--check", action="store_true",
                        help="exit 0 when the output folder holds a complete set, else 1; makes nothing")
    args = parser.parse_args()
    for name in ("tools", "game", "out", "overrides", "sheets", "generative_log"):
        if getattr(args, name):
            setattr(args, name, os.path.abspath(getattr(args, name)))
    tools = args.tools
    if args.check:
        sys.exit(0 if set_complete(args.out) else 1)

    if args.fetch_fonts or args.fetch_tools:
        fetch_fonts(tools)
    if args.fetch_fonts:
        return
    if args.fetch_tools:
        fetch_tools(root, tools)
        if args.generative:
            fetch_generative(tools)
        return
    if args.generative:
        sys.exit("--generative goes with --fetch-tools. A normal run uses the generative way when it is set up.")
    if args.lettering_only:
        sys.exit(relabel(args))
    args.rest_stays = bool(args.only) or args.menus_only
    stored = None
    if args.menus_only:
        if args.no_menus or not set_complete(args.out):
            sys.exit("--menus-only adds to a complete set, and %s holds none. Make one first: python3 tools/upscale-textures.py" % args.out)
        with open(os.path.join(args.out, MANIFEST)) as f:
            stored = json.load(f)
        args.scale = stored["settings"]["scale"]
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

    chosen, left_out, opened = [], {}, []
    kept = KEPT + ((FONTS,) if args.scale == 2 else ())
    for path in packs:
        pack = up.Pack(path)
        pack.path = path
        opened.append(pack)
    menu, screens = ({}, {}) if args.no_menus else menus.plans(opened)
    picked = set()
    for pack in opened:
        for entry in pack.entries:
            if not (entry.name.lower().endswith(".gti") or entry.path in menu):
                continue
            try:
                up.safe_parts(entry.path)
            except ValueError as problem:
                sys.exit("%s: %s. Nothing was written." % (pack.path, problem))
            if entry.path in menu:
                if args.only.lower() in entry.path.lower():
                    picked.add(menu[entry.path]["screen"] or entry.path)
            elif not entry.path.lower().startswith(kept):
                folder = "\\".join(entry.folder.split("\\")[:2])
                left_out[folder] = left_out.get(folder, 0) + 1
            elif args.only.lower() in entry.path.lower() and not args.menus_only:
                chosen.append((pack, entry))
    textures = len(chosen)
    chosen += [(pack, entry) for pack in opened for entry in pack.entries
               if entry.path in menu and (menu[entry.path]["screen"] or entry.path) in picked]
    stack = generative_stack(tools, args.generative_log or os.path.join(args.out, "generative.log"))
    listed = {}
    if stack and ways == WAYS and not args.no_generative:
        paths = {entry.path for _, entry in chosen}
        with open(GENERATIVE_LIST) as f:
            listed = {entry["path"]: entry for entry in json.load(f) if entry["path"] in paths}
    print("%d textures to resize %dx. Ways: %s." % (textures, args.scale, ", then ".join(ways)))
    if len(chosen) > textures:
        print("  %d menu, loading screen and HUD pictures to resize 2x or 4x, as %s lists them." % (
            len(chosen) - textures, os.path.relpath(menus.SPEC, root)))
    if listed:
        print("  %d listed in %s try the %s way first, at %dx." % (len(listed), os.path.relpath(GENERATIVE_LIST, root), GENERATIVE, GENERATIVE_SCALE))
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
    if stored:
        settings, key = stored["settings"], stored["key"]

    cache = os.path.join(args.out, "cache")
    if os.path.exists(cache) and not os.path.exists(os.path.join(args.out, MARKER)):
        sys.exit("%s exists and was not made by this tool. Move it away first." % cache)
    try:
        with open(os.path.join(args.out, MANIFEST)) as f:
            old = json.load(f)
    except (OSError, ValueError):
        old = {}
    if old.get("key") != key:
        old = {}
        targets = {os.path.join(cache, *up.safe_parts(entry.path)).lower() for _, entry in chosen}
        targets |= {target + ending for target in targets for ending in menus.MARKERS}
        if args.only and set(files_under(cache)) - targets:
            sys.exit("The set in %s was made with other settings, and --only would leave part of it as it is.\n"
                     "Run once without --only. Nothing was replaced." % args.out)
    os.makedirs(args.out, exist_ok=True)
    work = os.path.join(args.out, "%s-%s" % (WORK, key[:16]))
    for name in os.listdir(args.out):
        if name.startswith(WORK) and os.path.join(args.out, name) != work:
            shutil.rmtree(os.path.join(args.out, name), ignore_errors=True)
    os.makedirs(work, exist_ok=True)
    setup = {"scale": args.scale, "ways": ways, "tools": tools, "work": work, "out": args.out,
             "font_way": args.font_way, "glyphs": glyph_boxes(opened), "generative": listed, "generative_stack": stack,
             "menu": menu, "screens": screens,
             "allow_other_tools": args.allow_other_tools}
    sources = [(pack, entry, pack.read(entry)) for pack, entry in chosen]
    records, run = build(args, setup, sources, old)
    settle(args, setup, settings, key, sources, records, run, old)
    shutil.rmtree(work, ignore_errors=True)
    if args.sheets:
        sheets(args, setup["scale"], sources, cache)


def relabel(args):
    """Redraws the lettering of a complete set with the settings in its manifest, and makes nothing else.

    The set keeps its key, so a later run with the settings that made it
    still finds it complete. Returns None, or why nothing was done.
    """
    if not set_complete(args.out):
        return "%s holds no complete set. Make one first: python3 tools/upscale-textures.py" % args.out
    with open(os.path.join(args.out, MANIFEST)) as f:
        old = json.load(f)
    records = {record["path"]: generated(record) for record in old["textures"]}
    found = {}
    for path in sorted(os.path.join(args.game, name) for name in os.listdir(args.game) if name.lower().endswith(".up")):
        pack = up.Pack(path)
        for entry in pack.entries:
            if entry.path in records and entry.path not in found:
                found[entry.path] = (pack, entry, pack.read(entry))
    if set(found) != set(records):
        return "The game's packs do not hold every texture of the set. Make the set again: python3 tools/upscale-textures.py"
    if any(hashlib.sha256(data).hexdigest() != records[path]["source_sha256"] for path, (_, _, data) in found.items()):
        return "The game's textures differ from the ones the set was made from. Make the set again: python3 tools/upscale-textures.py"
    work = os.path.join(args.out, WORK + "-" + lettering.WAY)
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    setup = {"scale": old["settings"]["scale"], "work": work, "out": args.out}
    args.rest_stays = False
    sources = [found[record["path"]] for record in old["textures"]]
    settle(args, setup, old["settings"], old["key"], sources, records, {"made": 0, "repeat": None, "seconds": 0}, old)
    shutil.rmtree(work, ignore_errors=True)
    return None


def set_complete(out):
    """True when a run finished in out: the manifest comes last, so every texture it lists as made is there."""
    try:
        with open(os.path.join(out, MARKER)) as f:
            if f.read().strip() not in ("512", "1024"):
                return False
        with open(os.path.join(out, MANIFEST)) as f:
            made = [record["path"] for record in json.load(f)["textures"] if record["way"] != "none"]
    except (OSError, ValueError, KeyError, TypeError):
        return False
    return bool(made) and all(os.path.isfile(os.path.join(out, "cache", *path.split("\\"))) for path in made)


def files_under(folder):
    """Lower-case paths, because the pack spells one folder in more than one way and the disk keeps the first."""
    return {os.path.join(at, name).lower(): os.path.join(at, name) for at, _, names in os.walk(folder) for name in names}


def generated(record):
    """The record of the texture this tool made, also while an override takes its place."""
    if record["way"] not in REPLACING:
        return record
    plain = {name: value for name, value in record.items() if name not in OWN + ("generated", lettering.WAY)}
    plain.update(record["generated"])
    if plain["way"] == "none":
        del plain["out"]
    return plain


def where(setup, record):
    """The file of a generated texture: just made, set aside for an override, or in the set."""
    for folder in (os.path.join(setup["work"], "cache"), os.path.join(setup["out"], ASIDE), os.path.join(setup["out"], "cache")):
        path = os.path.join(folder, *up.safe_parts(record["path"]))
        if os.path.isfile(path) and sha256_of(path) == record["file_sha256"]:
            return path
    return None


def build(args, setup, sources, old):
    """Makes the textures that are not there yet, in work/cache. Returns every record, and what this run made."""
    work = setup["work"]
    fresh = os.path.join(work, "cache")
    log = os.path.join(work, "done.jsonl")
    started = time.time()

    done = {record["path"]: generated(record) for record in old.get("textures", [])}
    stopped = set()
    if os.path.exists(log):
        with open(log) as f:
            for line in f:
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                done[record["path"]] = record
                stopped.add(record["path"])
    todo, records = [], {}
    for number, (pack, entry, data) in enumerate(sources):
        record = done.get(entry.path)
        asked = font_way(setup) if entry.path.lower().startswith(FONTS) else None
        if entry.path in setup["generative"]:
            asked = generative_asked(setup, entry.path)
        if entry.path in setup["menu"]:
            asked = menus.asked(setup["menu"][entry.path])
        if record and record["source_sha256"] == hashlib.sha256(data).hexdigest() and record.get("asked") == asked and (
                record["way"] == "none" or where(setup, record)):
            records[entry.path] = record
        else:
            todo.append((number, pack, entry, data))
    todo = whole_screens(setup, sources, todo, records)
    if stopped & set(records):
        print("%d textures were already done in an earlier run that stopped." % len(stopped & set(records)))
    run = {"made": len(todo), "repeat": None, "seconds": 0}
    if not todo:
        return records, run

    setup["helpers"] = build_helpers(work)
    if any(len(item) == 4 and item[2].path in setup["generative"] for item in todo):
        check_generative_models(setup)
    with multiprocessing.Pool(max(1, args.jobs)) as pool:
        for at in range(0, len(todo), BATCH):
            made = run_batch(setup, todo[at:at + BATCH], fresh, pool)
            with open(log, "a") as f:
                for record in made:
                    records[record["path"]] = record
                    f.write(json.dumps(record, sort_keys=True) + "\n")
            print("  %d of %d, %.0f seconds" % (min(at + BATCH, len(todo)), len(todo), time.time() - started), flush=True)

        again = [item for item in todo if len(item) == 4 and records[item[2].path]["way"] != "none"]
        again = again[::max(1, len(again) // max(1, args.repeat))][:args.repeat] if args.repeat > 0 else []
        screens = [item for item in todo if len(item) == 3 and records[item[2][0][1].path]["way"] != "none"]
        if args.repeat > 0 and screens:
            again.append(min(screens, key=lambda item: len(item[2])))
        if again:
            second = [record for record in run_batch(setup, again, os.path.join(work, "repeat"), pool) if record["way"] != "none"]
            same = sum(1 for record in second if record.get("file_sha256") == records[record["path"]]["file_sha256"])
            run["repeat"] = {"textures": len(second), "identical": same}
            print("Made %d textures a second time: %d came out byte for byte the same." % (len(second), same))
            if same != len(second):
                print("WARNING: the upscaler does not give the same result twice on this Mac.")
    run["seconds"] = time.time() - started
    return records, run


def whole_screens(setup, sources, todo, records):
    """A screen is enlarged as one picture, so when one of its pieces is to be made, all of them are."""
    def screen_of(path):
        return setup["menu"].get(path, {}).get("screen")
    names = {screen_of(item[2].path) for item in todo} - {None}
    todo = [item for item in todo if screen_of(item[2].path) is None]
    grouped = {}
    for number, (pack, entry, data) in enumerate(sources):
        if screen_of(entry.path) in names:
            records.pop(entry.path, None)
            grouped.setdefault(screen_of(entry.path), (number, screen_of(entry.path), []))[2].append((pack, entry, data))
    return todo + list(grouped.values())


def marker_of(record):
    """The ending of the empty file that tells the launcher's helper how many times the pixels a flat picture has."""
    if record["way"] == "none":
        return None
    if record.get("kind") == "font":
        return TWICE
    return ".%dx" % record["marked"] if record.get("marked") else None


def fitting_overrides(args, sources, records):
    """{path: (file, checksum, bytes)} for each .gti or .tga under --overrides that may take the place of a picture of this run."""
    by_name = {entry.path.lower(): (entry.path, data) for _, entry, data in sources}
    found = {}
    for _, file in sorted(files_under(args.overrides).items()):
        name = os.path.relpath(file, args.overrides).replace(os.sep, "\\")
        if not name.lower().endswith((".gti", ".tga")):
            continue
        if name.lower() not in by_name:
            if not args.rest_stays:
                print("  override refused: %s is not a texture of the set" % name)
            continue
        path, data = by_name[name.lower()]
        own_w, own_h, _, has_alpha, mipmaps = picture_of(path, data)
        times = records[path].get("marked", args.scale)
        width, height = records[path].get("out") or (own_w * times, own_h * times)
        with open(file, "rb") as f:
            content = f.read()
        try:
            if name.lower().endswith(".tga"):
                wanted = ["%dx%d, %s alpha" % (width, height, "with" if has_alpha else "no")]
                tga_w, tga_h, _, tga_alpha = menus.read_tga(content)
                has = ["%dx%d, %s alpha" % (tga_w, tga_h, "with" if tga_alpha else "no")]
            else:
                shape = "format %d, %dx%d, %d levels"
                wanted = [shape % (8 if has_alpha else 7, width, height, gti.level_count(width, height) if mipmaps else 1)]
                has = [shape % (image.fmt, image.width, image.height, len(image.levels)) for image in gti.parse(content).images]
        except (ValueError, struct.error) as problem:
            print("  override refused: %s: %s" % (name, problem))
            continue
        if max(width, height) > 1024:
            print("  override refused: %s would pass 1024 pixels" % name)
        elif has != wanted:
            print("  override refused: %s has %s. The set has %s there." % (name, " and ".join(has) or "no picture", wanted[0]))
        else:
            found[path] = (file, hashlib.sha256(content).hexdigest(), len(content))
    return found


def letter(args, setup, sources, records, skip):
    """{path: (file, checksum, bytes, note)} for the textures of tools/lettering.json that got their words set again."""
    by_path = {entry.path: data for _, entry, data in sources}
    items = []
    for path, (entry, why) in sorted(lettering.wanted(by_path, skip).items()):
        source = where(setup, records[path]) if records[path]["way"] != "none" else None
        if why:
            print("  lettering left as made: %s (%s)" % (path, why))
        elif source:
            items.append((path, entry, by_path[path], source, records[path]["tiles"]))
    return lettering.draw(items, lettering_fonts(args.tools), setup["work"], lambda data, scale, tiles: plain_picture(setup, data, scale, tiles))


def plain_picture(setup, data, scale, tiles):
    """RGBA of a texture enlarged by the plain filter alone, for a lettering box taken from it."""
    width, height, pixels = gti.to_rgba(gti.parse(data).best())
    if "helpers" not in setup:
        setup["helpers"] = build_helpers(setup["work"])
    stem = os.path.join(setup["work"], lettering.WAY, "plain")
    os.makedirs(os.path.dirname(stem), exist_ok=True)
    with open(stem + ".in", "wb") as f:
        f.write(with_border(pixels, width, height, tiles[0], tiles[1]))
    full_w, full_h = width + 2 * BORDER, height + 2 * BORDER
    alphas = set(pixels[3::4])
    if 0 in alphas and len(alphas) > 1:
        run_jobs(setup["helpers"]["texture-refine"], ["bleed", stem + ".in", stem + ".in", full_w, full_h], True)
    run_jobs(setup["helpers"]["vimage-scale"], [stem + ".in", stem + ".out", full_w, full_h, full_w * scale, full_h * scale])
    with open(stem + ".out", "rb") as f:
        return without_border(f.read(), width * scale, height * scale, BORDER * scale)


def put(source, target):
    os.makedirs(os.path.dirname(target), exist_ok=True)
    shutil.copyfile(source, target + ".part")
    os.replace(target + ".part", target)


def settle(args, setup, settings, key, sources, records, run, old):
    """Moves what was made into the set, puts overrides in place and writes the manifest.

    Every file arrives by a rename and the manifest comes last, so a stop at any
    point leaves a set the game can load, and the next run finishes the rest.
    """
    out, scale = setup["out"], setup["scale"]
    cache, aside = os.path.join(out, "cache"), os.path.join(out, ASIDE)
    ordered = [records[entry.path] for _, entry, _ in sources]
    if all(record["way"] == "none" for record in ordered):
        summary(ordered)
        sys.exit("No texture passed its checks. Nothing was replaced.")
    overrides = fitting_overrides(args, sources, records) if os.path.isdir(args.overrides) else {}
    lettered = {} if args.no_lettering else letter(args, setup, sources, records, overrides)
    replacing = dict(overrides, **{path: done[:3] for path, done in lettered.items()})

    final = []
    for record in ordered:
        if record["path"] in replacing:
            _, digest, size = replacing[record["path"]]
            taken = {name: value for name, value in record.items() if name not in OWN}
            taken.update(way="override" if record["path"] in overrides else lettering.WAY, bytes=size, file_sha256=digest,
                         out=record.get("out") or [side * record.get("marked", scale) for side in record["size"]],
                         generated={name: record[name] for name in OWN if name in record})
            if record["path"] in lettered:
                taken[lettering.WAY] = lettered[record["path"]][3]
            record = taken
        final.append(record)
    with open(os.path.join(out, MARKER), "w") as f:
        f.write("1024\n")

    changed = 0
    for record in final:
        parts = up.safe_parts(record["path"])
        target, kept = os.path.join(cache, *parts), os.path.join(aside, *parts)
        made = generated(record)
        source = where(setup, made) if made["way"] != "none" else None
        if record["way"] in REPLACING:
            if source and source != kept:
                put(source, kept)
            if not (os.path.isfile(target) and sha256_of(target) == record["file_sha256"]):
                put(replacing[record["path"]][0], target)
                changed += 1
        else:
            if source and source != target:
                os.makedirs(os.path.dirname(target), exist_ok=True)
                os.replace(source, target)
                changed += 1
            elif not source and os.path.exists(target):
                os.remove(target)
                changed += 1
            if os.path.exists(kept):
                os.remove(kept)
        for ending in menus.MARKERS:
            if ending == marker_of(record) and not os.path.exists(target + ending):
                open(target + ending, "w").close()
            elif ending != marker_of(record) and os.path.exists(target + ending):
                os.remove(target + ending)

    if args.rest_stays:
        now = {record["path"]: record for record in final}
        final = [now.pop(record["path"], record) for record in old.get("textures", [])] + list(now.values())
    else:
        wanted = {os.path.join(cache, *up.safe_parts(record["path"])).lower() for record in final if record["way"] != "none"}
        wanted |= {os.path.join(cache, *up.safe_parts(record["path"])).lower() + marker_of(record) for record in final
                   if marker_of(record)}
        wanted |= {os.path.join(aside, *up.safe_parts(record["path"])).lower() for record in final
                   if record["way"] in REPLACING and record["generated"]["way"] != "none"}
        for folder in (cache, aside):
            for name, file in files_under(folder).items():
                if name not in wanted:
                    os.remove(file)
                    changed += 1
            for at, _, _ in os.walk(folder, topdown=False):
                if not os.listdir(at):
                    os.rmdir(at)

    counts = summary(final)
    largest = max(max(record["out"]) for record in final if record["way"] != "none")
    manifest = {"key": key, "settings": settings, "tools_are_the_pinned_ones": settings.get("tools", PINNED) == PINNED,
                "counts": counts, "repeat": run["repeat"] or old.get("repeat"),
                "seconds": round(old.get("seconds", 0) + run["seconds"]), "textures": final}
    if manifest != old:
        with open(os.path.join(out, MANIFEST + ".part"), "w") as f:
            json.dump(manifest, f, indent=1, sort_keys=True)
        os.replace(os.path.join(out, MANIFEST + ".part"), os.path.join(out, MANIFEST))
    with open(os.path.join(out, MARKER), "w") as f:
        f.write("%d\n" % (512 if largest <= 512 else 1024))
    if not run["made"] and not changed and manifest == old:
        print("The set in %s is already complete with these settings. Nothing to do." % out)
        return
    written = sum(record.get("bytes", 0) for record in final)
    print("%d textures, %.0f MB, in %s. Made %d now, in %.0f seconds." % (
        len(final) - counts["none"], written / 1e6, cache, run["made"], run["seconds"]))
    print("Largest side: %d pixels. Play with: ./dogfighter" % largest)


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
        records = [record for record in json.load(f)["textures"] if record["way"] in WAYS and "marked" not in record]
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
