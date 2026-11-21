#!/usr/bin/env python3
"""Runs SeedVR2's inference_cli.py with PyTorch's Metal cache emptied before each phase and after each batch.

Usage: seedvr2-run.py <path to inference_cli.py> [its arguments]

PyTorch keeps freed Metal memory in heaps and gives a heap back only when nothing
in it is live. The CLI never empties that cache between phases, so the VAE encode
left up to the high watermark in cached heaps, and the DiT weights loaded next
were placed inside those heaps (reserved memory rose 0.02 GB for 3.45 GB of
weights). Each heap then held a weight that stays to the end, so none could be
given back, and the DiT's large activations found no room under the cap. It ran
out of memory at whatever cap was set. The unpacked CLI is pinned by checksum, so
it is patched here in memory instead of on disk."""
import functools
import gc
import os
import runpy
import sys

cli = os.path.abspath(sys.argv[1])
sys.argv = [cli] + sys.argv[2:]
sys.path.insert(0, os.path.dirname(cli))

import torch  # noqa: E402
from src.core import generation_phases, infer  # noqa: E402


def empty():
    gc.collect()
    torch.mps.empty_cache()


def emptied_before(phase):
    @functools.wraps(phase)
    def run(*args, **kwargs):
        held = torch.mps.driver_allocated_memory()
        empty()
        print("seedvr2-run: Metal memory before %s: %.2f GB, after emptying the cache %.2f GB" % (
            phase.__name__, held / 1e9, torch.mps.driver_allocated_memory() / 1e9), flush=True)
        return phase(*args, **kwargs)
    return run


def emptied_after(batch):
    @functools.wraps(batch)
    def run(*args, **kwargs):
        result = batch(*args, **kwargs)
        torch.mps.empty_cache()
        return result
    return run


for name in ("encode_all_batches", "upscale_all_batches", "decode_all_batches", "postprocess_all_batches"):
    setattr(generation_phases, name, emptied_before(getattr(generation_phases, name)))
for name in ("vae_encode", "inference", "vae_decode"):
    setattr(infer.VideoDiffusionInfer, name, emptied_after(getattr(infer.VideoDiffusionInfer, name)))

runpy.run_path(cli, run_name="__main__")
