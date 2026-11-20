#include <Accelerate/Accelerate.h>
#include <stdio.h>
#include <stdlib.h>

int main(void)
{
    char in[4096], out[4096];
    unsigned long w, h, nw, nh;
    int failed = 0;

    while (scanf("%4095s %4095s %lu %lu %lu %lu", in, out, &w, &h, &nw, &nh) == 6)
    {
        vImage_Buffer src = { malloc(w * h * 4), h, w, w * 4 };
        vImage_Buffer dst = { malloc(nw * nh * 4), nh, nw, nw * 4 };
        FILE *f = fopen(in, "rb");
        int ok = f && src.data && dst.data && fread(src.data, 4, w * h, f) == w * h;

        if (f) fclose(f);
        ok = ok && vImageScale_ARGB8888(&src, &dst, NULL, kvImageHighQualityResampling | kvImageEdgeExtend) == kvImageNoError;
        f = ok ? fopen(out, "wb") : NULL;
        ok = f && fwrite(dst.data, 4, nw * nh, f) == nw * nh;
        if (f) fclose(f);
        if (!ok)
        {
            fprintf(stderr, "vimage-scale: could not resize %s\n", in);
            failed = 1;
        }
        free(src.data);
        free(dst.data);
    }
    return failed;
}
