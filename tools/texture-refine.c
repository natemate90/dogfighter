#include <CoreGraphics/CoreGraphics.h>
#include <ImageIO/ImageIO.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
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

static int number(size_t *value, size_t most)
{
    char *text = field(), *end = NULL;
    int ok = text && *text;

    if (ok) value[0] = strtoul(text, &end, 10);
    ok = ok && !end[0] && value[0] <= most;
    free(text);
    return ok;
}

static unsigned char *load(const char *path, size_t bytes)
{
    unsigned char *data = malloc(bytes ? bytes : 1);
    FILE *f = fopen(path, "rb");
    int ok = f && data && fread(data, 1, bytes, f) == bytes && fgetc(f) == EOF;

    if (f) fclose(f);
    if (ok) return data;
    free(data);
    return NULL;
}

static int save(const char *path, const unsigned char *data, size_t bytes)
{
    FILE *f = fopen(path, "wb");
    int ok = f && fwrite(data, 1, bytes, f) == bytes;

    if (f && fclose(f)) ok = 0;
    return ok;
}

static const char *bleed(const char *in, const char *out, size_t w, size_t h)
{
    size_t count = w * h, left = 0, i;
    unsigned char *pixels = load(in, count * 4);
    unsigned char *known = malloc(count), *next = malloc(count);
    const char *problem = NULL;

    if (!pixels || !known || !next) problem = "cannot read the picture";
    for (i = 0; !problem && i < count; i++) left += !(known[i] = pixels[i * 4 + 3] != 0);
    while (!problem && left && left < count)
    {
        memcpy(next, known, count);
        for (size_t y = 0; y < h; y++)
            for (size_t x = 0; x < w; x++)
            {
                unsigned sum[3] = { 0, 0, 0 }, found = 0;

                if (known[y * w + x]) continue;
                for (int dy = -1; dy <= 1; dy++)
                    for (int dx = -1; dx <= 1; dx++)
                    {
                        size_t ny = y + dy, nx = x + dx;

                        if (ny >= h || nx >= w || !known[ny * w + nx]) continue;
                        for (int c = 0; c < 3; c++) sum[c] += pixels[(ny * w + nx) * 4 + c];
                        found++;
                    }
                if (!found) continue;
                for (int c = 0; c < 3; c++) pixels[(y * w + x) * 4 + c] = (unsigned char)((sum[c] + found / 2) / found);
                next[y * w + x] = 1;
                left--;
            }
        memcpy(known, next, count);
    }
    if (!problem && !save(out, pixels, count * 4)) problem = "cannot write the picture";
    free(pixels);
    free(known);
    free(next);
    return problem;
}

static float *detail_colour(const char *path, size_t w, size_t h, size_t scale)
{
    CFURLRef url = CFURLCreateFromFileSystemRepresentation(NULL, (const UInt8 *)path, (CFIndex)strlen(path), false);
    CGImageSourceRef source = url ? CGImageSourceCreateWithURL(url, NULL) : NULL;
    CGImageRef image = source ? CGImageSourceCreateImageAtIndex(source, 0, NULL) : NULL;
    CFDataRef data = image ? CGDataProviderCopyData(CGImageGetDataProvider(image)) : NULL;
    float *out = NULL;

    if (data && CGImageGetBitsPerComponent(image) == 8)
    {
        size_t pw = CGImageGetWidth(image), ph = CGImageGetHeight(image);
        size_t size = CGImageGetBitsPerPixel(image) / 8, row = CGImageGetBytesPerRow(image);
        size_t ratio = pw / (w * scale), first = 0;
        CGImageAlphaInfo alpha = CGImageGetAlphaInfo(image);
        CGBitmapInfo order = CGImageGetBitmapInfo(image) & kCGBitmapByteOrderMask;
        const UInt8 *bytes = CFDataGetBytePtr(data);
        int plain_order = order == kCGBitmapByteOrderDefault || order == kCGBitmapByteOrder32Big;
        CGColorSpaceModel model = CGColorSpaceGetModel(CGImageGetColorSpace(image));
        size_t step = size > 2 ? 1 : 0;

        if (alpha == kCGImageAlphaFirst || alpha == kCGImageAlphaPremultipliedFirst || alpha == kCGImageAlphaNoneSkipFirst) first = 1;
        if (plain_order && model == (size > 2 ? kCGColorSpaceModelRGB : kCGColorSpaceModelMonochrome) && size >= 1 && size <= 4 && ratio >= 1 && pw == w * scale * ratio && ph == h * scale * ratio
            && (size_t)CFDataGetLength(data) >= (ph - 1) * row + pw * size
            && (out = malloc(w * scale * h * scale * 3 * sizeof(float))))
        {
            for (size_t y = 0; y < h * scale; y++)
                for (size_t x = 0; x < w * scale; x++)
                    for (size_t c = 0; c < 3; c++)
                    {
                        unsigned sum = 0;

                        for (size_t j = 0; j < ratio; j++)
                            for (size_t i = 0; i < ratio; i++)
                                sum += bytes[(y * ratio + j) * row + (x * ratio + i) * size + first + c * step];
                        out[(y * w * scale + x) * 3 + c] = (float)sum / (float)(ratio * ratio);
                    }
        }
    }
    if (data) CFRelease(data);
    if (image) CGImageRelease(image);
    if (source) CFRelease(source);
    if (url) CFRelease(url);
    return out;
}

