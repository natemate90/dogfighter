#!/usr/bin/env python3
"""Measures the two SeedVR2 faults the repair in tools/videos-make.py takes out, in two made videos of one game video.

Run it in upscale-tools/video/venv:
  upscale-tools/video/venv/bin/python tools/video-check.py OLD.mov NEW.mov [--name airfix] [--videos-out hd-videos]

It reads the game's frames from the video's work folder (hd-videos/.work/NAME/src) and the shots from its result.json.
  sky      in every 6th frame of the video's smooth_flat ranges, and the RIFE frame halfway to the next one: the
           picture blurred (6 pixels) minus the smooth upscale, where the game's frame is flat. The darkest 0.1% of
           those pixels, in levels, and the share more than 3 levels darker.
  borders  for each chunk border, the 21 frames from the last frame before the fade to the first after it. Each frame's
           sharpness (mean absolute Laplacian) over the game's frame's sharpness, compared with the straight line
           between the two unfaded ends. The worst frame's shortfall, in percent.
"""
import argparse
import importlib.util
import json
import os
import subprocess
import sys

import cv2
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
spec_ = importlib.util.spec_from_file_location("videos_make", os.path.join(HERE, "videos-make.py"))
make = importlib.util.module_from_spec(spec_)
sys.path.insert(0, HERE)
spec_.loader.exec_module(make)


def info(path):
    said = subprocess.run([make.FFMPEG, "-nostdin", "-i", path, "-map", "0:v", "-c", "copy", "-f", "null", "-"],
                          capture_output=True, text=True).stderr
    video = next(line.strip() for line in said.splitlines() if "Video:" in line)
    audio = subprocess.run([make.FFMPEG, "-nostdin", "-loglevel", "error", "-i", path, "-map", "0:a", "-f", "md5", "-"],
                           capture_output=True, text=True).stdout.strip()
    return int(said.rsplit("frame=", 1)[1].split()[0]), video, audio


def frames(path, wanted, width, height):
    """Luma of the frames numbered in wanted, decoded with the matrix and range the pipeline encodes with."""
    proc = subprocess.Popen([make.FFMPEG, "-nostdin", "-loglevel", "error", "-i", path,
                             "-vf", "scale=in_color_matrix=bt709:in_range=tv", "-pix_fmt", "gray", "-f", "rawvideo", "-"],
                            stdout=subprocess.PIPE)
    got, number, size = {}, 0, width * height
    while True:
        raw = proc.stdout.read(size)
        if len(raw) < size:
            break
        if number in wanted:
            got[number] = np.frombuffer(raw, np.uint8).reshape(height, width).astype(np.float32)
        number += 1
    proc.wait()
    return got


def sharpness(gray):
    return float(np.abs(cv2.Laplacian(gray, cv2.CV_32F, ksize=3)).mean())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("old")
    parser.add_argument("new")
    parser.add_argument("--name", default="airfix")
    parser.add_argument("--videos-out", default=os.path.join(os.path.dirname(HERE), "hd-videos"))
    args = parser.parse_args()
    spec = json.load(open(os.path.join(HERE, "videos.json")))
    video = next(v for v in spec["videos"] if v["name"] == args.name)
    level, rule, scale, times = spec["levels"][str(video["level"])], spec["repair"], spec["scale"], spec["fps"] // make.RATE
    work = os.path.join(args.videos_out, ".work", args.name)
    names = make.pictures(os.path.join(work, "src"))
    source = lambda k: np.asarray(Image.open(os.path.join(work, "src", names[k])).convert("RGB"))
    shots = make.shots_of(len(names), json.load(open(os.path.join(work, "result.json")))["cuts"])
    borders = sorted({before + 1 for _, before, _ in make.faded_frames(shots, level).values()})
    sky = [k for first, last in video.get("smooth_flat", []) for k in range(first, last, 6)]
    width, height = source(0).shape[1] * scale, source(0).shape[0] * scale
    wanted = {times * k + step for k in sky for step in (0, times // 2)}
    wanted |= {j for f in borders for j in range(times * (f - 1), times * (f + 4) + 1)}
    src_sharp = {}

    def sharp_of(k):
        if k not in src_sharp:
            src_sharp[k] = max(0.05, sharpness(cv2.cvtColor(source(k), cv2.COLOR_RGB2GRAY).astype(np.float32)))
        return src_sharp[k]

    results = {}
    for label, path in (("old", args.old), ("new", args.new)):
        count, stream, audio = info(path)
        print("%s: %s\n  %d frames, audio %s" % (label, stream, count, audio))
        got = frames(path, wanted, width, height)
        for step, kind in ((0, "game frames"), (times // 2, "RIFE frames")):
            darkest, share = [], []
            for k in sky:
                a = step / times
                (w0, s0), (w1, s1) = make.flat_parts(source(k), rule, scale), make.flat_parts(source(k + 1), rule, scale)
                smooth = cv2.cvtColor(((1 - a) * s0 + a * s1).astype(np.float32), cv2.COLOR_RGB2GRAY)
                flat = np.minimum(w0, w1)[..., 0] > 0.9
                miss = cv2.GaussianBlur(got[times * k + step] - smooth, (0, 0), 6)[flat]
                darkest.append(np.percentile(miss, 0.1))
                share.append((miss < -3).mean() * 100)
            if sky:
                print("  sky, %s: darkest 0.1%% mean %.1f levels (worst %.1f), over 3 levels darker mean %.2f%% (worst %.2f%%)"
                      % (kind, np.mean(darkest), np.min(darkest), np.mean(share), np.max(share)))
        for f in borders:
            norm = lambda j: sharpness(got[j]) / (sharp_of(j // times) * (1 - j % times / times)
                                                   + sharp_of(min(j // times + 1, f + 4)) * (j % times / times))
            low, high = norm(times * (f - 1)), norm(times * (f + 4))
            span = times * 5
            results.setdefault(f, {})[label] = 100 * (1 - min(
                norm(j) / (low + (high - low) * (j - times * (f - 1)) / span) for j in range(times * (f - 1) + 1, times * (f + 4))))
    for f in borders:
        print("border at frame %d: %.1f%% softer before, %.1f%% after" % (f, results[f]["old"], results[f]["new"]))


if __name__ == "__main__":
    main()
