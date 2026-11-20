#include <CoreGraphics/CoreGraphics.h>
#include <CoreText/CoreText.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>

#define FINE 16
#define MOST 64

typedef struct {
    double spread, top[3], bottom[3];
} Layer;

typedef struct {
    char *font, *text;
    size_t index, dxs, layers;
    double size, sx, weight, x, base, track, dx[MOST];
    Layer layer[4];
} Line;

static char *field(void)
{
    char *text = NULL;
    size_t room = 0;
    ssize_t length = getdelim(&text, &room, '\0', stdin);

    if (length > 0 && !text[length - 1]) return text;
    free(text);
    return NULL;
}

static int count(size_t *value, size_t most)
{
    char *text = field(), *end = NULL;
    int ok = text && *text;

    if (ok) value[0] = strtoul(text, &end, 10);
    ok = ok && !end[0] && value[0] <= most;
    free(text);
    return ok;
}

static int real(double *value)
{
    char *text = field(), *end = NULL;
    int ok = text && *text;

    if (ok) value[0] = strtod(text, &end);
    ok = ok && !end[0] && isfinite(value[0]);
    free(text);
    return ok;
}

static int line_fields(Line *line)
{
    size_t i;
    int ok;

    memset(line, 0, sizeof *line);
    line->font = field();
    ok = line->font && count(&line->index, 64);
    line->text = ok ? field() : NULL;
    ok = ok && line->text && real(&line->size) && real(&line->sx) && real(&line->weight) && real(&line->x) &&
         real(&line->base) && real(&line->track) && count(&line->dxs, MOST);
    for (i = 0; ok && i < line->dxs; i++) ok = real(&line->dx[i]);
    ok = ok && count(&line->layers, 4);
    for (i = 0; ok && i < line->layers; i++) {
        Layer *l = &line->layer[i];
        ok = real(&l->spread) && real(&l->top[0]) && real(&l->top[1]) && real(&l->top[2]) &&
             real(&l->bottom[0]) && real(&l->bottom[1]) && real(&l->bottom[2]);
    }
    return ok;
}

static void line_free(Line *line)
{
    free(line->font);
    free(line->text);
}

static CTFontRef open_font(const char *path, size_t index, double size)
{
    FILE *f = fopen(path, "rb");
    CFMutableDataRef data;
    unsigned char block[65536];
    size_t got;
    CFArrayRef found;
    CTFontRef font = NULL;

    if (!f) return NULL;
    data = CFDataCreateMutable(NULL, 0);
    while ((got = fread(block, 1, sizeof block, f)) > 0) CFDataAppendBytes(data, block, (CFIndex)got);
    fclose(f);
    found = CTFontManagerCreateFontDescriptorsFromData(data);
    CFRelease(data);
    if (found && (CFIndex)index < CFArrayGetCount(found))
        font = CTFontCreateWithFontDescriptor(CFArrayGetValueAtIndex(found, (CFIndex)index), size, NULL);
    if (found) CFRelease(found);
    return font;
}

