"""Makes the game's intro videos 4x as large and 60 frames a second, for tools/upscale-textures.py --videos.

The game plays two videos at start, Video/companies.avi (the company logos)
and Video/airfix.avi (the Airfix intro): 640x480, 15 frames a second, Indeo 5
video with 22 kHz PCM sound. tools/videos.json says what is made of each:
  levels       1 keeps the picture as it is and only adds sharpness:
               Real-ESRGAN on each frame, by the texture tool's upscayl-bin,
               then its pull-back in tools/texture-refine.c, so each frame
               shrunk again and rounded is the game's frame. 2 and 3 redraw
               whole shots with SeedVR2, a video model that sees 21 frames at
               once, so new detail stays put from frame to frame. 2 uses the
               3B model, 3 the 7B "sharp" one. refine is the job of
               tools/texture-refine.c: glyphs repeats the last pull-back until
               values cut off at 0 or 255 no longer keep a block from its
               original. chunk is the most frames of a shot SeedVR2 gets in
               one call, overlap the frames it shares with each neighbour
               (also between its batches), tile the size in pixels of the
               pieces its VAE encodes and decodes. These three set its memory.
  videos       name, file in the game folder, level, the SHA-256 the settings
               were checked on (another file is made too, with a note), and
               clip: start and length in seconds, for a sample.
  cuts         how a cut between shots is found (see tools/videos-make.py).
  interpolate  the RIFE model that makes the frames between, 15 to 60.
  encode       x265 10-bit in a .mov, with the game's sound unchanged.
  memory       the macOS memory pressure at which no chunk starts (stop_level,
               waited out for up to wait_s), the one that stops the run when
               it lasts abort_after_s (abort_level), the most swap used
               (abort_swap_gb), and the percent free that holds instead when
               the pressure cannot be read (stop_free, abort_free).
  seedvr2, models, rife
               the pinned downloads: URL, SHA-256 and licence. --fetch-videos
               fetches them (about 9.8 GB), the texture tool's upscalers, and
               the Python packages of tools/video-requirements.txt in
               upscale-tools/video/venv. Those packages, ffmpeg among them, are
               pinned by version only, without a checksum.

The videos go to hd-videos/<name>.mov, a clip asked with --video-clip to
hd-videos/clips/. hd-videos/manifest.json lists each with its checksum, the
settings, the checksums of the models and tools, the run time and the lowest
free memory seen. A video whose settings, models and source did not change is
not made again. Work files stay in hd-videos/.work/, so a run that stopped
goes on where it stopped.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import zipfile

import up

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = os.path.join(HERE, "videos.json")
REQUIREMENTS = os.path.join(HERE, "video-requirements.txt")
RUNNER = os.path.join(HERE, "videos-make.py")
FOLDER = "video"
PYTHON = (3, 12)
MANIFEST = "manifest.json"
RATE = 15
UNPACKED = ".unpacked-from"
REFINE = os.path.join(HERE, "texture-refine.c")
AI = ("upscayl/upscayl-bin", "realesrgan-models/realesrgan-x4plus.bin", "realesrgan-models/realesrgan-x4plus.param")


def load_spec():
    with open(SPEC) as f:
        return json.load(f)


def unpack_tar(archive, folder, digest):
    """Unpacks the regular files of a GitHub source archive without its top folder. Refuses links and paths that leave the folder."""
    shutil.rmtree(folder, ignore_errors=True)
    with tarfile.open(archive) as packed:
        for member in packed.getmembers():
            parts = member.name.split("/")[1:]
            if not parts or not parts[0]:
                continue
            if member.name.startswith("/") or ".." in parts or not (member.isfile() or member.isdir()):
                sys.exit("%s holds %s, which is not unpacked. Nothing else was." % (archive, member.name))
            target = os.path.join(folder, *parts)
            if member.isdir():
                os.makedirs(target, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "wb") as f:
                f.write(packed.extractfile(member).read())
    with open(os.path.join(folder, UNPACKED), "w") as f:
        f.write(digest)


def fetch(tools, download, python_env):
    """Sets up upscale-tools/video: the Python packages, SeedVR2's code, its models and RIFE, all checked against their pins."""
    spec, folder = load_spec(), os.path.join(tools, FOLDER)
    os.makedirs(folder, exist_ok=True)
    wanted = sum(model["bytes"] for model in spec["models"].values()) + 3e9
    if shutil.disk_usage(folder).free < wanted and not os.path.isdir(os.path.join(folder, "models")):
        sys.exit("The videos' models need about %.0f GB of free disk space." % (wanted / 1e9))
    python_env(folder, REQUIREMENTS, PYTHON)
    for name, model in sorted(spec["models"].items()):
        download(model["url"], os.path.join(folder, "models", name), model["sha256"])
    code = spec["seedvr2"]
    archive = os.path.join(folder, "downloads", code["file"])
    download(code["url"], archive, code["sha256"])
    unpack_tar(archive, os.path.join(folder, "seedvr2"), code["sha256"])
    rife = spec["rife"]
    archive = os.path.join(folder, "downloads", rife["file"])
    download(rife["url"], archive, rife["sha256"])
    shutil.rmtree(os.path.join(folder, "rife"), ignore_errors=True)
    with zipfile.ZipFile(archive) as packed:
        for member, (name, digest) in rife["members"].items():
            target = os.path.join(folder, "rife", *name.split("/"))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "wb") as f:
                f.write(packed.read(member))
            if up.sha256_of(target) != digest:
                sys.exit("%s does not match its pinned checksum." % target)
            if "." not in os.path.basename(name):
                os.chmod(target, 0o755)
    print("The video tools are in %s. Their checksums match." % folder)


