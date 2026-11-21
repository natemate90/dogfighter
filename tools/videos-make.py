#!/usr/bin/env python3
"""Makes the videos of one job file that tools/videos.py wrote, in upscale-tools/video/venv.

Each video goes through these steps in its work folder, and each step that
finished is kept, so a run that stopped goes on where it stopped:
  src/      the frames of the game's video as PNG, and audio.wav
  cuts      where one shot ends and the next starts
  up/       every frame 4x: level 1 by the texture tool's Real-ESRGAN and its
            pull-back in tools/texture-refine.c, a batch of frames at a time,
            levels 2 and 3 by SeedVR2, one shot at a time
  seg/      per shot: RIFE makes three frames between each two, the frames of
            the shot itself are put back unchanged, and x265 encodes them
  the .mov  the shots joined with the original audio

At a cut RIFE would blend two shots, so the last frame of a shot is held
until the next shot starts. That also keeps every original frame at its own
time, so picture and sound stay in sync.

Memory: under stop_free percent free no new shot or batch is started; under
abort_free the running tool is stopped at once and the run ends.
"""
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time

import imageio_ffmpeg
import numpy as np
import psutil
import torch
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import up as packs  # noqa: E402

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
RATE = 15
SAMPLES = 22050
BATCH = 32


class Watch:
    """Logs memory and load, remembers the worst, and stops the running tool when memory runs out."""

    def __init__(self, log, limits):
        self.log_file, self.limits = log, limits
        self.child, self.aborted = None, False
        self.least_free, self.most_used, self.most_child = 100, 0, 0
        threading.Thread(target=self.loop, daemon=True).start()

    def free(self):
        said = subprocess.run(["/usr/bin/memory_pressure"], capture_output=True, text=True).stdout
        return next((int(line.split(":")[1].strip().rstrip("%")) for line in said.splitlines() if "free percentage" in line), -1)

    def sample(self):
        free = self.free()
        used = psutil.virtual_memory().total - psutil.virtual_memory().available
        child = 0
        if self.child and self.child.poll() is None:
            try:
                top = psutil.Process(self.child.pid)
                child = sum(p.memory_info().rss for p in [top] + top.children(recursive=True))
            except psutil.Error:
                pass
        if free >= 0:
            self.least_free = min(self.least_free, free)
        self.most_used, self.most_child = max(self.most_used, used), max(self.most_child, child)
        return free, used, child

    def log(self, tag, text=""):
        free, used, child = self.sample()
        line = "%s load1=%.1f free=%d%% used=%.1fGB tool=%.1fGB %s %s" % (
            time.strftime("%Y-%m-%d %H:%M:%S"), os.getloadavg()[0], free, used / 1e9, child / 1e9, tag, text)
        with open(self.log_file, "a") as f:
            f.write(line + "\n")
        print(line, flush=True)
        return free

    def loop(self):
        while True:
            time.sleep(5)
            free, _, _ = self.sample()
            if 0 <= free < self.limits["abort_free"] and not self.aborted:
                self.aborted = True
                self.log("ABORT", "free memory under %d%%, the running tool is stopped" % self.limits["abort_free"])
                if self.child and self.child.poll() is None:
                    os.killpg(self.child.pid, signal.SIGKILL)
                else:
                    os._exit(3)

    def run(self, command, quiet=False, feed=None):
        if self.aborted:
            sys.exit(3)
        self.child = subprocess.Popen(command, start_new_session=True, stdout=subprocess.PIPE if quiet else None,
                                      stderr=subprocess.STDOUT if quiet else None, stdin=subprocess.PIPE if feed else None)
        said = self.child.communicate(feed)[0]
        if self.aborted:
            sys.exit("Stopped: free memory went under %d%%. Run again to go on." % self.limits["abort_free"])
        if self.child.returncode:
            tail = said.decode(errors="replace").strip().splitlines()[-8:] if said else []
            sys.exit("%s ended with exit code %d\n%s" % (os.path.basename(command[0]), self.child.returncode, "\n".join(tail)))
        return said.decode(errors="replace") if said else ""

    def room(self, what):
        for _ in range(10):
            free = self.log("before", what)
            if free < 0 or free >= self.limits["stop_free"]:
                return
            time.sleep(60)
        sys.exit("Stopped before %s: under %d%% memory free for ten minutes. Run again to go on." % (what, self.limits["stop_free"]))


