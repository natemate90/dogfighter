import sys, struct, collections
path=sys.argv[1]; f=open(path,'rb'); h=f.read(32)
v=struct.unpack('<6I',h[8:32])
f.seek(v[3]); names=f.read(v[2])
def s(o):
    e=names.index(b'\0',o); return names[o:e].decode('latin-1')
f.seek(v[5]); ft=f.read(v[4])
f.seek(v[1]); dt=f.read(v[0])
print(path,'files',len(ft)//24,'dir-ish entries',len(dt)//24)
ext=collections.defaultdict(lambda:[0,0,collections.Counter(),None]); comp=0
files=[]
for i in range(len(ft)//24):
    a,b,c,sz,sz2,off=struct.unpack_from('<6I',ft,i*24)
    n=s(b); d=s(a) if a<len(names) else '?'
    files.append((d,n,sz,sz2,off))
    if sz!=sz2: comp+=1
    e=n.rsplit('.',1)[-1].lower() if '.' in n else '(none)'
    f.seek(off); m=f.read(8)
    x=ext[e]; x[0]+=1; x[1]+=sz; x[2][m[:4]]+=1; x[3]=d+'\\'+n
print('entries with size!=size2:',comp)
for e,x in sorted(ext.items(), key=lambda kv:-kv[1][1]):
    print('%-8s n=%5d bytes=%10d magic=%s eg=%s'%(e,x[0],x[1],dict(x[2].most_common(3)),x[3]))
if len(sys.argv)>2:
    for r in files:
        if sys.argv[2].lower() in (r[0]+'\\'+r[1]).lower(): print(r)
