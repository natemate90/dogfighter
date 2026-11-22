#!/usr/bin/env python3
"""Makes the videos of one job file that tools/videos.py wrote, in upscale-tools/video/venv.

Each video goes through these steps in its work folder, and each step that
finished is kept, so a run that stopped goes on where it stopped:
  src/      the frames of the game's video as PNG, and audio.wav
  cuts      where one shot ends and the next starts
  up/       every frame 4x: level 1 by the texture tool's Real-ESRGAN and its
            pull-back in tools/texture-refine.c, a batch of frames at a time,
            levels 2 and 3 by SeedVR2, one chunk of a shot at a time, so its
            memory does not grow with the shot (see upscale_seedvr2)
  seg/      per shot: RIFE makes three frames between each two, the frames of
            the shot itself are put back unchanged, and x265 encodes them.
            A frame in one of the video's no_interpolate ranges is held until
            the next one instead, as the game shows it
  the .mov  the shots joined with the original audio

At a cut RIFE would blend two shots, so the last frame of a shot is held
until the next shot starts. That also keeps every original frame at its own
time, so picture and sound stay in sync.

Memory: the run follows macOS's memory pressure, so compressed memory and idle
apps swapped to the SSD do not stop it. At stop_level or worse no new shot,
chunk or batch is started; it checks again every 30 s for up to wait_s, then
the run ends. At abort_level for abort_after_s in a row, or with more than
abort_swap_gb more swap used than at the start, the running tool is stopped and the run
ends. When the pressure cannot be read, the old rule holds: nothing starts
under stop_free percent free, and the run ends under abort_free. While a tool
runs, a "during" line is logged each minute with the memory of the tool and
its children (tool=).
"""
import ctypes
import json
import os
import shutil
import signal
import struct
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
LIBC = ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)
LIBC.sysctlbyname.argtypes = [ctypes.c_char_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_size_t), ctypes.c_void_p, ctypes.c_size_t]
PRESSURE = {"normal": 1, "warning": 2, "critical": 4}
PRESSURE_NAME = {level: name for name, level in PRESSURE.items()}


def sysctl(name, size):
    value, length = ctypes.create_string_buffer(size), ctypes.c_size_t(size)
    if LIBC.sysctlbyname(name.encode(), value, ctypes.byref(length), None, 0):
        raise OSError(ctypes.get_errno(), "sysctl " + name)
    return value.raw[:length.value]


def pressure():
    """The green, yellow and red of Activity Monitor: 1, 2 or 4. The sysctl is not in the SDK; xnu returns the
    DISPATCH_MEMORYPRESSURE_NORMAL, _WARN and _CRITICAL of <dispatch/source.h>, and counts its urgent level as 2."""
    return struct.unpack("<i", sysctl("kern.memorystatus_vm_pressure_level", 4))[0]


def swap_used():
    try:
        return psutil.swap_memory().used
    except psutil.Error as error:
        raise OSError("psutil.swap_memory: %r" % error) from error


def footprint(pid):
    """What Activity Monitor shows as a process's memory. Unlike RSS it counts what the process holds on the graphics
    card (Metal), which on Apple Silicon is the same memory and is most of what SeedVR2 uses. Byte 72 is
    ri_phys_footprint of struct rusage_info_v0 in <sys/resource.h>, after a 16-byte uuid and seven 64-bit fields."""
    info = ctypes.create_string_buffer(256)
    if LIBC.proc_pid_rusage(pid, 0, info):
        raise OSError(ctypes.get_errno(), "proc_pid_rusage of %d" % pid)
    return struct.unpack_from("<Q", info.raw, 72)[0]


