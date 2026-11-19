"""Encode sector ranges of a raw CD image as Track02.ogg, Track03.ogg, ...

usage: rip_tracks.py <image.bin> <encoder> <out dir> <start-end>...

The encoder reads a WAV file on stdin and writes Ogg Vorbis to stdout.
Tracks that already exist are skipped.
"""
import sys, struct, subprocess, os

if len(sys.argv) < 5:
    sys.exit(__doc__)
SECTOR = 2352
bin_path, encoder, out_dir = sys.argv[1], sys.argv[2], sys.argv[3]
tracks = [tuple(map(int, t.split('-'))) for t in sys.argv[4:]]
os.makedirs(out_dir, exist_ok=True)

with open(bin_path, 'rb') as f:
    for n, (start, end) in enumerate(tracks, start=2):
        dst = os.path.join(out_dir, 'Track%02d.ogg' % n)
        if os.path.exists(dst):
            continue
        size = (end - start) * SECTOR
        hdr = struct.pack('<4sI4s4sIHHIIHH4sI', b'RIFF', 36 + size, b'WAVE', b'fmt ', 16, 1, 2,
                          44100, 44100 * 4, 4, 16, b'data', size)
        part = dst + '.part'
        with open(part, 'wb') as o:
            p = subprocess.Popen([encoder], stdin=subprocess.PIPE, stdout=o, stderr=subprocess.DEVNULL)
            p.stdin.write(hdr)
            f.seek(start * SECTOR)
            left = size
            while left:
                chunk = f.read(min(left, SECTOR * 1000))
                p.stdin.write(chunk)
                left -= len(chunk)
            p.stdin.close()
            if p.wait() != 0:
                sys.exit('encoder failed on track %d' % n)
        os.replace(part, dst)
        print('Track%02d sectors %d-%d  %.3f s' % (n, start, end, (end - start) / 75.0))
