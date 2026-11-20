"""Redraws listed surface textures at 4x with Stable Diffusion 1.5 and the ControlNet 1.1 tile model.

tools/upscale-textures.py runs this with the Python in upscale-tools/generative/venv,
one process at a time: generative-upscale.py JOBS.json. JOBS.json holds the model
folder, the log file, the settings and one job per texture: the original and its
faithful 2x version as PNG, where the 4x PNG goes, prompt, strength, seed and
whether the texture tiles across and down. It prints one JSON line per job.

How a texture is made, as tested in logs/shots/generative (DECISION.md):
  - The faithful 2x version is enlarged to 4x, or 8x or 16x for small
    textures so the model works near 512 pixels, and given to the model as
    start picture and as the tile ControlNet's guide.
  - Every convolution pads by wrapping around where the texture tiles, so the
    result tiles too.
  - Afterwards the coarse shapes, at half the original's resolution, are
    replaced by the original's, twice.
Checks, shrunk to the original size and compared as PSNR:
  drift   the model's own result. Under the limit it drew something else.
  match   after the coarse shapes were put back.
  seam    for a tiling direction: the mean difference between the opposite
          edges may not pass 4, twice the difference between neighbouring
          columns, or 1.5 times the seam of a plain enlargement.
Memory: under stop_free percent free no new texture is started; under
abort_free the process ends at once.
"""
import fcntl
import json
import logging
import os
import subprocess
import sys
import threading
import time

os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1", DO_NOT_TRACK="1",
                  DIFFUSERS_VERBOSITY="error", TRANSFORMERS_VERBOSITY="error", PYTORCH_ENABLE_MPS_FALLBACK="1")

logging.getLogger("torch.distributed.elastic.multiprocessing.redirects").setLevel(logging.ERROR)

import numpy as np  # noqa: E402
import torch  # noqa: E402
import torch.nn.functional as F  # noqa: E402
from PIL import Image  # noqa: E402

WRAP = {"x": False, "y": False}
ABORTED = 3


def free_memory():
    said = subprocess.run(["/usr/bin/memory_pressure"], capture_output=True, text=True).stdout
    return next((int(line.split(":")[1].strip().rstrip("%")) for line in said.splitlines() if "free percentage" in line), -1)


class Log:
    def __init__(self, path):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)

    def __call__(self, tag, text=""):
        free = free_memory()
        line = "%s load1=%.2f free=%d%% %s %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), os.getloadavg()[0], free, tag, text)
        with open(self.path, "a") as f:
            f.write(line.rstrip() + "\n")
        return free


def watchdog(log, abort_free):
    while True:
        time.sleep(15)
        free = free_memory()
        if 0 <= free < abort_free:
            log("ABORT", "free memory under %d%%" % abort_free)
            os._exit(ABORTED)


def conv_forward(module, inp, weight, bias):
    if not (WRAP["x"] or WRAP["y"]) or isinstance(module.padding, str) or module.padding == (0, 0):
        return module._plain_forward(inp, weight, bias)
    left, right, top, bottom = module._reversed_padding_repeated_twice
    out = F.pad(inp, (left, right, 0, 0), mode="circular" if WRAP["x"] else "constant")
    out = F.pad(out, (0, 0, top, bottom), mode="circular" if WRAP["y"] else "constant")
    return F.conv2d(out, weight, bias, module.stride, (0, 0), module.dilation, module.groups)


def make_wrappable(model):
    for module in model.modules():
        if isinstance(module, torch.nn.Conv2d):
            module._plain_forward = module._conv_forward
            module._conv_forward = lambda inp, weight, bias, module=module: conv_forward(module, inp, weight, bias)


def load_pipe(models, device, dtype):
    from diffusers import ControlNetModel, DPMSolverMultistepScheduler, StableDiffusionControlNetImg2ImgPipeline
    from diffusers.utils import logging as diffusers_logging
    diffusers_logging.disable_progress_bar()
    controlnet = ControlNetModel.from_pretrained(os.path.join(models, "cn-tile"), use_safetensors=True,
                                                 local_files_only=True, torch_dtype=dtype)
    pipe = StableDiffusionControlNetImg2ImgPipeline.from_single_file(
        os.path.join(models, "sd15", "v1-5-pruned-emaonly.safetensors"), config=os.path.join(models, "sd15"),
        controlnet=controlnet, safety_checker=None, feature_extractor=None, local_files_only=True, torch_dtype=dtype)
    pipe.scheduler = DPMSolverMultistepScheduler.from_config(pipe.scheduler.config, use_karras_sigmas=True)
    pipe.set_progress_bar_config(disable=True)
    for model in (pipe.unet, pipe.vae, pipe.controlnet):
        make_wrappable(model)
    return pipe.to(device)


def padded(a, pad, wrap_x, wrap_y):
    a = np.pad(a, ((0, 0), (pad, pad), (0, 0)), mode="wrap" if wrap_x else "edge")
    return np.pad(a, ((pad, pad), (0, 0), (0, 0)), mode="wrap" if wrap_y else "edge")


def enlarge(a, factor, wrap_x, wrap_y, pad=4):
    big = padded(a, pad, wrap_x, wrap_y)
    h, w = big.shape[:2]
    planes = [np.asarray(Image.fromarray(big[:, :, c].astype(np.float32), "F").resize((w * factor, h * factor), Image.BICUBIC))
              for c in range(3)]
    return np.stack(planes, axis=2)[pad * factor:(h - pad) * factor, pad * factor:(w - pad) * factor]