static CGPathRef line_path(const Line *line, double *cap, double *natural)
{
    CTFontRef font = open_font(line->font, line->index, line->size * FINE);
    CFStringRef text, keys[2] = {kCTFontAttributeName, kCTLigatureAttributeName};
    int zero = 0;
    CFNumberRef none;
    CFTypeRef values[2];
    CFDictionaryRef attributes;
    CFAttributedStringRef styled;
    CTLineRef laid;
    CFArrayRef runs;
    CFIndex r, g;
    CGMutablePathRef glyphs, placed;
    double lo = INFINITY, hi = -INFINITY;
    CGAffineTransform move;

    if (!font) return NULL;
    none = CFNumberCreate(NULL, kCFNumberIntType, &zero);
    glyphs = CGPathCreateMutable();
    placed = CGPathCreateMutable();
    text = CFStringCreateWithCString(NULL, line->text, kCFStringEncodingUTF8);
    values[0] = font;
    values[1] = none;
    attributes = CFDictionaryCreate(NULL, (const void **)keys, values, 2, &kCFTypeDictionaryKeyCallBacks,
                                    &kCFTypeDictionaryValueCallBacks);
    styled = CFAttributedStringCreate(NULL, text, attributes);
    laid = CTLineCreateWithAttributedString(styled);
    runs = CTLineGetGlyphRuns(laid);
    for (r = 0; r < CFArrayGetCount(runs); r++) {
        CTRunRef run = CFArrayGetValueAtIndex(runs, r);
        CFIndex n = CTRunGetGlyphCount(run);
        CTFontRef used = CFDictionaryGetValue(CTRunGetAttributes(run), kCTFontAttributeName);
        CGGlyph *ids = malloc(sizeof *ids * (size_t)(n ? n : 1));
        CGPoint *at = malloc(sizeof *at * (size_t)(n ? n : 1));
        CFIndex *from = malloc(sizeof *from * (size_t)(n ? n : 1));

        CTRunGetGlyphs(run, CFRangeMake(0, 0), ids);
        CTRunGetPositions(run, CFRangeMake(0, 0), at);
        CTRunGetStringIndices(run, CFRangeMake(0, 0), from);
        for (g = 0; g < n; g++) {
            size_t i = (size_t)from[g];
            double pen = line->sx * at[g].x + FINE * (line->track * (double)i + (i < line->dxs ? line->dx[i] : 0));
            CGAffineTransform put = CGAffineTransformMake(line->sx, 0, 0, -1, pen, 0);
            CGPathRef shape = CTFontCreatePathForGlyph(used ? used : font, ids[g], &put);
            CGRect box;

            if (!shape) continue;
            box = CGPathGetPathBoundingBox(shape);
            if (!CGRectIsEmpty(box)) {
                if (CGRectGetMinX(box) < lo) lo = CGRectGetMinX(box);
                if (CGRectGetMaxX(box) > hi) hi = CGRectGetMaxX(box);
            }
            CGPathAddPath(glyphs, NULL, shape);
            CGPathRelease(shape);
        }
        free(ids);
        free(at);
        free(from);
    }
    if (!isfinite(lo)) lo = hi = 0;
    move = CGAffineTransformMakeTranslation(line->x * FINE - lo, line->base * FINE);
    CGPathAddPath(placed, &move, glyphs);
    cap[0] = CTFontGetCapHeight(font) / FINE;
    natural[0] = (hi - lo) / FINE;
    CGPathRelease(glyphs);
    CFRelease(laid);
    CFRelease(styled);
    CFRelease(attributes);
    CFRelease(text);
    CFRelease(none);
    CFRelease(font);
    return placed;
}

static float *cover(CGPathRef path, double spread, size_t w, size_t h, size_t scale)
{
    size_t fw = w * FINE, fh = h * FINE, step = FINE / scale, x, y, i, j;
    unsigned char *fine = calloc(fw * fh, 1);
    float *out = calloc(w * scale * h * scale, sizeof *out);
    CGColorSpaceRef grey = CGColorSpaceCreateDeviceGray();
    CGContextRef ctx = CGBitmapContextCreate(fine, fw, fh, 8, fw, grey, (CGBitmapInfo)kCGImageAlphaNone);

    CGColorSpaceRelease(grey);
    CGContextTranslateCTM(ctx, 0, (CGFloat)fh);
    CGContextScaleCTM(ctx, 1, -1);
    CGContextSetShouldAntialias(ctx, true);
    CGContextSetLineJoin(ctx, kCGLineJoinRound);
    CGContextSetLineCap(ctx, kCGLineCapRound);
    CGContextSetGrayFillColor(ctx, 1, 1);
    CGContextAddPath(ctx, path);
    CGContextFillPath(ctx);
    if (spread != 0) {
        CGContextSetGrayStrokeColor(ctx, spread > 0 ? 1 : 0, 1);
        CGContextSetLineWidth(ctx, (CGFloat)(2 * fabs(spread) * FINE));
        CGContextAddPath(ctx, path);
        CGContextStrokePath(ctx);
    }
    CGContextRelease(ctx);
    for (y = 0; y < h * scale; y++)
        for (x = 0; x < w * scale; x++) {
            unsigned sum = 0;
            for (j = 0; j < step; j++)
                for (i = 0; i < step; i++) sum += fine[(y * step + j) * fw + x * step + i];
            out[y * w * scale + x] = (float)sum / (255.0f * (float)(step * step));
        }
    free(fine);
    return out;
}