static void shrink(const float *big, size_t w, size_t h, size_t scale, float *small)
{
    for (size_t y = 0; y < h; y++)
        for (size_t x = 0; x < w; x++)
            for (size_t c = 0; c < 3; c++)
            {
                float sum = 0;

                for (size_t j = 0; j < scale; j++)
                    for (size_t i = 0; i < scale; i++)
                        sum += big[((y * scale + j) * w * scale + x * scale + i) * 3 + c];
                small[(y * w + x) * 3 + c] = sum / (float)(scale * scale);
            }
}

static void add_enlarged(float *big, const float *small, size_t w, size_t h, size_t scale)
{
    for (size_t y = 0; y < h * scale; y++)
    {
        float fy = ((float)y + 0.5f) / (float)scale - 0.5f;
        float ty = fy < 0 ? 0 : fy > (float)(h - 1) ? (float)(h - 1) : fy;
        size_t y0 = (size_t)ty, y1 = y0 + 1 < h ? y0 + 1 : y0;
        float wy = ty - (float)y0;

        for (size_t x = 0; x < w * scale; x++)
        {
            float fx = ((float)x + 0.5f) / (float)scale - 0.5f;
            float tx = fx < 0 ? 0 : fx > (float)(w - 1) ? (float)(w - 1) : fx;
            size_t x0 = (size_t)tx, x1 = x0 + 1 < w ? x0 + 1 : x0;
            float wx = tx - (float)x0;

            for (size_t c = 0; c < 3; c++)
                big[(y * w * scale + x) * 3 + c] +=
                    (1 - wy) * ((1 - wx) * small[(y0 * w + x0) * 3 + c] + wx * small[(y0 * w + x1) * 3 + c])
                    + wy * ((1 - wx) * small[(y1 * w + x0) * 3 + c] + wx * small[(y1 * w + x1) * 3 + c]);
        }
    }
}

static double decibel(double squares, double count)
{
    double psnr = count > 0 && squares > 0 ? 10.0 * log10(255.0 * 255.0 * count / squares) : 99.0;

    return psnr > 99.0 ? 99.0 : psnr;
}

struct likeness { double whole, worst; };

static struct likeness compare(const unsigned char *original, const float *small, size_t w, size_t h, size_t border)
{
    struct likeness found = { 0, 99.0 };
    double squares = 0, count = 0;

    for (size_t by = border; by < h - border; by += 8)
        for (size_t bx = border; bx < w - border; bx += 8)
        {
            double block = 0, seen = 0;

            for (size_t y = by; y < by + 8 && y < h - border; y++)
                for (size_t x = bx; x < bx + 8 && x < w - border; x++)
                {
                    if (!original[(y * w + x) * 4 + 3]) continue;
                    for (size_t c = 0; c < 3; c++)
                    {
                        double d = (double)original[(y * w + x) * 4 + c] - (double)small[(y * w + x) * 3 + c];
                        block += d * d;
                    }
                    seen += 3;
                }
            squares += block;
            count += seen;
            if (seen >= 48 && decibel(block, seen) < found.worst) found.worst = decibel(block, seen);
        }
    found.whole = decibel(squares, count);
    return found;
}

static void seams(const unsigned char *pixels, size_t w, size_t h, size_t border, double out[4])
{
    size_t iw = w - 2 * border, ih = h - 2 * border;
    double seam_x = 0, inside_x = 0, seam_y = 0, inside_y = 0;

    for (size_t y = 0; y < ih; y++)
        for (size_t x = 0; x < iw; x++)
            for (size_t c = 0; c < 4; c++)
            {
                int here = pixels[((y + border) * w + x + border) * 4 + c];
                int right = pixels[((y + border) * w + (x + 1) % iw + border) * 4 + c];
                int below = pixels[(((y + 1) % ih + border) * w + x + border) * 4 + c];

                if (x + 1 < iw) inside_x += abs(here - right); else seam_x += abs(here - right);
                if (y + 1 < ih) inside_y += abs(here - below); else seam_y += abs(here - below);
            }
    out[0] = seam_x / (double)(ih * 4);
    out[1] = iw > 1 ? inside_x / (double)(ih * 4 * (iw - 1)) : 0;
    out[2] = seam_y / (double)(iw * 4);
    out[3] = ih > 1 ? inside_y / (double)(iw * 4 * (ih - 1)) : 0;
}

