"""Write the data track of a raw CD image (2352-byte sectors) as a plain ISO file.

usage: scan.py <image.bin> <out.iso>

The data track is the run of sectors with a sync header at the start of the disc.
"""
import sys, os
if len(sys.argv) != 3:
    sys.exit(__doc__)
src, out = sys.argv[1], sys.argv[2]
SECTOR = 2352
SYNC = b'\x00' + b'\xff'*10 + b'\x00'
n = 0
with open(src, 'rb') as f, open(out, 'wb') as o:
    while True:
        s = f.read(SECTOR)
        if len(s) < SECTOR or s[:12] != SYNC:
            break
        if s[15] == 1:
            o.write(s[16:16+2048])
        elif s[15] == 2:
            o.write(s[24:24+2048])
        else:
            sys.exit('sector %d: unknown mode %d' % (n, s[15]))
        n += 1
if n == 0:
    sys.exit('%s does not start with a data track' % src)
print('data track: %d sectors' % n)