static void turn_once(const double *in, double *out, size_t w, size_t h, size_t depth)
{
    size_t i, j, c;
    for (i = 0; i < w; i++)
        for (j = 0; j < h; j++)
            for (c = 0; c < depth; c++) out[(i * h + j) * depth + c] = in[(j * w + (w - 1 - i)) * depth + c];
}

static double *turned(const double *in, size_t *w, size_t *h, size_t depth, size_t times)
{
    double *a = malloc(w[0] * h[0] * depth * sizeof *a), *b = malloc(w[0] * h[0] * depth * sizeof *b), *t;
    size_t k, s;

    memcpy(a, in, w[0] * h[0] * depth * sizeof *a);
    for (k = 0; k < times % 4; k++) {
        turn_once(a, b, w[0], h[0], depth);
        s = w[0];
        w[0] = h[0];
        h[0] = s;
        t = a;
        a = b;
        b = t;
    }
    free(b);
    return a;
}

static double ink_share(const double *p, const double *ink, const double *bg)
{
    double d, n = 0, t = 0;
    int c;
    for (c = 0; c < 3; c++) {
        d = ink[c] - bg[c];
        n += d * d;
        t += (p[c] - bg[c]) * d;
    }
    t = n > 0 ? t / n : 0;
    return t < 0 ? 0 : t > 1 ? 1 : t;
}

static void grow(unsigned char *mask, size_t w, size_t h, size_t times)
{
    unsigned char *next = malloc(w * h);
    size_t k, x, y;
    for (k = 0; k < times; k++) {
        memcpy(next, mask, w * h);
        for (y = 0; y < h; y++)
            for (x = 0; x < w; x++)
                if (!mask[y * w + x] && ((x && mask[y * w + x - 1]) || (x + 1 < w && mask[y * w + x + 1]) ||
                                         (y && mask[(y - 1) * w + x]) || (y + 1 < h && mask[(y + 1) * w + x])))
                    next[y * w + x] = 1;
        memcpy(mask, next, w * h);
    }
    free(next);
}

static double *row_background(const double *p, size_t w, size_t h, const double *ink)
{
    double *rows = calloc(h * 3, sizeof *rows), *out = malloc(w * h * 3 * sizeof *out), *far = malloc(w * sizeof *far);
    char *used = malloc(w);
    size_t keep = w / 12 > 3 ? w / 12 : 3, x, y, k, c;

    if (keep > w) keep = w;
    for (y = 0; y < h; y++) {
        memset(used, 0, w);
        for (x = 0; x < w; x++) {
            far[x] = 0;
            for (c = 0; c < 3; c++) far[x] += (p[(y * w + x) * 3 + c] - ink[c]) * (p[(y * w + x) * 3 + c] - ink[c]);
        }
        for (k = 0; k < keep; k++) {
            size_t best = 0;
            double most = -1;
            for (x = 0; x < w; x++)
                if (!used[x] && far[x] > most) {
                    most = far[x];
                    best = x;
                }
            used[best] = 1;
            for (c = 0; c < 3; c++) rows[y * 3 + c] += p[(y * w + best) * 3 + c] / (double)keep;
        }
    }
    for (y = 0; y < h; y++)
        for (c = 0; c < 3; c++) {
            double v = (rows[(y ? y - 1 : 0) * 3 + c] + 2 * rows[y * 3 + c] + rows[(y + 1 < h ? y + 1 : y) * 3 + c]) / 4;
            for (x = 0; x < w; x++) out[(y * w + x) * 3 + c] = v;
        }
    free(rows);
    free(far);
    free(used);
    return out;
}