static const char *refine(const char *original_path, const char *plain_path, const char *detail_path, const char *out_path,
                          size_t w, size_t h, size_t scale, size_t border, size_t passes)
{
    size_t bw = w * scale, bh = h * scale;
    unsigned char *original = load(original_path, w * h * 4);
    unsigned char *result = load(plain_path, bw * bh * 4);
    float *big = NULL, *small = malloc(w * h * 3 * sizeof(float));
    struct likeness drift, match;
    double seam[4], before[4];
    const char *problem = NULL;

    if (!original || !result || !small) problem = "cannot read the picture";
    else if (detail_path[0] && !(big = detail_colour(detail_path, w, h, scale))) problem = "the upscaler's picture is missing or has the wrong size";
    else if (!big && !(big = malloc(bw * bh * 3 * sizeof(float)))) problem = "out of memory";
    if (problem) goto done;

    if (!detail_path[0])
        for (size_t i = 0; i < bw * bh; i++)
            for (size_t c = 0; c < 3; c++) big[i * 3 + c] = result[i * 4 + c];

    shrink(big, w, h, scale, small);
    drift = compare(original, small, w, h, border);
    for (size_t pass = 0; pass < passes; pass++)
    {
        for (size_t i = 0; i < w * h; i++)
            for (size_t c = 0; c < 3; c++) small[i * 3 + c] = (float)original[i * 4 + c] - small[i * 3 + c];
        add_enlarged(big, small, w, h, scale);
        shrink(big, w, h, scale, small);
    }
    if (passes)
        for (size_t y = 0; y < bh; y++)
            for (size_t x = 0; x < bw; x++)
                for (size_t c = 0; c < 3; c++)
                {
                    size_t from = (y / scale) * w + x / scale;

                    big[(y * bw + x) * 3 + c] += (float)original[from * 4 + c] - small[from * 3 + c];
                }
    for (size_t i = 0; i < bw * bh; i++)
        for (size_t c = 0; c < 3; c++)
        {
            float v = big[i * 3 + c];

            result[i * 4 + c] = (unsigned char)(v < 0 ? 0 : v > 255 ? 255 : lroundf(v));
            big[i * 3 + c] = result[i * 4 + c];
        }
    shrink(big, w, h, scale, small);
    match = compare(original, small, w, h, border);
    seams(result, bw, bh, border * scale, seam);
    seams(original, w, h, border, before);
    if (!save(out_path, result, bw * bh * 4)) problem = "cannot write the picture";
    else printf("ok %.2f %.2f %.2f %.3f %.3f %.3f %.3f %.3f %.3f\n", drift.whole, match.whole, match.worst,
                seam[0], seam[1], seam[2], seam[3], before[0], before[2]);
done:
    free(original);
    free(result);
    free(big);
    free(small);
    return problem;
}

int main(void)
{
    char *kind;

    while ((kind = field()))
    {
        char *path[4] = { NULL, NULL, NULL, NULL };
        size_t value[5] = { 0, 0, 1, 0, 0 };
        int paths = !strcmp(kind, "bleed") ? 2 : !strcmp(kind, "refine") ? 4 : 0;
        int numbers = paths == 2 ? 2 : 5, ok = paths != 0;
        const char *problem;

        for (int i = 0; ok && i < paths; i++) ok = (path[i] = field()) != NULL;
        for (int i = 0; ok && i < numbers; i++) ok = number(&value[i], 16384);
        ok = ok && value[0] > 0 && value[1] > 0 && value[2] > 0 && value[2] <= 8
             && value[0] > 2 * value[3] && value[1] > 2 * value[3] && value[4] <= 8;
        if (!ok)
        {
            fprintf(stderr, "texture-refine: the job list is broken or ends in the middle of a job\n");
            return 2;
        }
        problem = paths == 2 ? bleed(path[0], path[1], value[0], value[1])
                             : refine(path[0], path[1], path[2], path[3], value[0], value[1], value[2], value[3], value[4]);
        if (problem) printf("fail %s\n", problem);
        else if (paths == 2) printf("ok\n");
        fflush(stdout);
        for (int i = 0; i < 4; i++) free(path[i]);
        free(kind);
    }
    if (torn)
    {
        fprintf(stderr, "texture-refine: the job list ends in the middle of a job\n");
        return 2;
    }
    return 0;
}