class Watch:
    """Logs memory and load, remembers the worst, and stops the running tool when memory runs out."""
    TICK, PAUSE = 5, 30

    def __init__(self, log, limits, pressure=pressure, swap=swap_used):
        self.log_file, self.limits, self.read_pressure, self.read_swap = log, limits, pressure, swap
        self.stop_level, self.abort_level = PRESSURE[limits["stop_level"]], PRESSURE[limits["abort_level"]]
        self.child, self.label, self.aborted, self.why, self.unread = None, "", False, "", None
        self.least_free, self.most_used, self.most_child, self.run_peak = 100, 0, 0, 0
        self.worst_level, self.most_swap, self.red_since, self.notes, self.noted = 0, 0, None, [], set()
        self.swap_base = None
        self.logged = time.time()
        threading.Thread(target=self.loop, daemon=True).start()

    def read(self, what, reader, then):
        try:
            return reader()
        except OSError as error:
            if what not in self.noted:
                self.noted.add(what)
                self.notes.append("%s not read (%s), so %s" % (what, error, then))
            return None

    def free(self):
        said = subprocess.run(["/usr/bin/memory_pressure"], capture_output=True, text=True).stdout
        return next((int(line.split(":")[1].strip().rstrip("%")) for line in said.splitlines() if "free percentage" in line), -1)

    def tool_memory(self, pid):
        try:
            pids = [pid] + [p.pid for p in psutil.Process(pid).children(recursive=True)]
        except psutil.Error as error:
            self.unread = repr(error)
            return 0
        total = 0
        for each in pids:
            try:
                total += footprint(each)
            except OSError as error:
                try:
                    total += psutil.Process(each).memory_info().rss
                except psutil.Error:
                    self.unread = repr(error)
        return total

    def sample(self):
        free = self.free()
        used = psutil.virtual_memory().total - psutil.virtual_memory().available
        child = self.tool_memory(self.child.pid) if self.child and self.child.poll() is None else 0
        level = self.read("memory pressure", self.read_pressure, "the old rule holds: nothing starts under %d%% free, and the run "
                          "ends under %d%%" % (self.limits["stop_free"], self.limits["abort_free"]))
        swap = self.read("swap", self.read_swap, "it has no limit")
        if free >= 0:
            self.least_free = min(self.least_free, free)
        self.most_used, self.most_child = max(self.most_used, used), max(self.most_child, child)
        self.worst_level, self.most_swap = max(self.worst_level, level or 0), max(self.most_swap, swap or 0)
        self.run_peak = max(self.run_peak, child)
        return free, used, child, level, swap

    def log(self, tag, text=""):
        sampled = free, used, child, level, swap = self.sample()
        if self.unread:
            text, self.unread = "%s (tool memory not read: %s)" % (text, self.unread), None
        while self.notes:
            text = "%s (%s)" % (text, self.notes.pop(0))
        line = "%s load1=%.1f free=%d%% used=%.1fGB pressure=%s swap=%s tool=%.1fGB %s %s" % (
            time.strftime("%Y-%m-%d %H:%M:%S"), os.getloadavg()[0], free, used / 1e9,
            "?" if level is None else PRESSURE_NAME.get(level, level), "?" if swap is None else "%.1fGB" % (swap / 1e9),
            child / 1e9, tag, text)
        with open(self.log_file, "a") as f:
            f.write(line + "\n")
        print(line, flush=True)
        self.logged = time.time()
        return sampled

    def danger(self, free, level, swap):
        """Why the run must end now, or "". Pressure must stay at abort_level for abort_after_s, not one sample."""
        if swap is not None:
            self.swap_base = swap if self.swap_base is None else min(self.swap_base, swap)
            if swap - self.swap_base > self.limits["abort_swap_gb"] * 1e9:
                return "swap used grew by more than %s GB during the run" % self.limits["abort_swap_gb"]
        if level is None:
            return "free memory went under %d%%" % self.limits["abort_free"] if 0 <= free < self.limits["abort_free"] else ""
        if level < self.abort_level:
            self.red_since = None
            return ""
        if self.red_since is None:
            self.red_since = time.time()
            self.log("pressure", "%s, the tool is stopped if it stays so for %d s" % (
                PRESSURE_NAME.get(level, level), self.limits["abort_after_s"]))
        if time.time() - self.red_since >= self.limits["abort_after_s"]:
            return "memory pressure was %s or worse for %d s" % (self.limits["abort_level"], self.limits["abort_after_s"])
        return ""

    def loop(self):
        while True:
            time.sleep(self.TICK)
            free, _, _, level, swap = self.sample()
            running = self.child and self.child.poll() is None
            if not running:
                self.red_since = None
            why = "" if self.aborted or not running else self.danger(free, level, swap)
            if why:
                self.aborted, self.why = True, why
                self.log("ABORT", why + ", the running tool is stopped")
                os.killpg(self.child.pid, signal.SIGKILL)
            elif running and time.time() - self.logged >= 60:
                self.log("during", "%s, tool peak %.1fGB" % (self.label, self.run_peak / 1e9))

    def run(self, command, quiet=False, feed=None, log=None, env=None):
        """Runs command and ends the run when it fails. With log, its output goes to the end of that file instead."""
        if self.aborted:
            sys.exit(3)
        self.label = os.path.basename(next((part for part in command if part.endswith(".py")), command[0]))
        self.run_peak = 0
        output = open(log, "ab") if log else subprocess.PIPE if quiet else None
        self.child = subprocess.Popen(command, start_new_session=True, stdout=output, env=env,
                                      stderr=subprocess.STDOUT if quiet or log else None,
                                      stdin=subprocess.PIPE if feed else None)
        said = self.child.communicate(feed)[0]
        if log:
            output.close()
            if self.child.returncode:
                with open(log, "rb") as f:
                    f.seek(max(0, os.path.getsize(log) - 4000))
                    said = f.read()
        if self.aborted:
            sys.exit("Stopped: %s. Run again to go on." % self.why)
        if self.child.returncode:
            tail = said.decode(errors="replace").strip().splitlines()[-8:] if said else []
            sys.exit("%s ended with exit code %d\n%s" % (os.path.basename(command[0]), self.child.returncode, "\n".join(tail)))
        return "" if log else said.decode(errors="replace") if said else ""

    def room(self, what):
        started = time.time()
        while True:
            free, _, _, level, _ = self.log("before", what)
            if level is None and (free < 0 or free >= self.limits["stop_free"]) or level is not None and level < self.stop_level:
                return
            if time.time() - started >= self.limits["wait_s"]:
                break
            time.sleep(self.PAUSE)
        busy = "memory pressure %s or worse" % self.limits["stop_level"] if level is not None else (
            "under %d%% memory free" % self.limits["stop_free"])
        sys.exit("Stopped before %s: %s for %d s. Run again to go on." % (what, busy, self.limits["wait_s"]))


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