static void fill_in(double *p, const unsigned char *mask, const double *start, size_t w, size_t h, size_t rounds)
{
    double *next = malloc(w * h * 3 * sizeof *next);
    size_t k, x, y, c;

    for (x = 0; x < w * h; x++)
        if (mask[x])
            for (c = 0; c < 3; c++) p[x * 3 + c] = start[x * 3 + c];
    for (k = 0; k < rounds; k++) {
        memcpy(next, p, w * h * 3 * sizeof *next);
        for (y = 0; y < h; y++)
            for (x = 0; x < w; x++) {
                size_t l = x ? x - 1 : x, r = x + 1 < w ? x + 1 : x, u = y ? y - 1 : y, d = y + 1 < h ? y + 1 : y;
                if (!mask[y * w + x]) continue;
                for (c = 0; c < 3; c++)
                    next[(y * w + x) * 3 + c] = (p[(y * w + l) * 3 + c] + p[(y * w + r) * 3 + c] + p[(u * w + x) * 3 + c] +
                                                 p[(d * w + x) * 3 + c]) / 4;
            }
        memcpy(p, next, w * h * 3 * sizeof *next);
    }
    free(next);
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

static int save(const char *path, const void *data, size_t bytes)
{
    FILE *f = fopen(path, "wb");
    int ok = f && fwrite(data, 1, bytes, f) == bytes;

    if (f && fclose(f)) ok = 0;
    return ok;
}

static void surround(const unsigned char *pixels, size_t pw, size_t ph, size_t scale, const size_t *box, size_t turn, const size_t *around,
                     double *frame, const unsigned char *mask, const double *bg, size_t fw, size_t fh)
{
    size_t bw = (box[2] - box[0]) * scale, bh = (box[3] - box[1]) * scale, w = fw, h = fh, x, y, c;
    size_t left = box[0] && around[0] ? scale : 0, top = box[1] && around[1] ? scale : 0;
    size_t right = box[2] * scale < pw && around[2] ? scale : 0, bottom = box[3] * scale < ph && around[3] ? scale : 0;
    size_t ew = bw + left + right, eh = bh + top + bottom, ox = box[0] * scale - left, oy = box[1] * scale - top;
    double *flags = malloc(fw * fh * sizeof *flags), *upright_mask, *upright_bg, *upright, *wide = calloc(ew * eh * 3, sizeof *wide);
    double *start = calloc(ew * eh * 3, sizeof *start), *inner = malloc(bw * bh * 3 * sizeof *inner), *again;
    unsigned char *fill = calloc(ew * eh, 1);

    for (x = 0; x < fw * fh; x++) flags[x] = mask[x];
    upright_mask = turned(flags, &w, &h, 1, 4 - turn % 4);
    w = fw;
    h = fh;
    upright_bg = turned(bg, &w, &h, 3, 4 - turn % 4);
    w = fw;
    h = fh;
    upright = turned(frame, &w, &h, 3, 4 - turn % 4);
    for (y = 0; y < eh; y++)
        for (x = 0; x < ew; x++)
            for (c = 0; c < 3; c++) wide[(y * ew + x) * 3 + c] = pixels[((oy + y) * pw + ox + x) * 4 + c];
    for (y = 0; y < bh; y++)
        for (x = 0; x < bw; x++) {
            size_t at = (y + top) * ew + x + left;
            fill[at] = upright_mask[y * bw + x] > 0.5;
            for (c = 0; c < 3; c++) {
                start[at * 3 + c] = upright_bg[(y * bw + x) * 3 + c];
                wide[at * 3 + c] = upright[(y * bw + x) * 3 + c];
            }
        }
    fill_in(wide, fill, start, ew, eh, 400 * scale);
    for (y = 0; y < bh; y++)
        for (x = 0; x < bw; x++)
            for (c = 0; c < 3; c++) inner[(y * bw + x) * 3 + c] = wide[((y + top) * ew + x + left) * 3 + c];
    w = bw;
    h = bh;
    again = turned(inner, &w, &h, 3, turn);
    memcpy(frame, again, fw * fh * 3 * sizeof *frame);
    free(again);
    free(flags);
    free(upright_mask);
    free(upright_bg);
    free(upright);
    free(wide);
    free(start);
    free(inner);
    free(fill);
}

static const char *region(unsigned char *pixels, size_t pw, size_t ph, size_t scale, const size_t *box, size_t turn, const size_t *around,
                          const double *ink, double threshold, Line *lines, size_t nlines)
{
    size_t bw = (box[2] - box[0]) * scale, bh = (box[3] - box[1]) * scale, fw = bw, fh = bh, x, y, c, l, k;
    double *crop = malloc(bw * bh * 3 * sizeof *crop), *frame, *bg, *back;
    unsigned char *mask;
    float **covers = calloc(nlines * 4 + 1, sizeof *covers);
    double *caps = calloc(nlines + 1, sizeof *caps);
    const char *problem = NULL;

    for (y = 0; y < bh; y++)
        for (x = 0; x < bw; x++)
            for (c = 0; c < 3; c++)
                crop[(y * bw + x) * 3 + c] = pixels[((box[1] * scale + y) * pw + box[0] * scale + x) * 4 + c];
    frame = turned(crop, &fw, &fh, 3, turn);
    for (l = 0; l < nlines && !problem; l++) {
        double natural;
        CGPathRef path = line_path(&lines[l], &caps[l], &natural);
        if (!path) {
            problem = "a font could not be opened";
            break;
        }
        for (k = 0; k < lines[l].layers; k++)
            covers[l * 4 + k] = cover(path, lines[l].weight + lines[l].layer[k].spread, fw / scale, fh / scale, scale);
        CGPathRelease(path);
    }
    if (!problem) {
        bg = row_background(frame, fw, fh, ink);
        mask = calloc(fw * fh, 1);
        for (x = 0; x < fw * fh; x++) {
            int on = ink_share(&frame[x * 3], ink, &bg[x * 3]) > threshold;
            for (l = 0; l < nlines; l++)
                for (k = 0; k < lines[l].layers; k++) on = on || covers[l * 4 + k][x] > 0.02f;
            mask[x] = (unsigned char)on;
        }
        grow(mask, fw, fh, scale / 2 ? scale / 2 : 1);
        surround(pixels, pw, ph, scale, box, turn, around, frame, mask, bg, fw, fh);
        for (l = 0; l < nlines; l++)
            for (k = 0; k < lines[l].layers; k++) {
                Layer *layer = &lines[l].layer[k];
                double top = lines[l].base - caps[l], bottom = lines[l].base;
                for (y = 0; y < fh; y++) {
                    double at = ((double)y + 0.5) / (double)scale, t = bottom > top ? (at - top) / (bottom - top) : 0;
                    t = t < 0 ? 0 : t > 1 ? 1 : t;
                    for (x = 0; x < fw; x++) {
                        double a = covers[l * 4 + k][y * fw + x];
                        for (c = 0; c < 3; c++) {
                            double colour = layer->top[c] + (layer->bottom[c] - layer->top[c]) * t;
                            frame[(y * fw + x) * 3 + c] = frame[(y * fw + x) * 3 + c] * (1 - a) + colour * a;
                        }
                    }
                }
            }
        back = turned(frame, &fw, &fh, 3, 4 - turn % 4);
        for (y = 0; y < bh; y++)
            for (x = 0; x < bw; x++)
                for (c = 0; c < 3; c++) {
                    double v = floor(back[(y * bw + x) * 3 + c] + 0.5);
                    pixels[((box[1] * scale + y) * pw + box[0] * scale + x) * 4 + c] = (unsigned char)(v < 0 ? 0 : v > 255 ? 255 : v);
                }
        free(back);
        free(bg);
        free(mask);
    }
    for (l = 0; l < nlines * 4; l++) free(covers[l]);
    free(covers);
    free(caps);
    free(crop);
    free(frame);
    return problem;
}

static const char *draw(void)
{
    char *made = field(), *out = NULL, *copy = NULL;
    size_t w = 0, h = 0, scale = 0, regions = 0, n, i, j;
    unsigned char *pixels = NULL, *other = NULL;
    const char *problem = NULL;
    int ok = made && count(&w, 4096) && count(&h, 4096) && count(&scale, FINE) && (out = field()) && (copy = field()) &&
             count(&regions, 64) && scale && FINE % scale == 0 && w % scale == 0 && h % scale == 0;

    if (ok && !(pixels = load(made, w * h * 4))) problem = "the made picture could not be read";
    if (ok && !problem && *copy && !(other = load(copy, w * h * 4))) problem = "the copy picture could not be read";
    for (n = 0; ok && n < regions; n++) {
        char *kind = field();
        size_t box[4], around[4] = {0, 0, 0, 0}, turn = 0, nlines = 0, l = 0;
        double ink[3], threshold;
        Line lines[16];

        ok = kind && count(&box[0], w / scale) && count(&box[1], h / scale) && count(&box[2], w / scale) && count(&box[3], h / scale) &&
             box[0] < box[2] && box[1] < box[3];
        if (ok && !strcmp(kind, "copy")) {
            if (!other && !problem) problem = "a copy region has no copy picture";
            for (i = box[1] * scale; !problem && i < box[3] * scale; i++)
                for (j = box[0] * scale; j < box[2] * scale; j++) memcpy(pixels + (i * w + j) * 4, other + (i * w + j) * 4, 3);
        } else if (ok) {
            ok = !strcmp(kind, "text") && count(&turn, 3) && count(&around[0], 1) && count(&around[1], 1) && count(&around[2], 1) &&
                 count(&around[3], 1) && real(&ink[0]) && real(&ink[1]) && real(&ink[2]) && real(&threshold) &&
                 count(&nlines, 16);
            for (l = 0; ok && l < nlines; l++)
                if (!(ok = line_fields(&lines[l]))) line_free(&lines[l]);
            if (ok && !problem) problem = region(pixels, w, h, scale, box, turn, around, ink, threshold, lines, nlines);
            for (i = 0; i < l && ok; i++) line_free(&lines[i]);
        }
        free(kind);
    }
    if (!ok) problem = "the job could not be read";
    if (!problem && !save(out, pixels, w * h * 4)) problem = "the result could not be written";
    free(made);
    free(out);
    free(copy);
    free(pixels);
    free(other);
    return problem;
}

static const char *cover_job(double *cap, double *natural)
{
    size_t w = 0, h = 0, scale = 0;
    double spread = 0;
    char *out = NULL;
    Line line;
    const char *problem = NULL;
    int ok = count(&w, 4096) && count(&h, 4096) && count(&scale, FINE) && scale && FINE % scale == 0 && (out = field()) &&
             real(&spread) && line_fields(&line);

    if (!ok) problem = "the job could not be read";
    else {
        CGPathRef path = line_path(&line, cap, natural);
        if (!path) problem = "the font could not be opened";
        else {
            float *a = cover(path, line.weight + spread, w, h, scale);
            if (!save(out, a, w * scale * h * scale * sizeof *a)) problem = "the coverage could not be written";
            free(a);
            CGPathRelease(path);
        }
        line_free(&line);
    }
    free(out);
    return problem;
}

int main(void)
{
    char *kind;

    while ((kind = field())) {
        const char *problem;
        double cap = 0, natural = 0;

        if (!strcmp(kind, "draw")) problem = draw();
        else if (!strcmp(kind, "cover")) problem = cover_job(&cap, &natural);
        else problem = "unknown job";
        if (problem) printf("fail %s\n", problem);
        else printf("ok %.6f %.6f\n", cap, natural);
        fflush(stdout);
        free(kind);
    }
    return 0;
}