def stage(folder, key):
    """True when folder holds a finished step made with key; otherwise empties it and stamps the key."""
    stamp = folder + ".key"
    if os.path.isfile(stamp) and open(stamp).read() == key:
        return True
    shutil.rmtree(folder, ignore_errors=True)
    os.makedirs(folder)
    with open(stamp, "w") as f:
        f.write(key)
    return False


def done(folder):
    with open(folder + ".done", "w") as f:
        f.write(open(folder + ".key").read())


def finished(folder):
    return os.path.isfile(folder + ".done") and open(folder + ".done").read() == open(folder + ".key").read()


def pictures(folder):
    return sorted(name for name in os.listdir(folder) if name.endswith(".png"))


def decode(watch, video, work):
    src, first, count = os.path.join(work, "src"), video["first"], video["count"]
    if stage(src, video["keys"]["src"]) and finished(src):
        return len(pictures(src))
    picks = ["-vf", "trim=start_frame=%d:end_frame=%d,setpts=PTS-STARTPTS" % (first, first + count)] if video["clip"] else []
    watch.run([FFMPEG, "-nostdin", "-loglevel", "error", "-i", video["source"], "-map", "0:v:0", "-fps_mode", "passthrough"]
              + picks + ["-pix_fmt", "rgb24", os.path.join(src, "%05d.png")])
    cut = ["-af", "atrim=start_sample=%d:end_sample=%d,asetpts=PTS-STARTPTS" % (
        first * SAMPLES // RATE, (first + count) * SAMPLES // RATE)] if video["clip"] else []
    watch.run([FFMPEG, "-nostdin", "-loglevel", "error", "-y", "-i", video["source"], "-map", "0:a:0"] + cut
              + ["-c:a", "pcm_s16le", "-ar", str(SAMPLES), os.path.join(src, "audio.wav")])
    made = len(pictures(src))
    if video["clip"] and made != count:
        sys.exit("%s: %d frames decoded, %d asked" % (video["name"], made, count))
    done(src)
    return made


def find_cuts(src, rule):
    """Indexes k where frame k ends a shot: a large jump on small thumbnails, far above its neighbours, or to or from black."""
    thumbs = [np.asarray(Image.open(os.path.join(src, name)).convert("RGB").reduce(rule["reduce"]), dtype=np.float32)
              for name in pictures(src)]
    jumps = [float(np.abs(b - a).mean()) for a, b in zip(thumbs, thumbs[1:])]
    dark = [float(t.mean()) < rule["black"] for t in thumbs]
    cuts = []
    for k, jump in enumerate(jumps):
        around = max(jumps[k - 1] if k else 0.0, jumps[k + 1] if k + 1 < len(jumps) else 0.0)
        if jump > rule["least"] and (jump >= rule["ratio"] * around or dark[k] or dark[k + 1]):
            cuts.append(k)
    return cuts


def shots_of(count, cuts):
    starts = [0] + [k + 1 for k in cuts]
    return list(zip(starts, starts[1:] + [count]))


def tensor(path):
    return torch.from_numpy(np.asarray(Image.open(path).convert("RGB"), dtype=np.float32)).permute(2, 0, 1)[None]


def shrink(picture, scale):
    return torch.nn.functional.avg_pool2d(picture, scale)


def psnr(a, b):
    mse = float(((a - b) ** 2).mean())
    return 99.0 if mse == 0 else 10 * np.log10(255.0 ** 2 / mse)


def upscale_esrgan(watch, job, video, level, src, up):
    """Real-ESRGAN by the texture tool's upscayl-bin, then its pull-back in tools/texture-refine.c, a batch of frames at a time."""
    ai, scale = video["esrgan"], job["scale"]
    for name in os.listdir(up):
        if ".part" in name:
            os.remove(os.path.join(up, name))
    missing = [name for name in pictures(src) if not os.path.isfile(os.path.join(up, name))]
    if not missing:
        return
    width, height = Image.open(os.path.join(src, missing[0])).size
    raw = up + "-raw"
    watch.log("esrgan", "%d frames" % len(missing))
    started = time.time()
    for at in range(0, len(missing), BATCH):
        batch = missing[at:at + BATCH]
        watch.room("frames %d to %d of %d" % (at + 1, at + len(batch), len(missing)))
        for folder in (ai["feed"], ai["made"], raw):
            shutil.rmtree(folder, ignore_errors=True)
            os.makedirs(folder)
        blank = os.path.join(raw, "blank")
        with open(blank, "wb") as f:
            f.truncate(width * scale * height * scale * 4)
        fields = []
        for name in batch:
            os.link(os.path.join(src, name), os.path.join(ai["feed"], name))
            with open(os.path.join(raw, name + ".in"), "wb") as f:
                f.write(Image.open(os.path.join(src, name)).convert("RGBA").tobytes())
            fields += [level["refine"], os.path.join(raw, name + ".in"), blank, os.path.join(ai["made"], name),
                       os.path.join(raw, name + ".out"), width, height, scale, 0, level["passes"]]
        watch.run(ai["command"], quiet=True)
        lines = watch.run([job["refine"]], quiet=True, feed=b"".join(str(field).encode() + b"\0" for field in fields)).splitlines()
        for name, line in zip(batch, lines + [""] * len(batch)):
            if not line.startswith("ok "):
                sys.exit("tools/texture-refine.c did not take frame %s: %s" % (name, line or "no answer"))
            with open(os.path.join(raw, name + ".out"), "rb") as f:
                picture = Image.frombytes("RGBA", (width * scale, height * scale), f.read()).convert("RGB")
            save(picture, os.path.join(up, name))
        watch.log("esrgan", "%d of %d, %.1f s a frame" % (at + len(batch), len(missing), (time.time() - started) / (at + len(batch))))
    for folder in (ai["feed"], ai["made"], raw):
        shutil.rmtree(folder, ignore_errors=True)


def save(picture, path):
    """Writes through a name pictures() does not list, so a frame stopped mid-save is not taken for a frame."""
    picture.save(path + ".part", format="PNG")
    os.replace(path + ".part", path)


def upscale_seedvr2(watch, job, video, level, src, up, shots):
    names = pictures(src)
    width, height = Image.open(os.path.join(src, names[0])).size
    feed, out = up + "-shots", up + "-out"
    for number, (start, end) in enumerate(shots):
        if all(os.path.isfile(os.path.join(up, name)) for name in names[start:end]):
            continue
        watch.room("shot %d of %d (frames %d to %d)" % (number + 1, len(shots), start, end - 1))
        for folder in (feed, out):
            shutil.rmtree(folder, ignore_errors=True)
            os.makedirs(folder)
        clip = os.path.join(feed, "shot.mkv")
        watch.run([FFMPEG, "-nostdin", "-loglevel", "error", "-framerate", str(RATE), "-start_number", str(start + 1),
                   "-i", os.path.join(src, "%05d.png"), "-frames:v", str(end - start), "-c:v", "ffv1", "-pix_fmt", "bgr0", clip])
        command = [sys.executable, "-I", os.path.join(job["seedvr2"], "inference_cli.py"), clip, "--output", out,
                   "--output_format", "png", "--model_dir", job["models"], "--dit_model", level["dit"],
                   "--resolution", str(height * job["scale"]), "--max_resolution", str(width * job["scale"]),
                   "--batch_size", str(level["batch"]), "--chunk_size", str(level["chunk"]),
                   "--temporal_overlap", str(level["overlap"]), "--color_correction", level["color"],
                   "--seed", str(level["seed"]), "--input_noise_scale", str(level["input_noise"]),
                   "--latent_noise_scale", str(level["latent_noise"]),
                   "--vae_encode_tiled", "--vae_decode_tiled", "--vae_encode_tile_size", str(level["tile"]),
                   "--vae_decode_tile_size", str(level["tile"]), "--vae_encode_tile_overlap", str(level["tile_overlap"]),
                   "--vae_decode_tile_overlap", str(level["tile_overlap"])]
        started = time.time()
        watch.run(command, quiet=True)
        made = sorted(os.path.join(root, name) for root, _, files in os.walk(out) for name in files if name.endswith(".png"))
        if len(made) != end - start:
            sys.exit("SeedVR2 made %d frames for shot %d, which has %d" % (len(made), number + 1, end - start))
        for path, name in zip(made, names[start:end]):
            if Image.open(path).size != (width * job["scale"], height * job["scale"]):
                sys.exit("SeedVR2 made %s at %dx%d" % (name, *Image.open(path).size))
            os.replace(path, os.path.join(up, name))
        watch.log("shot", "%d frames in %.0f s, %.1f s a frame" % (end - start, time.time() - started,
                                                                  (time.time() - started) / (end - start)))
    for folder in (feed, out):
        shutil.rmtree(folder, ignore_errors=True)


def match_scores(src, up, scale):
    """PSNR of each made frame, shrunk by block average, against the game's frame: how far the picture moved away."""
    scores = []
    for name in pictures(src):
        scores.append(psnr(shrink(tensor(os.path.join(up, name)), scale), tensor(os.path.join(src, name))))
    return scores


def interpolate_and_encode(watch, job, video, up, seg, shots):
    spec, names = job["spec"], pictures(up)
    times = spec["fps"] // RATE
    encode = spec["encode"]
    for number, (start, end) in enumerate(shots):
        target = os.path.join(seg, "%04d.mov" % number)
        if os.path.isfile(target):
            continue
        watch.room("frames between, shot %d of %d" % (number + 1, len(shots)))
        feed, out = seg + "-feed", seg + "-out"
        for folder in (feed, out):
            shutil.rmtree(folder, ignore_errors=True)
            os.makedirs(folder)
        for name in names[start:end]:
            os.link(os.path.join(up, name), os.path.join(feed, name))
        wanted = (end - start) * times
        if end - start > 1:
            watch.run([job["rife"], "-i", feed, "-o", out, "-n", str(wanted), "-m", job["rife_model"], "-f", "%08d.png"]
                      + (["-u"] if spec["interpolate"]["uhd"] else []) + ([] if torch.backends.mps.is_available() else ["-g", "-1"]),
                      quiet=True)
        for at, name in enumerate(names[start:end]):
            for step in range(times if at == end - start - 1 else 1):
                frame = os.path.join(out, "%08d.png" % (at * times + step + 1))
                if os.path.exists(frame):
                    os.remove(frame)
                os.link(os.path.join(up, name), frame)
        if len(pictures(out)) != wanted:
            sys.exit("RIFE made %d frames for shot %d, %d wanted" % (len(pictures(out)), number + 1, wanted))
        watch.run([FFMPEG, "-nostdin", "-loglevel", "error", "-y", "-framerate", str(spec["fps"]), "-i", os.path.join(out, "%08d.png"),
                   "-vf", "scale=out_color_matrix=bt709:out_range=tv", "-c:v", encode["codec"], "-preset", encode["preset"],
                   "-crf", str(encode["crf"]), "-pix_fmt", encode["pix_fmt"], "-color_primaries", "bt709", "-color_trc", "bt709",
                   "-colorspace", "bt709", "-color_range", "tv", "-x265-params", "log-level=error", "-f", "mov", target + ".part"])
        os.replace(target + ".part", target)
        for folder in (feed, out):
            shutil.rmtree(folder)


def join(watch, job, video, src, seg, count):
    spec = job["spec"]
    listing = os.path.join(seg, "parts.txt")
    with open(listing, "w") as f:
        for name in sorted(os.listdir(seg)):
            if name.endswith(".mov"):
                f.write("file '%s'\n" % os.path.join(seg, name))
    target = video["target"]
    os.makedirs(os.path.dirname(target), exist_ok=True)
    part = target + ".part." + spec["encode"]["container"]
    watch.run([FFMPEG, "-nostdin", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0",
               "-i", listing, "-i", os.path.join(src, "audio.wav"), "-map", "0:v", "-map", "1:a",
               "-c:v", "copy", "-tag:v", spec["encode"]["tag"], "-c:a", spec["encode"]["audio"], "-movflags", "+faststart", part])
    probe = subprocess.run([FFMPEG, "-nostdin", "-i", part, "-map", "0:v", "-c", "copy", "-f", "null", "-"],
                           capture_output=True, text=True).stderr
    frames = int(probe.rsplit("frame=", 1)[1].split()[0])
    if frames != count * spec["fps"] // RATE:
        sys.exit("%s has %d frames, %d wanted" % (part, frames, count * spec["fps"] // RATE))
    os.replace(part, target)
    return frames


def main():
    with open(sys.argv[1]) as f:
        job = json.load(f)
    watch = Watch(job["log"], job["spec"]["memory"])
    left = []
    for video in job["videos"]:
        started = time.time()
        work, level = video["work"], video["level"]
        if not torch.backends.mps.is_available():
            print("%s is left out: %s needs the Mac's graphics card (Metal), and this process cannot reach it." % (
                video["name"], "SeedVR2" if level["way"] == "seedvr2" else "upscayl-bin"))
            left.append(video["name"])
            continue
        os.makedirs(work, exist_ok=True)
        watch.log("start", "%s, level %s" % (video["name"], video["level_name"]))
        count = decode(watch, video, work)
        src = os.path.join(work, "src")
        cuts = find_cuts(src, job["spec"]["cuts"])
        shots = shots_of(count, cuts)
        watch.log("cuts", "%d shots, cuts after frames %s" % (len(shots), cuts))
        up = os.path.join(work, "up")
        if not (stage(up, video["keys"]["up"]) and finished(up)):
            if level["way"] == "esrgan":
                upscale_esrgan(watch, job, video, level, src, up)
            else:
                upscale_seedvr2(watch, job, video, level, src, up, shots)
            done(up)
        scores = match_scores(src, up, job["scale"])
        seg = os.path.join(work, "seg")
        stage(seg, video["keys"]["seg"] + json.dumps(cuts))
        interpolate_and_encode(watch, job, video, up, seg, shots)
        frames = join(watch, job, video, src, seg, count)
        result = {
            "name": video["name"], "file": os.path.basename(video["target"]), "sha256": packs.sha256_of(video["target"]),
            "bytes": os.path.getsize(video["target"]), "frames": frames, "source_frames": count, "cuts": cuts,
            "match_db": {"least": round(min(scores), 1), "mean": round(float(np.mean(scores)), 1)},
            "seconds": round(time.time() - started), "ffmpeg_sha256": packs.sha256_of(FFMPEG),
            "least_free_percent": watch.least_free, "most_used_gb": round(watch.most_used / 1e9, 1),
            "most_tool_gb": round(watch.most_child / 1e9, 1),
        }
        with open(os.path.join(work, "result.json"), "w") as f:
            json.dump(result, f, indent=1, sort_keys=True)
        print("RESULT " + json.dumps(result), flush=True)
        watch.log("done", "%s: %d frames in %.0f s" % (video["name"], frames, time.time() - started))
    if left:
        sys.exit("Not made: " + ", ".join(left))


if __name__ == "__main__":
    main()
