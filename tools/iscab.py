"""List or extract an InstallShield 6 cabinet set (data1.hdr, data1.cab, data2.cab).

usage: iscab.py <dir with data1.hdr> [<output dir>]

Without an output dir it only lists the files. With one, it extracts the game files,
English only, and skips any file that already exists there, so it can be run again.
"""
import sys, struct, os, zlib
if len(sys.argv) not in (2, 3):
    sys.exit(__doc__)
srcdir = sys.argv[1]
outdir = sys.argv[2] if len(sys.argv) == 3 else None
extract = outdir is not None
# Entries before this are InstallShield's own engine and setup files.
FIRST_GAME_FILE = 35
OTHER_LANGS = ('French', 'German', 'Italian')
h = open(os.path.join(srcdir,'data1.hdr'),'rb').read()
sig, ver, volinfo, cdo, cds = struct.unpack_from('<5I', h, 0)
if not extract: print('ver %08x major' % ver, (ver>>12)&0xf, 'cdo %x cds %x' % (cdo,cds))
fto, = struct.unpack_from('<I', h, cdo+0x0c)
dircount, = struct.unpack_from('<I', h, cdo+0x1c)
filecount, = struct.unpack_from('<I', h, cdo+0x28)
fto2, = struct.unpack_from('<I', h, cdo+0x2c)
base = cdo+fto
if not extract: print('dirs', dircount, 'files', filecount)
def cstr(o):
    e = h.index(b'\0', o); return h[o:e].decode('latin-1')
dirs = [cstr(base+struct.unpack_from('<I',h,base+4*i)[0]) for i in range(dircount)]
vols = {}
def vol(n):
    if n not in vols:
        p = os.path.join(srcdir,'data%d.cab'%n)
        f = open(p,'rb'); hd = f.read(0x14+56)
        v = struct.unpack_from('<14I', hd, 0x14)
        vols[n] = dict(f=f, size=os.path.getsize(p), first=v[2], last=v[3], foff=v[4], fcomp=v[8], loff=v[10], lcomp=v[12])
    return vols[n]
class Reader:
    def __init__(s, idx, volno, off, obf):
        s.idx=idx; s.volno=volno; s.obf=obf; s.seed=0
        v=vol(volno); s.v=v
        if idx==v['last'] and v['lcomp']: off=v['loff']; s.left=v['lcomp']
        elif idx==v['first'] and v['fcomp']: off=v['foff']; s.left=v['fcomp']
        else: s.left=1<<62
        v['f'].seek(off)
    def read(s, n):
        out=b''
        while n:
            if s.left==0:
                s.volno+=1; v=vol(s.volno); s.v=v
                assert v['first']==s.idx, (v['first'], s.idx)
                v['f'].seek(v['foff']); s.left=v['fcomp']
            k=min(n,s.left); d=s.v['f'].read(k); assert len(d)==k
            s.left-=k; n-=k; out+=d
        if s.obf:
            b=bytearray(out)
            for i in range(len(b)):
                t=b[i]^0xd5; t=((t>>2)|(t<<6))&0xff
                b[i]=(t-(s.seed%0x47))&0xff; s.seed+=1
            out=bytes(b)
        return out
tot=0
for i in range(filecount):
    p = base+fto2+i*0x57
    flags, exp, comp, doff = struct.unpack_from('<HQQQ', h, p)
    nameoff, diridx = struct.unpack_from('<IH', h, p+58)
    lprev, lnext, lflags, volno = struct.unpack_from('<IIBH', h, p+76)
    if flags & 8 or not nameoff: continue
    name = cstr(base+nameoff); d = dirs[diridx] if diridx < dircount else '?'
    rel = (d+'\\'+name if d else name).replace('\\','/')
    tot+=exp
    if not extract:
        print('%3d fl=%02x vol=%d off=%9d comp=%10d exp=%10d %s' % (i,flags,volno,doff,comp,exp,rel))
        continue
    if i<FIRST_GAME_FILE or exp==0: continue
    if os.path.splitext(name)[0] in OTHER_LANGS: continue
    parts=[x for x in rel.split('/') if x not in ('','.','..')]
    dst=os.path.join(outdir,*parts)
    # user.ini, system.ini and readme.txt come once per language, English first.
    # The game also rewrites the ini files, so an existing file is never replaced.
    if os.path.exists(dst): continue
    os.makedirs(os.path.dirname(dst),exist_ok=True)
    r=Reader(i,volno,doff,flags&2)
    part=dst+'.part'
    with open(part,'wb') as o:
        if flags & 4:
            left=comp; w=0
            while left>0:
                n,=struct.unpack('<H', r.read(2)); left-=2+n
                o.write(zlib.decompress(r.read(n), -15))
        else:
            left=exp
            while left: 
                k=min(left,1<<20); o.write(r.read(k)); left-=k
    if os.path.getsize(part)!=exp:
        sys.exit('%s: size %d, expected %d' % (rel, os.path.getsize(part), exp))
    os.replace(part, dst)
    print('extracted', rel)
if not extract: print('total expanded', tot)
