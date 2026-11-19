import sys, struct, os, json

SECTOR = 2352
path, first_audio = sys.argv[1], int(sys.argv[2])
min_gap = int(sys.argv[3]) if len(sys.argv) > 3 else 100
total = os.path.getsize(path) // SECTOR
zero = bytes(SECTOR)

def quiet(s):
    if s == zero:
        return True
    v = struct.unpack('<%dh' % (SECTOR // 2), s)
    return max(abs(x) for x in v) <= 16

runs = []
with open(path, 'rb') as f:
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

gaps = [(a, b) for a, b in runs if b - a >= min_gap]
print(json.dumps({'total_sectors': total, 'first_audio': first_audio,
                  'gaps': gaps, 'short_quiet_runs_over_20': [(a, b) for a, b in runs if 20 <= b - a < min_gap]}))