def needs(level):
    """The pinned files a level runs: SeedVR2's models, or the texture tool's Real-ESRGAN."""
    return (level["dit"], level["vae"]) if level["way"] == "seedvr2" else AI


def stack(tools, levels, pinned):
    """Paths of what the asked levels need, and a list of what is missing or not the pinned file."""
    spec, folder = load_spec(), os.path.join(tools, FOLDER)
    found = {"python": os.path.join(folder, "venv", "bin", "python"), "seedvr2": os.path.join(folder, "seedvr2"),
             "models": os.path.join(folder, "models"), "rife": os.path.join(folder, "rife", "rife-ncnn-vulkan"),
             "rife_model": os.path.join(folder, "rife", spec["interpolate"]["model"])}
    problems, checksums = [], {}
    if not os.access(found["python"], os.X_OK):
        problems.append("the Python environment in %s is missing" % folder)
    marker = os.path.join(found["seedvr2"], UNPACKED)
    if not (os.path.isfile(marker) and open(marker).read() == spec["seedvr2"]["sha256"]):
        problems.append("SeedVR2's code is missing or not the pinned version")
    checksums["seedvr2"] = spec["seedvr2"]["sha256"]
    files = {name: os.path.join(folder, "rife", *target.split("/")) for name, (target, _) in spec["rife"]["members"].items()}
    pins = {name: digest for name, (_, digest) in spec["rife"]["members"].items()}
    for level in levels:
        for name in needs(level):
            if level["way"] == "seedvr2":
                files[name], pins[name] = os.path.join(found["models"], name), spec["models"][name]["sha256"]
            else:
                files[name], pins[name] = os.path.join(tools, *name.split("/")), pinned[name]
    for name, path in sorted(files.items()):
        checksums[name] = up.sha256_of(path) if os.path.isfile(path) else None
        if checksums[name] != pins[name]:
            problems.append("%s is %s" % (name, "missing" if checksums[name] is None else "not the pinned file"))
    return found, problems, checksums


def source_of(game, name):
    """The file at name (with /) in the game folder, whatever the case of its letters."""
    path = game
    for part in name.split("/"):
        here = {entry.lower(): entry for entry in os.listdir(path)} if os.path.isdir(path) else {}
        if part.lower() not in here:
            return None
        path = os.path.join(path, here[part.lower()])
    return path


def key_of(*parts):
    return hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()


