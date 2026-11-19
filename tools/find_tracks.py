"""Find the audio tracks of a raw CD image (2352-byte sectors) that has no cue sheet.

usage: find_tracks.py <image.bin> [min_gap]

Prints one "start-end" sector range per audio track. Tracks are split at runs of
silence of at least min_gap sectors (default 100, 1.3 s).
"""
import sys, struct, os

if len(sys.argv) not in (2, 3):
    sys.exit(__doc__)
SECTOR = 2352
path = sys.argv[1]
min_gap = int(sys.argv[2]) if len(sys.argv) > 2 else 100
total = os.path.getsize(path) // SECTOR
SYNC = b'\x00' + b'\xff'*10 + b'\x00'
zero = bytes(SECTOR)

def quiet(s):
    if s == zero:
        return True
    v = struct.unpack('<%dh' % (SECTOR // 2), s)
    return max(abs(x) for x in v) <= 16

with open(path, 'rb') as f:
    data_end = 0
    while f.read(SECTOR)[:12] == SYNC:
        data_end += 1
    # A rip can leave a few junk sectors after the data track; the audio starts
    # at the first silent sector after it.
    first_audio = data_end
    f.seek(data_end * SECTOR)
    for i in range(data_end, min(data_end + 150, total)):
        if f.read(SECTOR) == zero:
            first_audio = i
            break

    runs = []
    f.seek(first_audio * SECTOR)
    start = None
    for i in range(first_audio, total):
        q = quiet(f.read(SECTOR))
        if q and start is None:
            start = i
        elif not q and start is not None:
            runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, total))

bounds = [first_audio]
for a, b in runs:
    if b - a < min_gap:
        continue
    if a == bounds[-1]:
        bounds[-1] = b
    else:
        bounds += [a, b]
if bounds[-1] != total:
    bounds.append(total)
for a, b in zip(bounds[::2], bounds[1::2]):
    print('%d-%d' % (a, b))
