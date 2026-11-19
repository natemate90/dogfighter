import sys, struct, os
src, out = sys.argv[1], sys.argv[2]
SYNC = b'\x00' + b'\xff'*10 + b'\x00'
n = os.path.getsize(src)//2352
first_nosync = None; modes = {}; runs = []; prev = None
with open(src,'rb') as f, open(out,'wb') as o:
    for i in range(n):
        s = f.read(2352)
        if s[:12] == SYNC:
            k = 'mode%d' % s[15]
        else:
            k = 'nosync_zero' if s.count(0) == 2352 else 'nosync_data'
        modes[k] = modes.get(k,0)+1
        if k != prev:
            runs.append((i,k)); prev = k
        if k == 'mode1': o.write(s[16:16+2048])
        elif k == 'mode2': o.write(s[24:24+2048])
        elif first_nosync is None: first_nosync = i
        if k.startswith('nosync') and len(runs) > 400: pass
print('sectors', n, modes)
print('runs', len(runs)); print(runs[:40]); print(runs[-10:])
