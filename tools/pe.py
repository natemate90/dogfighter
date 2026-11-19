import sys, struct, time
for path in sys.argv[1:]:
    d=open(path,'rb').read()
    pe=struct.unpack_from('<I',d,0x3c)[0]
    mach,nsec,ts,_,_,optsz,ch=struct.unpack_from('<HHIIIHH',d,pe+4)
    o=pe+24
    magic,lmaj,lmin,codesz,idata,udata,ep,_,_,ibase=struct.unpack_from('<HBBIIIIIII',d,o)
    subsys=struct.unpack_from('<H',d,o+68)[0]
    print('==',path.split('/')[-1],'machine %x'%mach,'linker %d.%d'%(lmaj,lmin),'ts',time.strftime('%Y-%m-%d',time.gmtime(ts)),'SizeOfCode',codesz,'subsys',subsys,'chars %x'%ch)
    dd=[struct.unpack_from('<II',d,o+96+8*i) for i in range(16)]
    secs=[]
    so=o+optsz
    for i in range(nsec):
        nm=d[so:so+8].rstrip(b'\0').decode('latin-1'); vs,va,rs,rp=struct.unpack_from('<IIII',d,so+8); fl=struct.unpack_from('<I',d,so+36)[0]
        secs.append((nm,va,vs,rp,rs)); print('   sec %-8s vsize %7d raw %7d flags %08x'%(nm,vs,rs,fl)); so+=40
    def r2o(rva):
        for nm,va,vs,rp,rs in secs:
            if va<=rva<va+max(vs,rs): return rva-va+rp
        return None
    def cs(off):
        e=d.index(b'\0',off); return d[off:e].decode('latin-1')
    # imports
    iv,isz=dd[1]
    if iv:
        p=r2o(iv); out=[]
        while True:
            oft,_,_,nrva,ft=struct.unpack_from('<IIIII',d,p)
            if not nrva: break
            t=r2o(oft or ft); n=0; names=[]
            while True:
                v=struct.unpack_from('<I',d,t)[0]
                if not v: break
                n+=1
                if not v&0x80000000 and len(names)<6: names.append(cs(r2o(v)+2))
                t+=4
            out.append('%s(%d: %s)'%(cs(r2o(nrva)),n,','.join(names))); p+=20
        print('   imports:',' | '.join(out))
    ev,esz=dd[0]
    if ev:
        p=r2o(ev); nfun,nnames=struct.unpack_from('<II',d,p+20); nt=r2o(struct.unpack_from('<I',d,p+32)[0])
        names=[cs(r2o(struct.unpack_from('<I',d,nt+4*i)[0])) for i in range(nnames)]
        print('   exports: %d named %d; sample:'%(nfun,nnames), names[:12])
    dv,dsz=dd[6]
    print('   debugdir',dv,dsz,'reloc',dd[5],'rsrc',dd[2])
    if dv:
        p=r2o(dv)
        for i in range(dsz//28):
            _,_,_,_,typ,sz,rva,ptr=struct.unpack_from('<IIHHIIII',d,p+28*i)
            print('     debug type',typ,'size',sz,'ptr',ptr, d[ptr:ptr+60])