def make(args, tools, pinned, upscaler_command, build_helpers):
    """Makes the videos of tools/videos.json (or the one of --video-only) and writes the manifest. Returns an exit message or None."""
    spec = load_spec()
    picked = [video for video in spec["videos"] if not args.video_only or video["name"] == args.video_only]
    if not picked:
        return "tools/videos.json has no video named %s. It has: %s" % (args.video_only, ", ".join(v["name"] for v in spec["videos"]))
    jobs = []
    for video in picked:
        level_name = str(args.video_level or video["level"])
        if level_name not in spec["levels"]:
            return "There is no level %s. Levels: %s" % (level_name, ", ".join(sorted(spec["levels"])))
        clip = video.get("clip")
        if args.video_clip:
            start, _, seconds = args.video_clip.partition(",")
            clip = [float(start), float(seconds or 3)]
        jobs.append((video, level_name, clip))
    levels = [spec["levels"][name] for _, name, _ in jobs]
    found, problems, checksums = stack(tools, levels, pinned)
    if problems:
        return "The videos cannot be made: %s. Run: python3 tools/upscale-textures.py --fetch-videos" % "; ".join(problems)

    out = os.path.abspath(args.videos_out)
    manifest_path = os.path.join(out, MANIFEST)
    manifest = {"videos": {}, "clips": {}}
    if os.path.isfile(manifest_path):
        with open(manifest_path) as f:
            manifest = json.load(f)
    todo, entries = [], {}
    for video, level_name, clip in jobs:
        source = source_of(args.game, video["file"])
        if not source:
            return "%s is not in %s." % (video["file"], args.game)
        digest = up.sha256_of(source)
        if digest != video["sha256"]:
            print("Note: %s is not the file these settings were checked on (SHA-256 %s). It is made anyway." % (source, digest))
        level = spec["levels"][level_name]
        first, count = (round(clip[0] * RATE), round(clip[1] * RATE)) if clip else (0, None)
        sample = bool(args.video_clip) or level_name != str(video["level"])
        stem = "%s-level%s-%d-%d" % (video["name"], level_name, first, count) if args.video_clip else (
            "%s-level%s" % (video["name"], level_name) if sample else video["name"])
        target = os.path.join(out, "clips" if sample else "", stem + "." + spec["encode"]["container"])
        work = os.path.join(out, ".work", stem)
        used = {name: checksums[name] for name in checksums
                if name not in spec["models"] and name not in AI or name in needs(level)}
        esrgan = None
        if level["way"] == "esrgan":
            used["texture-refine.c"] = up.sha256_of(REFINE)
            feed, made = os.path.join(work, "up-feed"), os.path.join(work, "up-made")
            esrgan = {"command": upscaler_command("ai", tools, feed, made, spec["scale"]), "feed": feed, "made": made}
        upscaler = [part for part in esrgan["command"] if not os.path.isabs(part)] if esrgan else None
        keys = {"src": key_of(digest, first, count)}
        pixels = {name: value for name, value in level.items() if not name.startswith("mps_")}
        keys["up"] = key_of(keys["src"], spec["scale"], pixels, used, upscaler, spec["cuts"] if level["way"] == "seedvr2" else None)
        keys["seg"] = key_of(keys["up"], spec["cuts"], spec["fps"], spec["interpolate"], spec["encode"])
        shelf = "clips" if sample else "videos"
        entry = {"source": video["file"], "source_sha256": digest, "level": level_name, "settings": level, "upscaler": upscaler,
                 "clip_frames": [first, count] if clip else None, "scale": spec["scale"], "fps": spec["fps"], "cuts": spec["cuts"],
                 "interpolate": spec["interpolate"], "encode": spec["encode"], "checksums": used, "key": keys["seg"]}
        old = manifest.get(shelf, {}).get(stem)
        if old and old.get("key") == keys["seg"] and os.path.isfile(target) and up.sha256_of(target) == old.get("sha256"):
            print("%s is already made with these settings." % target)
            continue
        entries[stem] = (shelf, entry)
        todo.append({"name": stem, "source": source, "first": first, "count": count, "clip": bool(clip), "keys": keys,
                     "level": level, "level_name": level_name, "target": target, "work": work, "esrgan": esrgan})
    if not todo:
        return None

    helpers = os.path.join(out, ".work", "helpers")
    os.makedirs(helpers, exist_ok=True)
    if any(video["esrgan"] for video in todo):
        found["refine"] = build_helpers(helpers)["texture-refine"]
    job = dict(found, spec=spec, scale=spec["scale"], videos=todo, log=os.path.join(out, "videos.log"))
    job_file = os.path.join(out, ".work", "job.json")
    with open(job_file, "w") as f:
        json.dump(job, f, indent=1)
    runner = subprocess.Popen([found["python"], "-I", RUNNER, job_file], stdout=subprocess.PIPE, text=True)
    for line in runner.stdout:
        if line.startswith("RESULT "):
            result = json.loads(line[len("RESULT "):])
            shelf, entry = entries[result["name"]]
            entry.update(result)
            manifest.setdefault(shelf, {})[result["name"]] = entry
            with open(manifest_path + ".part", "w") as f:
                json.dump(manifest, f, indent=1, sort_keys=True)
            os.replace(manifest_path + ".part", manifest_path)
            print("Made %s: %d frames, %.0f MB, in %d seconds." % (
                os.path.join(out, "clips" if shelf == "clips" else "", result["file"]), result["frames"], result["bytes"] / 1e6,
                result["seconds"]))
        else:
            print(line, end="", flush=True)
    if runner.wait():
        return "The videos were not all made (exit %d). The log is %s. A new run goes on where this one stopped." % (
            runner.returncode, job["log"])
    return None