def spans(start, end, most):
    """Frames start to end split into nearly equal chunks of at most `most` frames."""
    parts = -(-(end - start) // most)
    edges = [start + (end - start) * k // parts for k in range(parts + 1)]
    return list(zip(edges, edges[1:]))


def upscale_seedvr2(watch, job, video, level, src, up, shots):
    """SeedVR2 on one chunk of a shot at a time, in a process of its own.

    SeedVR2's memory grows with the frames of one call (its output is held at
    full size until the call ends), so a call gets at most level["chunk"]
    frames, plus level["overlap"] frames of the same shot on either side. Those
    before the chunk only steer the model and are dropped. Those after it are
    kept in up/tail and faded into the first frames of the next chunk, so no
    step shows where one chunk ends. A chunk counts as made when all its frames
    are in up/ and the tail the next chunk needs is there too.

    SeedVR2's inference_cli.py sets both PYTORCH_MPS_*_WATERMARK_RATIO to 0.0
    unless they are set already. That turns off PyTorch's release of cached Metal
    memory, so freed memory is never given back and reached 29 GB in the VAE
    encode alone. level["mps_low_gb"] and level["mps_high_gb"] set them again:
    above the low one PyTorch releases cached memory, the high one is a hard cap.
    The cap alone did not hold: the CLI runs through tools/seedvr2-run.py, which
    empties that cache before each phase and after each batch (see there)."""
    names = pictures(src)
    width, height = Image.open(os.path.join(src, names[0])).size
    feed, out, tail = up + "-shots", up + "-out", os.path.join(up, "tail")
    os.makedirs(tail, exist_ok=True)
    overlap, log = level["overlap"], os.path.join(os.path.dirname(up), "seedvr2.log")
    most = torch.mps.recommended_max_memory()
    env = dict(os.environ, PYTORCH_MPS_LOW_WATERMARK_RATIO="%.3f" % min(2.0, level["mps_low_gb"] * 1e9 / most),
               PYTORCH_MPS_HIGH_WATERMARK_RATIO="%.3f" % min(2.0, level["mps_high_gb"] * 1e9 / most))
    wrapper = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seedvr2-run.py")

    def there(folder, part):
        return all(os.path.isfile(os.path.join(folder, name)) for name in part)

    for number, (start, end) in enumerate(shots):
        chunks = spans(start, end, level["chunk"])
        made_already = [there(up, names[first:last]) for first, last in chunks]
        for k in reversed(range(len(chunks) - 1)):
            last = chunks[k][1]
            made_already[k] = made_already[k] and (made_already[k + 1] or there(tail, names[last:min(end, last + overlap)]))
        for part, (first, last) in enumerate(chunks):
            if made_already[part]:
                continue
            low, high = max(start, first - overlap), min(end, last + overlap)
            fade = names[first:min(last, first + overlap)] if part else []
            watch.room("shot %d of %d, chunk %d of %d (frames %d to %d)" % (
                number + 1, len(shots), part + 1, len(chunks), first, last - 1))
            for folder in (feed, out):
                shutil.rmtree(folder, ignore_errors=True)
                os.makedirs(folder)
            clip = os.path.join(feed, "chunk.mkv")
            watch.run([FFMPEG, "-nostdin", "-loglevel", "error", "-framerate", str(RATE), "-start_number", str(low + 1),
                       "-i", os.path.join(src, "%05d.png"), "-frames:v", str(high - low), "-c:v", "ffv1", "-pix_fmt", "bgr0",
                       clip])
            command = [sys.executable, "-I", wrapper, os.path.join(job["seedvr2"], "inference_cli.py"), clip, "--output", out,
                       "--output_format", "png", "--model_dir", job["models"], "--dit_model", level["dit"],
                       "--resolution", str(height * job["scale"]), "--max_resolution", str(width * job["scale"]),
                       "--batch_size", str(level["batch"]), "--temporal_overlap", str(overlap),
                       "--color_correction", level["color"], "--seed", str(level["seed"]),
                       "--input_noise_scale", str(level["input_noise"]), "--latent_noise_scale", str(level["latent_noise"]),
                       "--vae_encode_tiled", "--vae_decode_tiled", "--vae_encode_tile_size", str(level["tile"]),
                       "--vae_decode_tile_size", str(level["tile"]), "--vae_encode_tile_overlap", str(level["tile_overlap"]),
                       "--vae_decode_tile_overlap", str(level["tile_overlap"]), "--debug"]
            with open(log, "a") as f:
                f.write("\n=== %s shot %d chunk %d: frames %d to %d, with %d to %d, Metal memory low %s high %s of %.1fGB\n" % (
                    time.strftime("%Y-%m-%d %H:%M:%S"), number + 1, part + 1, first, last - 1, low, high - 1,
                    env["PYTORCH_MPS_LOW_WATERMARK_RATIO"], env["PYTORCH_MPS_HIGH_WATERMARK_RATIO"], most / 1e9))
            started = time.time()
            watch.run(command, log=log, env=env)
            made = sorted(os.path.join(root, name) for root, _, files in os.walk(out) for name in files if name.endswith(".png"))
            if len(made) != high - low:
                sys.exit("SeedVR2 made %d frames for frames %d to %d, which are %d" % (len(made), low, high - 1, high - low))
            for path in made:
                if Image.open(path).size != (width * job["scale"], height * job["scale"]):
                    sys.exit("SeedVR2 made %s at %dx%d" % (path, *Image.open(path).size))
            for path, name in zip(made[last - low:], names[last:high]):
                os.replace(path, os.path.join(tail, name))
            for at, (path, name) in enumerate(zip(made[first - low:last - low], names[first:last])):
                if at < len(fade):
                    weight = (overlap - at) / (overlap + 1)
                    before = np.asarray(Image.open(os.path.join(tail, name)).convert("RGB"), dtype=np.float32)
                    now = np.asarray(Image.open(path).convert("RGB"), dtype=np.float32)
                    save(Image.fromarray(np.rint(before * weight + now * (1 - weight)).astype(np.uint8)), os.path.join(up, name))
                else:
                    os.replace(path, os.path.join(up, name))
            spent = time.time() - started
            watch.log("chunk", "%d of %d of shot %d: %d frames (%d made) in %.0f s, %.1f s a frame, tool peak %.1fGB" % (
                part + 1, len(chunks), number + 1, last - first, high - low, spent, spent / (last - first), watch.run_peak / 1e9))
    for folder in (feed, out, tail):
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
    still = {k - video["first"] for first, last in video["no_interpolate"] for k in range(first, last + 1)}
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
        held = [at == end - start - 1 or start + at in still for at in range(end - start)]
        if not all(held):
            watch.run([job["rife"], "-i", feed, "-o", out, "-n", str(wanted), "-m", job["rife_model"], "-f", "%08d.png"]
                      + (["-u"] if spec["interpolate"]["uhd"] else []) + ([] if torch.backends.mps.is_available() else ["-g", "-1"]),
                      quiet=True)
        for at, name in enumerate(names[start:end]):
            for step in range(times if held[at] else 1):
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
            "most_tool_gb": round(watch.most_child / 1e9, 1), "worst_pressure": PRESSURE_NAME.get(watch.worst_level),
            "most_swap_gb": round(watch.most_swap / 1e9, 1),
        }
        with open(os.path.join(work, "result.json"), "w") as f:
            json.dump(result, f, indent=1, sort_keys=True)
        print("RESULT " + json.dumps(result), flush=True)
        watch.log("done", "%s: %d frames in %.0f s" % (video["name"], frames, time.time() - started))
    if left:
        sys.exit("Not made: " + ", ".join(left))


if __name__ == "__main__":
    main()