def shrink(a, factor):
    h, w = a.shape[:2]
    return a.reshape(h // factor, factor, w // factor, factor, 3).mean(axis=(1, 3))


def psnr(a, b):
    mse = float(np.mean((a - b) ** 2))
    return 99.0 if mse < 1e-9 else float(10 * np.log10(255.0 ** 2 / mse))


def seam(a):
    return float(np.mean(np.abs(a[:, 0] - a[:, -1]))), float(np.mean(np.abs(a[:, 1:] - a[:, :-1])))


def to_image(a):
    return Image.fromarray(np.clip(a + 0.5, 0, 255).astype(np.uint8))


def work_factor(w, h):
    more = 1
    while min(w, h) * 4 * more < 384 and max(w, h) * 4 * more * 2 <= 1024:
        more *= 2
    return more


def one(pipe, job, settings, device):
    wrap_x, wrap_y = job["tiles"]
    orig = np.asarray(Image.open(job["original"]).convert("RGB")).astype(np.float64)
    faithful = np.asarray(Image.open(job["faithful"]).convert("RGB")).astype(np.float64)
    h, w = orig.shape[:2]
    more = work_factor(w, h)
    start = enlarge(faithful, 4 // job["faithful_scale"] * more, wrap_x, wrap_y)
    WRAP["x"], WRAP["y"] = wrap_x, wrap_y
    if device == "cpu" and start.shape[0] * start.shape[1] > 600 * 600:
        pipe.enable_attention_slicing("max")
    else:
        pipe.disable_attention_slicing()
    began = time.time()
    with torch.inference_mode():
        made = pipe(prompt=job["prompt"], negative_prompt=settings["negative"], image=to_image(start),
                    control_image=to_image(start), strength=job["strength"], num_inference_steps=settings["steps"],
                    guidance_scale=settings["guidance"], controlnet_conditioning_scale=settings["control"],
                    generator=torch.Generator("cpu").manual_seed(job["seed"])).images[0]
    seconds = time.time() - began
    raw = np.asarray(made).astype(np.float64)
    if more > 1:
        raw = shrink(raw, more)
    scores = {"drift": round(psnr(shrink(raw, 4), orig), 2)}
    cutoff = settings["cutoff"]
    low = shrink(orig, cutoff)
    result = raw
    for _ in range(2):
        result = result + enlarge(low - shrink(result, 4 * cutoff), 4 * cutoff, wrap_x, wrap_y)
    result = np.clip(result, 0, 255)
    scores["match"] = round(psnr(shrink(result, 4), orig), 2)
    plain = enlarge(orig, 4, wrap_x, wrap_y)
    limits = settings["limits"]
    why = None
    if not np.isfinite(raw).all() or raw.max() - raw.min() < 1:
        why = "the model gave an empty picture"
    for name in ("drift", "match"):
        if why is None and scores[name] < limits[name]:
            why = "%s %.1f dB is under %.1f" % (name, scores[name], limits[name])
    for wraps, axis, picture, before in ((wrap_x, "x", result, plain),
                                         (wrap_y, "y", result.transpose(1, 0, 2), plain.transpose(1, 0, 2))):
        edge, inside = seam(picture)
        plain_edge = seam(before)[0]
        scores.update({"seam_" + axis: round(edge, 2), "inside_" + axis: round(inside, 2), "plain_seam_" + axis: round(plain_edge, 2)})
        if wraps and why is None and edge > max(4.0, 2.0 * inside, 1.5 * plain_edge):
            why = "seam %s %.1f against %.1f inside" % (axis, edge, inside)
    scores.update(seconds=round(seconds, 1), work=[start.shape[1], start.shape[0]], device=device)
    if why is None:
        to_image(result).save(job["out"])
    return scores, why


def main():
    with open(sys.argv[1]) as f:
        task = json.load(f)
    settings = task["settings"]
    log = Log(task["log"])
    lock = open(os.path.join(task["models"], "run.lock"), "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        busy = "another generative run is busy"
    else:
        busy = None
        free = log("start", "%d textures" % len(task["jobs"]))
        if 0 <= free < settings["stop_free"]:
            busy = "under %d%% memory free, not started" % settings["stop_free"]
    if busy:
        for job in task["jobs"]:
            print(json.dumps({"id": job["id"], "why": busy, "retry": True}), flush=True)
        return
    threading.Thread(target=watchdog, args=(log, settings["abort_free"]), daemon=True).start()
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    dtype = torch.float16 if device == "mps" else torch.float32
    began = time.time()
    pipe = load_pipe(task["models"], device, dtype)
    log("loaded", "device=%s torch=%s %.1fs" % (device, torch.__version__, time.time() - began))
    stopped = False
    for job in task["jobs"]:
        free = log("before", job["name"])
        if stopped or 0 <= free < settings["stop_free"]:
            if not stopped:
                log("STOP", "free memory under %d%%, no new texture is started" % settings["stop_free"])
            stopped = True
            print(json.dumps({"id": job["id"], "why": "under %d%% memory free, not started" % settings["stop_free"], "retry": True}), flush=True)
            continue
        try:
            scores, why = one(pipe, job, settings, device)
        except Exception as problem:  # noqa: BLE001
            scores, why = None, "%s: %s" % (type(problem).__name__, problem)
        log("done", "%s %ss work=%s %s" % (job["name"], scores and scores["seconds"],
                                           scores and "x".join(map(str, scores["work"])), why or "ok"))
        print(json.dumps({"id": job["id"], "scores": scores, "why": why}), flush=True)
    log("end")


if __name__ == "__main__":
    main()
