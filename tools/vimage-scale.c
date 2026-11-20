#include <Accelerate/Accelerate.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/types.h>

static int torn;

static char *field(void)
{
    char *text = NULL;
    size_t room = 0;
    ssize_t length = getdelim(&text, &room, '\0', stdin);

    if (length > 0 && !text[length - 1]) return text;
    if (length > 0) torn = 1;
    free(text);
    return NULL;
}

static int number(unsigned long *value)
{
    char *text = field(), *end = NULL;
    int ok = text && *text;

    if (ok) *value = strtoul(text, &end, 10);
    ok = ok && !*end && *value > 0 && *value <= 16384;
    free(text);
    return ok;
}

int main(void)
{
    char *in, *out;
    unsigned long w, h, nw, nh;
    int failed = 0;

    while ((in = field()))
    {
        if (!(out = field()) || !number(&w) || !number(&h) || !number(&nw) || !number(&nh))
        {
            fprintf(stderr, "vimage-scale: the job list ends in the middle of a job, after %s\n", in);
            return 2;
        }

        vImage_Buffer src = { malloc(w * h * 4), h, w, w * 4 };
        vImage_Buffer dst = { malloc(nw * nh * 4), nh, nw, nw * 4 };
        FILE *f = fopen(in, "rb");
        int ok = f && src.data && dst.data && fread(src.data, 4, w * h, f) == w * h;

        if (f) fclose(f);
        ok = ok && vImageScale_ARGB8888(&src, &dst, NULL, kvImageHighQualityResampling | kvImageEdgeExtend) == kvImageNoError;
        f = ok ? fopen(out, "wb") : NULL;
        ok = f && fwrite(dst.data, 4, nw * nh, f) == nw * nh;
        if (f && fclose(f)) ok = 0;
        if (!ok)
        {
            fprintf(stderr, "vimage-scale: could not resize %s\n", in);
            failed = 1;
        }
        free(src.data);
        free(dst.data);
        free(in);
        free(out);
    }
    if (torn)
    {
        fprintf(stderr, "vimage-scale: the job list ends in the middle of a job\n");
        return 2;
    }
    return failed;
}
