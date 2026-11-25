#include <windows.h>
#include <math.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

struct wined3d_display_mode_copy
{
    UINT width, height, refresh_rate;
    int format_id, scanline_ordering;
};

struct wined3d_swapchain_desc_start
{
    void *output;
    UINT backbuffer_width, backbuffer_height;
    int backbuffer_format;
    UINT backbuffer_count, backbuffer_bind_flags;
    int multisample_type;
    UINT multisample_quality;
    int swap_effect;
    HWND device_window;
    BOOL windowed;
};

struct wined3d_viewport_copy
{
    float x, y, width, height, min_z, max_z;
};

struct wined3d_resource_desc_copy
{
    int resource_type, format, multisample_type;
    unsigned int multisample_quality, usage, bind_flags, access, width, height, depth, size;
};

#define WINED3DERR_INVALIDCALL ((HRESULT)0x8876086c)
#define CONSOLE_COMMAND 0x41664463
#define CONSOLE_COMMAND_RUN 1
#define CONSOLE_COMMAND_LATER 2
#define SCRIPTED_KEY 0x41664464
#define WIDEN_VIEW (WM_APP + 0x4466)
#define HIDE_POINTER (WM_APP + 0x4467)

static HRESULT (__cdecl *real_present)(void *swapchain, const RECT *src, const RECT *dst,
                                       HWND override, unsigned int interval, uint32_t flags);
static void *(__cdecl *real_front_buffer)(void *swapchain);
static void *(__cdecl *real_back_buffer)(void *swapchain, UINT index);
static HRESULT (__cdecl *real_blt)(void *context, void *dst, unsigned int dst_index, const RECT *dst_rect,
                                   void *src, unsigned int src_index, const RECT *src_rect,
                                   unsigned int flags, const void *fx, int filter);
static HRESULT (__cdecl *real_swapchain_create)(void *device, struct wined3d_swapchain_desc_start *desc,
                                                void *state_parent, void *parent, const void *parent_ops,
                                                void **swapchain);
static HRESULT (__cdecl *real_get_display_mode)(const void *output, struct wined3d_display_mode_copy *mode,
                                                int *rotation);

static void (__cdecl *real_sampler_state)(void *stateblock, UINT sampler, int state, unsigned int value);
static void *(__cdecl *real_swapchain_device)(void *swapchain);
static void *(__cdecl *real_immediate_context)(void *device);
static void (__cdecl *real_get_viewports)(const void *context, unsigned int *count, struct wined3d_viewport_copy *viewports);
static void (__cdecl *real_set_viewports)(void *context, unsigned int count, const struct wined3d_viewport_copy *viewports);

static HRESULT (__cdecl *real_texture_create)(void *device, const struct wined3d_resource_desc_copy *desc,
                                              unsigned int layers, unsigned int levels, uint32_t flags,
                                              const void *data, void *parent, const void *parent_ops, void **texture);

static void (__cdecl *real_stateblock_viewport)(void *stateblock, const struct wined3d_viewport_copy *viewport);
static HRESULT (__cdecl *real_upload)(void *device, void *buffer, const void *data, unsigned int size,
                                      unsigned int stride, unsigned int *pos);
static HRESULT (__cdecl *real_clear)(void *device, unsigned int count, const RECT *rects, uint32_t flags,
                                     const void *color, float z, unsigned int stencil);
static HRESULT (__cdecl *real_map)(void *resource, unsigned int index, void *map_desc, const void *box, uint32_t flags);
static HRESULT (__cdecl *real_unmap)(void *resource, unsigned int index);
static ULONG (__cdecl *real_texture_decref)(void *texture);
static void *(__cdecl *real_texture_resource)(void *texture);
static void *(__cdecl *real_view_resource)(const void *view);
static HRESULT (__cdecl *real_clear_view)(void *context, void *view, const RECT *rect, unsigned int flags,
                                          const void *color, float depth, unsigned int stencil);
static HRESULT (__cdecl *real_set_views)(void *context, unsigned int start, unsigned int count, void *const *views,
                                         BOOL set_viewport);
static HRESULT (__cdecl *real_get_dc)(void *texture, unsigned int index, HDC *dc);
static HRESULT (__cdecl *real_release_dc)(void *texture, unsigned int index, HDC dc);
static HRESULT (__cdecl *real_update_desc)(void *texture, unsigned int index, void *memory, unsigned int pitch);
static HRESULT (__cdecl *real_device_reset)(void *device, struct wined3d_swapchain_desc_start *desc, const void *mode,
                                            void *callback, BOOL reset_state);
static void (__cdecl *real_texture_pitch)(const void *texture, unsigned int level, unsigned int *row_pitch,
                                          unsigned int *slice_pitch);

/* With DOGFIGHTER_FULL_SIZE the game goes on believing in its own mode, and
   the surfaces it draws its picture into are made as large as the screen.
   The picture is drawn into their top left part, as large as the window is
   at that moment, so a resized window needs no new surfaces. One entry per
   such surface. The shadow is a copy in the game's size, made when the game
   locks the surface, which is how it reads a screenshot. */
static struct full_size_surface
{
    void *texture, *resource, *shadow, *device;
    struct wined3d_resource_desc_copy as_asked;
    UINT width, height;
    uint32_t map_flags;
} full_size_surfaces[8];
static BOOL full_size;
static float picture_scale_x = 1.0f, picture_scale_y = 1.0f;
static void *viewport_stateblock;
static BOOL edges_clamped, drawing_into_picture, shown_picture_is_full_size;
static struct wined3d_viewport_copy game_viewport;
static SIZE swapchain_size;
static void *swapchain_back_buffer;

static FILE *log_file;
static HWND game_window;
static WNDPROC game_proc, next_proc;
static SIZE max_client, mac_screen, fitted_for, modes[32];
static unsigned int mode_count;
static struct wined3d_display_mode_copy game_mode;
static BOOL mode_set, dinput_wants_mouse, mouse_free, widen_view, test_on_right_display, test_leaves_mouse, pointer_hidden, deep_z, keep_shape, test_saves_full_size;
static RECT test_display, given_area;
static void *front_swapchain, *front_texture;
static DWORD front_thread;
static unsigned int anisotropy, texture_limit, edge_samples, frames_a_second;
static BOOL match_pointer;
static BOOL test_notes_draws;
/* On Mach9 the game ends with exit code -1 when a mission is started while its
   intro videos play. It makes its first depth surface for the main menu, so
   console commands wait for one. */
static BOOL no_depth_surface_yet;
/* Test runs only: how many console commands still have to run before the
   player's keys and clicks reach the game. A mission started by hand while a
   scripted start is on its way crashes the game. */
static volatile LONG commands_before_input, inputs_kept;
static BOOL scripted_char_owed;
/* A command the game window did not answer within windiag's 5 seconds never
   counts, so the wait also ends this many seconds after the game could first
   take commands. */
static DWORD input_wait_limit;
static char test_shot_on[64];
static LONG test_shot_in;
static volatile LONG flips, direct_draws, gdi_draws, unscaled_draws, to_announce, dinput_clips, dinput_moves;

static void say(const char *fmt, ...)
{
    va_list args;
    if (!log_file) return;
    va_start(args, fmt);
    fprintf(log_file, "focushook: ");
    vfprintf(log_file, fmt, args);
    fprintf(log_file, "\n");
    fflush(log_file);
    va_end(args);
}

static SIZE env_size(const char *name)
{
    char text[32];
    SIZE size = { 0, 0 };
    if (GetEnvironmentVariableA(name, text, sizeof(text)))
        sscanf(text, "%ldx%ld", &size.cx, &size.cy);
    return size;
}

static void read_mode_list(void)
{
    char text[512], *next = text;
    int used;

    if (!GetEnvironmentVariableA("DOGFIGHTER_MODES", text, sizeof(text))) return;
    while (mode_count < ARRAYSIZE(modes)
           && sscanf(next, "%ldx%ld%n", &modes[mode_count].cx, &modes[mode_count].cy, &used) == 2)
    {
        mode_count++;
        next += used;
    }
}

static BOOL picture_target(RECT *client)
{
    return game_window && GetClientRect(game_window, client) && client->right > 0 && client->bottom > 0;
}

static SIZE fitted_client(void)
{
    SIZE size = { max_client.cx, 0 };

    if (!game_mode.width || !game_mode.height) return size;
    size.cy = max_client.cx * game_mode.height / game_mode.width;
    if (size.cy > max_client.cy)
    {
        size.cy = max_client.cy;
        size.cx = max_client.cy * game_mode.width / game_mode.height;
    }
    return size;
}

static BOOL full_size_of_picture(UINT width, UINT height, SIZE *full)
{
    *full = swapchain_size.cx && swapchain_size.cy ? swapchain_size : fitted_client();
    return full_size && mode_set && width == game_mode.width && height == game_mode.height
           && full->cx > (LONG)width && full->cy > (LONG)height;
}

static struct full_size_surface *full_size_surface(const void *texture_or_resource)
{
    if (!texture_or_resource) return NULL;
    for (unsigned int i = 0; i < ARRAYSIZE(full_size_surfaces); i++)
        if (full_size_surfaces[i].texture == texture_or_resource || full_size_surfaces[i].resource == texture_or_resource)
            return &full_size_surfaces[i];
    return NULL;
}

static BOOL full_size_surface_made(void)
{
    for (unsigned int i = 0; i < ARRAYSIZE(full_size_surfaces); i++)
        if (full_size_surfaces[i].texture) return TRUE;
    return FALSE;
}

static BOOL picture_is_scaled(void)
{
    return picture_scale_x != 1.0f || picture_scale_y != 1.0f;
}

static void scale_viewport(const struct wined3d_viewport_copy *viewport)
{
    struct wined3d_viewport_copy full = *viewport;

    full.x *= picture_scale_x;
    full.width *= picture_scale_x;
    full.y *= picture_scale_y;
    full.height *= picture_scale_y;
    real_stateblock_viewport(viewport_stateblock, &full);
}

/* The picture is drawn as large as the window's client area, at most as large
   as the surfaces. Called between two frames, so one frame has one scale. */
static void scale_picture_to(LONG width, LONG height)
{
    struct full_size_surface *any = NULL;
    float x, y;

    for (unsigned int i = 0; !any && i < ARRAYSIZE(full_size_surfaces); i++)
        if (full_size_surfaces[i].texture) any = &full_size_surfaces[i];
    if (!any || !game_mode.width || !game_mode.height || width <= 0 || height <= 0) return;
    if (width > (LONG)any->width) width = any->width;
    if (height > (LONG)any->height) height = any->height;
    x = (float)width / game_mode.width;
    y = (float)height / game_mode.height;
    if (x == picture_scale_x && y == picture_scale_y) return;
    picture_scale_x = x;
    picture_scale_y = y;
    if (viewport_stateblock) scale_viewport(&game_viewport);
    say("the picture is drawn %ldx%ld now, %.3f by %.3f times the game's %ux%u", width, height, x, y,
        game_mode.width, game_mode.height);
}

static const RECT *scaled_rect(const RECT *rect, RECT *scaled)
{
    if (!rect) return NULL;
    SetRect(scaled, lroundf(rect->left * picture_scale_x), lroundf(rect->top * picture_scale_y),
            lroundf(rect->right * picture_scale_x), lroundf(rect->bottom * picture_scale_y));
    return scaled;
}

static void tell_helper_about_picture(void)
{
    static LONG told;
    HANDLE picture;

    if (InterlockedExchange(&told, 1)) return;
    if (!(picture = OpenEventA(EVENT_MODIFY_STATE, FALSE, "DogfighterFirstPicture"))) return;
    SetEvent(picture);
    CloseHandle(picture);
}

static void count_scaled(volatile LONG *counter, const char *path, const RECT *client)
{
    InterlockedIncrement(counter);
    if (InterlockedDecrement(&to_announce) >= 0)
        say("%s: picture %ux%u drawn into client area %ldx%ld on thread %04lx", path,
            game_mode.width, game_mode.height, client->right, client->bottom, GetCurrentThreadId());
}

/* After the window gets a new size, the OpenGL viewport is the size of the
   window, without wined3d having asked for it. wined3d sets the viewport only
   when the game changes it, which is once. The game's picture is then drawn at
   window size into a surface of the game's size: only its top left part fits,
   and that part is what gets stretched over the window. Handing wined3d its own
   viewport again makes it set the OpenGL one before the next frame is drawn. */
static void set_viewport_again(void *swapchain)
{
    struct wined3d_viewport_copy viewports[16];
    unsigned int count = ARRAYSIZE(viewports);
    void *context;

    if (!real_set_viewports || !(context = real_immediate_context(real_swapchain_device(swapchain)))) return;
    real_get_viewports(context, &count, viewports);
    if (count && count <= ARRAYSIZE(viewports)) real_set_viewports(context, count, viewports);
}

/* --fps=N. Each frame is due a fixed time after the one before, not after
   the end of the last wait, so a wait that runs long is made up for and the
   rate is N, not a little under it. */
static void wait_for_next_frame(void)
{
    static LARGE_INTEGER a_second, due;
    LARGE_INTEGER now;
    LONGLONG a_frame;

    if (!frames_a_second) return;
    if (!a_second.QuadPart) QueryPerformanceFrequency(&a_second);
    a_frame = a_second.QuadPart / frames_a_second;
    QueryPerformanceCounter(&now);
    if (now.QuadPart < due.QuadPart)
        Sleep((DWORD)(((due.QuadPart - now.QuadPart) * 1000 + a_second.QuadPart - 1) / a_second.QuadPart));
    else if (now.QuadPart - due.QuadPart > a_frame) due = now;
    due.QuadPart += a_frame;
}

static void read_pointer_step(void);

static HRESULT __cdecl scaled_present(void *swapchain, const RECT *src, const RECT *dst,
                                      HWND override, unsigned int interval, uint32_t flags)
{
    RECT client, full;
    HRESULT hr;

    if (picture_target(&client))
    {
        count_scaled(&flips, "flip", &client);
        dst = &client;
    }
    if (picture_is_scaled() && shown_picture_is_full_size) src = scaled_rect(src, &full);
    read_pointer_step();
    wait_for_next_frame();
    hr = real_present(swapchain, src, dst, override, interval, flags);
    if (full_size && dst == &client) scale_picture_to(client.right, client.bottom);
    set_viewport_again(swapchain);
    tell_helper_about_picture();
    return hr;
}

static void *__cdecl noted_front_buffer(void *swapchain)
{
    front_swapchain = swapchain;
    front_texture = real_front_buffer(swapchain);
    front_thread = GetCurrentThreadId();
    return front_texture;
}

static void save_test_picture(void *resource, unsigned int index, int format, LONG width, LONG height);
static void save_full_size_picture(struct full_size_surface *entry, unsigned int index);

static void *__cdecl noted_back_buffer(void *swapchain, UINT index)
{
    void *texture = real_back_buffer(swapchain, index);

    if (!index) swapchain_back_buffer = texture;
    return texture;
}

static HRESULT __cdecl scaled_blt(void *context, void *dst, unsigned int dst_index, const RECT *dst_rect,
                                  void *src, unsigned int src_index, const RECT *src_rect,
                                  unsigned int flags, const void *fx, int filter)
{
    void *back;
    RECT client, full_src, full_dst;
    HRESULT hr;

    if (picture_is_scaled())
    {
        BOOL from_picture = full_size_surface(src) != NULL;

        if (full_size_surface(dst) || (from_picture && (dst == swapchain_back_buffer || dst == front_texture)))
            dst_rect = scaled_rect(dst_rect, &full_dst);
        if (from_picture) src_rect = scaled_rect(src_rect, &full_src);
    }
    if (dst && (dst == swapchain_back_buffer || dst == front_texture)) shown_picture_is_full_size = full_size_surface(src) != NULL;
    if (test_shot_in > 0 && dst && dst == swapchain_back_buffer && shown_picture_is_full_size && !--test_shot_in)
        save_full_size_picture(full_size_surface(src), src_index);
    if (test_saves_full_size && dst && dst == swapchain_back_buffer && !shown_picture_is_full_size && src_rect)
    {
        static int plain;

        if (++plain == 40)
            save_test_picture(real_texture_resource(src), src_index, game_mode.format_id, src_rect->right, src_rect->bottom);
    }
    if (!dst || dst != front_texture || front_thread != GetCurrentThreadId())
        return real_blt(context, dst, dst_index, dst_rect, src, src_index, src_rect, flags, fx, filter);

    front_texture = NULL;
    if (!picture_target(&client))
        return real_blt(context, dst, dst_index, dst_rect, src, src_index, src_rect, flags, fx, filter);
    if (!(back = real_back_buffer(front_swapchain, 0)))
    {
        InterlockedIncrement(&unscaled_draws);
        return real_blt(context, dst, dst_index, dst_rect, src, src_index, src_rect, flags, fx, filter);
    }
    hr = real_blt(context, back, 0, dst_rect, src, src_index, src_rect, flags, fx, filter);
    if (SUCCEEDED(hr))
    {
        count_scaled(&direct_draws, "direct draw", &client);
        wait_for_next_frame();
        real_present(front_swapchain, NULL, &client, NULL, 0, 0);
        tell_helper_about_picture();
    }
    return hr;
}

static BOOL WINAPI counted_bitblt(HDC dst, int x, int y, int w, int h, HDC src, int sx, int sy, DWORD rop)
{
    if (InterlockedIncrement(&gdi_draws) <= 3)
        say("ddraw copied %dx%d through GDI; that is not scaled", w, h);
    return BitBlt(dst, x, y, w, h, src, sx, sy, rop);
}

static HWND WINAPI game_is_foreground(void)
{
    return game_window ? game_window : GetForegroundWindow();
}

static HRESULT __cdecl windowed_swapchain_create(void *device, struct wined3d_swapchain_desc_start *desc,
                                                 void *state_parent, void *parent, const void *parent_ops,
                                                 void **swapchain)
{
    say("ddraw asked for a %s swapchain of %ux%u on thread %04lx; wined3d gets a windowed one",
        desc->windowed ? "windowed" : "fullscreen", desc->backbuffer_width, desc->backbuffer_height, GetCurrentThreadId());
    desc->windowed = TRUE;
    swapchain_size.cx = desc->backbuffer_width;
    swapchain_size.cy = desc->backbuffer_height;
    return real_swapchain_create(device, desc, state_parent, parent, parent_ops, swapchain);
}

/* ddraw makes the swapchain's back buffer the size of the game's mode when
   the game makes its screen surface. The full-size picture is copied there
   before it is shown, so the back buffer has to hold it. */
static HRESULT __cdecl full_size_device_reset(void *device, struct wined3d_swapchain_desc_start *desc, const void *mode,
                                              void *callback, BOOL reset_state)
{
    SIZE full;

    if (desc && full_size_of_picture(desc->backbuffer_width, desc->backbuffer_height, &full))
    {
        desc->backbuffer_width = full.cx;
        desc->backbuffer_height = full.cy;
    }
    return real_device_reset(device, desc, mode, callback, reset_state);
}

static HRESULT __cdecl kept_set_display_mode(void *output, const struct wined3d_display_mode_copy *wanted)
{
    if (!wanted)
    {
        mode_set = FALSE;
        return S_OK;
    }
    game_mode = *wanted;
    mode_set = TRUE;
    picture_scale_x = picture_scale_y = 1.0f;
    viewport_stateblock = NULL;
    edges_clamped = drawing_into_picture = shown_picture_is_full_size = FALSE;
    InterlockedExchange(&to_announce, 4);
    say("the game asked for display mode %ux%u, format %d; the Mac keeps its mode and the picture is scaled",
        wanted->width, wanted->height, wanted->format_id);
    return S_OK;
}

static HRESULT __cdecl kept_restore_display_modes(void *wined3d)
{
    mode_set = FALSE;
    return S_OK;
}

static HRESULT __cdecl faked_get_display_mode(const void *output, struct wined3d_display_mode_copy *mode,
                                              int *rotation)
{
    HRESULT hr = real_get_display_mode(output, mode, rotation);

    if (SUCCEEDED(hr) && mode && mode_set)
    {
        mode->width = game_mode.width;
        mode->height = game_mode.height;
        mode->format_id = game_mode.format_id;
        if (game_mode.refresh_rate) mode->refresh_rate = game_mode.refresh_rate;
    }
    return hr;
}

static HRESULT __cdecl listed_mode(void *output, int format_id, int ordering, unsigned int index,
                                   struct wined3d_display_mode_copy *mode, int cached)
{
    if (index >= mode_count) return WINED3DERR_INVALIDCALL;
    if (FAILED(real_get_display_mode(output, mode, NULL))) memset(mode, 0, sizeof(*mode));
    mode->width = modes[index].cx;
    mode->height = modes[index].cy;
    mode->format_id = format_id;
    if (!mode->refresh_rate) mode->refresh_rate = 60;
    return S_OK;
}

/* The game asks for linear filtering with the nearest mipmap, which blurs the
   ground towards the horizon. Where it asks for that, it gets anisotropic
   filtering blended between mipmaps. Point filtering is left alone: the game
   picks it on purpose. The numbers are wined3d's sampler states and filters. */
static void __cdecl sharper_sampler_state(void *stateblock, UINT sampler, int state, unsigned int value)
{
    enum { MIN_FILTER = 6, MIP_FILTER = 7, MAX_ANISOTROPY = 10, POINT = 1, LINEAR = 2, ANISOTROPIC = 3 };

    if (state == MIN_FILTER && value == LINEAR)
    {
        real_sampler_state(stateblock, sampler, MAX_ANISOTROPY, anisotropy);
        value = ANISOTROPIC;
    }
    else if (state == MIP_FILTER && value == POINT) value = LINEAR;
    else if (state == MAX_ANISOTROPY) value = anisotropy;
    real_sampler_state(stateblock, sampler, state, value);
}

static void __stdcall shadow_destroyed(void *parent)
{
}

/* ddraw has no multisampling, so wined3d's SampleCount setting only reaches
   the swapchain, which the game never draws its 3D picture into. The picture
   is drawn into ddraw's own surfaces. Those that can be drawn into, and the
   depth buffers that go with them, are made multisampled here; wined3d then
   resolves them whenever ddraw copies, locks or shows one. Colour and depth
   must have the same sample count, so a refused count is halved for the rest.
   The numbers are wined3d's resource types, bind flags and format ids. */
static HRESULT __cdecl better_texture_create(void *device, const struct wined3d_resource_desc_copy *desc,
                                             unsigned int layers, unsigned int levels, uint32_t flags,
                                             const void *data, void *parent, const void *parent_ops, void **texture)
{
    enum { TEXTURE_2D = 3, RENDER_TARGET = 0x20, DEPTH_STENCIL = 0x40, D16 = 85, X8D24 = 24 };
    static void (__stdcall *const shadow_ops)(void *) = shadow_destroyed;
    static LONG said;
    struct wined3d_resource_desc_copy better;
    struct full_size_surface *entry;
    RECT client;
    BOOL depth = (desc->bind_flags & DEPTH_STENCIL) != 0;
    BOOL the_picture = mode_set && desc->width == game_mode.width && desc->height == game_mode.height;
    SIZE full;
    HRESULT hr;

    if (depth) no_depth_surface_yet = FALSE;
    if (desc->resource_type != TEXTURE_2D || desc->multisample_type || layers != 1 || levels != 1 || data
        || !(desc->bind_flags & (RENDER_TARGET | DEPTH_STENCIL)))
    {
        if (full_size && the_picture && desc->resource_type == TEXTURE_2D && InterlockedIncrement(&said) <= 24)
            say("a surface of the picture's size that cannot be drawn into, format %d, is left at %ux%u",
                desc->format, desc->width, desc->height);
        return real_texture_create(device, desc, layers, levels, flags, data, parent, parent_ops, texture);
    }

    the_picture = full_size_of_picture(desc->width, desc->height, &full);
    for (;;)
    {
        better = *desc;
        if (edge_samples > 1) better.multisample_type = edge_samples;
        if (deep_z && depth && desc->format == D16) better.format = X8D24;
        if (the_picture)
        {
            better.width = full.cx;
            better.height = full.cy;
        }
        hr = real_texture_create(device, &better, layers, levels, flags, data, parent, parent_ops, texture);
        if (InterlockedIncrement(&said) <= 24 || FAILED(hr))
            say("%s surface %ux%u, format %d made as %ux%u, format %d with %d samples: %s", depth ? "depth" : "picture",
                desc->width, desc->height, desc->format, better.width, better.height, better.format,
                better.multisample_type, SUCCEEDED(hr) ? "done" : "refused");
        if (SUCCEEDED(hr) || !memcmp(&better, desc, sizeof(better))) break;
        if (edge_samples > 1) edge_samples /= 2;
        else if (deep_z) deep_z = FALSE;
        else the_picture = full_size = FALSE;
    }
    if (FAILED(hr) || !the_picture) return hr;

    if (!(entry = full_size_surface(*texture))) entry = full_size_surface(NULL);
    for (unsigned int i = 0; !entry && i < ARRAYSIZE(full_size_surfaces); i++)
        if (!full_size_surfaces[i].texture) entry = &full_size_surfaces[i];
    if (!entry)
    {
        say("more than %u surfaces of the picture's size; this one cannot be locked or copied right",
            (unsigned int)ARRAYSIZE(full_size_surfaces));
        return hr;
    }
    memset(entry, 0, sizeof(*entry));
    entry->texture = *texture;
    entry->resource = real_texture_resource(*texture);
    entry->device = device;
    entry->as_asked = *desc;
    entry->width = better.width;
    entry->height = better.height;
    full = fitted_client();
    if (picture_target(&client) && fitted_for.cx == (LONG)game_mode.width && fitted_for.cy == (LONG)game_mode.height)
    {
        full.cx = client.right;
        full.cy = client.bottom;
    }
    scale_picture_to(full.cx, full.cy);
    if (!depth && FAILED(real_texture_create(device, desc, 1, 1, 0, NULL, NULL, &shadow_ops, &entry->shadow)))
    {
        entry->shadow = NULL;
        say("no copy of the picture in the game's size could be made; a screenshot will be wrong");
    }
    return hr;
}

/* ddraw tells the game the row length of a locked surface from this. The game
   must get that of the copy in its own size, which is what it is handed. */
static void __cdecl shadow_pitch(const void *texture, unsigned int level, unsigned int *row_pitch, unsigned int *slice_pitch)
{
    struct full_size_surface *entry = full_size_surface(texture);

    real_texture_pitch(entry && entry->shadow ? entry->shadow : texture, level, row_pitch, slice_pitch);
}

static ULONG __cdecl noted_texture_decref(void *texture)
{
    struct full_size_surface *entry = full_size_surface(texture);
    ULONG left = real_texture_decref(texture);

    if (!left && entry && entry->texture == texture)
    {
        if (entry->shadow) real_texture_decref(entry->shadow);
        memset(entry, 0, sizeof(*entry));
    }
    return left;
}

/* The game transforms every vertex itself and draws with one vertex layout:
   a position in pixels of its own mode, a colour and three texture
   coordinates, 44 bytes. So moving those positions to the larger surface
   scales the 3D scene, the HUD, the menus and the letters alike. A pixel's
   middle is at a whole number, hence the half pixel.
   The game never sets how a texture goes on past its edge, so it repeats.
   An enlarged menu tile then mixes its last row with its first one, which
   shows as a thin line between tiles. Flat pictures, drawn with a depth
   factor of 1 and the whole texture, get an edge that does not repeat. */
static HRESULT __cdecl scaled_upload(void *device, void *buffer, const void *data, unsigned int size,
                                     unsigned int stride, unsigned int *pos)
{
    enum { GAME_VERTEX = 44, ADDRESS_U = 1, ADDRESS_V = 2, WRAP = 1, CLAMP = 3 };
    static float *moved;
    static unsigned int room;
    static BOOL said;
    BOOL flat = TRUE;

    if (!picture_is_scaled() || !drawing_into_picture || !data || stride < 4)
        return real_upload(device, buffer, data, size, stride, pos);
    if (stride != GAME_VERTEX)
    {
        if (!said) say("vertices of %u bytes are not the game's known layout; they are not scaled", stride);
        said = TRUE;
        return real_upload(device, buffer, data, size, stride, pos);
    }
    if (size > room)
    {
        free(moved);
        room = size * 2;
        if (!(moved = malloc(room)))
        {
            room = 0;
            return real_upload(device, buffer, data, size, stride, pos);
        }
    }
    memcpy(moved, data, size);
    for (unsigned int at = 0; at + GAME_VERTEX <= size; at += GAME_VERTEX)
    {
        float *vertex = (float *)((BYTE *)moved + at);
        vertex[0] = (vertex[0] + 0.5f) * picture_scale_x - 0.5f;
        vertex[1] = (vertex[1] + 0.5f) * picture_scale_y - 0.5f;
        if (vertex[3] != 1.0f || vertex[5] < 0.0f || vertex[5] > 1.0f || vertex[6] < 0.0f || vertex[6] > 1.0f) flat = FALSE;
    }
    if (flat != edges_clamped && viewport_stateblock && real_sampler_state)
    {
        edges_clamped = flat;
        real_sampler_state(viewport_stateblock, 0, ADDRESS_U, flat ? CLAMP : WRAP);
        real_sampler_state(viewport_stateblock, 0, ADDRESS_V, flat ? CLAMP : WRAP);
    }
    return real_upload(device, buffer, moved, size, stride, pos);
}

/* ddraw also hands wined3d's own viewport back, which is already full size. */
static void __cdecl scaled_stateblock_viewport(void *stateblock, const struct wined3d_viewport_copy *viewport)
{
    if (!full_size_surface_made() || !drawing_into_picture || !viewport || viewport->x + viewport->width > game_mode.width
        || viewport->y + viewport->height > game_mode.height)
    {
        real_stateblock_viewport(stateblock, viewport);
        return;
    }
    viewport_stateblock = stateblock;
    game_viewport = *viewport;
    scale_viewport(viewport);
}

/* The game's positions are only moved while it draws into one of the
   full-size surfaces. A smaller target of its own, such as a texture it draws
   a picture into, keeps the game's numbers. */
static HRESULT __cdecl noted_set_views(void *context, unsigned int start, unsigned int count, void *const *views,
                                       BOOL set_viewport)
{
    static int said;

    if (!start && count && views)
    {
        BOOL picture = views[0] && full_size_surface(real_view_resource(views[0])) != NULL;

        if (picture != drawing_into_picture && full_size_surface_made() && said++ < 20)
            say("the game now draws into %s", picture ? "the full-size picture" : "a surface of its own, which is not enlarged");
        drawing_into_picture = picture;
    }
    return real_set_views(context, start, count, views, set_viewport);
}

static HRESULT __cdecl scaled_clear_view(void *context, void *view, const RECT *rect, unsigned int flags,
                                         const void *color, float depth, unsigned int stencil)
{
    static BOOL said;
    RECT full;

    if (picture_is_scaled() && rect && view && full_size_surface(real_view_resource(view)))
    {
        if (!said) say("a fill of %ld,%ld to %ld,%ld of the picture is scaled", rect->left, rect->top, rect->right, rect->bottom);
        said = TRUE;
        rect = scaled_rect(rect, &full);
    }
    return real_clear_view(context, view, rect, flags, color, depth, stencil);
}

static HRESULT __cdecl scaled_clear(void *device, unsigned int count, const RECT *rects, uint32_t flags,
                                    const void *color, float z, unsigned int stencil)
{
    RECT full[16];

    if (!picture_is_scaled() || !count || !rects || count > ARRAYSIZE(full))
        return real_clear(device, count, rects, flags, color, z, stencil);
    for (unsigned int i = 0; i < count; i++) scaled_rect(&rects[i], &full[i]);
    return real_clear(device, count, full, flags, color, z, stencil);
}

static void save_test_picture(void *resource, unsigned int index, int format, LONG width, LONG height)
{
    enum { MAP_READ = 0x80000000u, B5G6R5 = 116, B8G8R8X8 = 119 };
    static int saved;
    struct { UINT row_pitch, slice_pitch; void *data; } map = { 0 };
    RECT drawn = { 0, 0, width, height };
    BYTE header[18] = { 0, 0, 2, [16] = 24, 0x20 };
    char name[64];
    BYTE *row;
    FILE *file;

    header[12] = drawn.right & 0xff;
    header[13] = drawn.right >> 8;
    header[14] = drawn.bottom & 0xff;
    header[15] = drawn.bottom >> 8;
    if (format != B5G6R5 && format != B8G8R8X8) return;
    if (FAILED(real_map(resource, index, &map, NULL, MAP_READ)) || !map.data) return;
    snprintf(name, sizeof(name), "C:\\dogfighter-full-size-%d.tga", saved++);
    if ((file = fopen(name, "wb")) && (row = malloc(drawn.right * 3)))
    {
        fwrite(header, 1, sizeof(header), file);
        for (LONG y = 0; y < drawn.bottom; y++)
        {
            const BYTE *from = (const BYTE *)map.data + y * map.row_pitch;

            for (LONG x = 0; x < drawn.right; x++)
            {
                if (format == B8G8R8X8) memcpy(row + x * 3, from + x * 4, 3);
                else
                {
                    WORD pixel = from[x * 2] | from[x * 2 + 1] << 8;
                    row[x * 3] = (pixel & 0x1f) << 3;
                    row[x * 3 + 1] = (pixel >> 5 & 0x3f) << 2;
                    row[x * 3 + 2] = (pixel >> 11) << 3;
                }
            }
            fwrite(row, 1, drawn.right * 3, file);
        }
        free(row);
        say("test run: the picture, %ldx%ld, saved as %s", drawn.right, drawn.bottom, name);
    }
    if (file) fclose(file);
    real_unmap(resource, index);
}

static void save_full_size_picture(struct full_size_surface *entry, unsigned int index)
{
    RECT asked = { 0, 0, entry->as_asked.width, entry->as_asked.height }, drawn;

    scaled_rect(&asked, &drawn);
    save_test_picture(entry->resource, index, entry->as_asked.format, drawn.right, drawn.bottom);
}

/* ddraw also takes that row length when it gives a surface memory of its
   own. There the full-size surface needs its real one. */
static HRESULT __cdecl full_size_update_desc(void *texture, unsigned int index, void *memory, unsigned int pitch)
{
    struct full_size_surface *entry = full_size_surface(texture);
    unsigned int slice_pitch;

    if (entry && entry->shadow) real_texture_pitch(texture, index, &pitch, &slice_pitch);
    return real_update_desc(texture, index, memory, pitch);
}

static HRESULT __cdecl shadow_map(void *resource, unsigned int index, void *map_desc, const void *box, uint32_t flags)
{
    enum { LINEAR = 2 };
    struct full_size_surface *entry = full_size_surface(resource);
    RECT asked, full;

    if (!entry || entry->resource != resource || !entry->shadow) return real_map(resource, index, map_desc, box, flags);
    SetRect(&asked, 0, 0, entry->as_asked.width, entry->as_asked.height);
    scaled_rect(&asked, &full);
    real_blt(real_immediate_context(entry->device), entry->shadow, index, &asked, entry->texture, index, &full, 0, NULL, LINEAR);
    entry->map_flags = flags;
    if (test_saves_full_size) save_full_size_picture(entry, index);
    return real_map(real_texture_resource(entry->shadow), index, map_desc, box, flags);
}

/* The game writes its console and some messages with Windows text calls
   on the picture, and those know only the game's size. They get the copy in
   the game's size; it is scaled back over the picture when they are done,
   so the whole picture is as soft as a stretched one while such text shows. */
static HRESULT __cdecl shadow_get_dc(void *texture, unsigned int index, HDC *dc)
{
    enum { LINEAR = 2 };
    static BOOL said;
    struct full_size_surface *entry = full_size_surface(texture);
    RECT asked, full;

    if (!entry || entry->texture != texture || !entry->shadow) return real_get_dc(texture, index, dc);
    if (!said) say("the game draws on the picture with Windows drawing calls; they get a copy in the game's size");
    said = TRUE;
    SetRect(&asked, 0, 0, entry->as_asked.width, entry->as_asked.height);
    scaled_rect(&asked, &full);
    real_blt(real_immediate_context(entry->device), entry->shadow, index, &asked, entry->texture, index, &full, 0, NULL, LINEAR);
    return real_get_dc(entry->shadow, index, dc);
}

static HRESULT __cdecl shadow_release_dc(void *texture, unsigned int index, HDC dc)
{
    enum { LINEAR = 2 };
    struct full_size_surface *entry = full_size_surface(texture);
    RECT asked, full;
    HRESULT hr;

    if (!entry || entry->texture != texture || !entry->shadow) return real_release_dc(texture, index, dc);
    hr = real_release_dc(entry->shadow, index, dc);
    SetRect(&asked, 0, 0, entry->as_asked.width, entry->as_asked.height);
    scaled_rect(&asked, &full);
    real_blt(real_immediate_context(entry->device), entry->texture, index, &full, entry->shadow, index, &asked, 0, NULL, LINEAR);
    return hr;
}

static HRESULT __cdecl shadow_unmap(void *resource, unsigned int index)
{
    enum { MAP_WRITE = 0x40000000, LINEAR = 2 };
    struct full_size_surface *entry = full_size_surface(resource);
    HRESULT hr;

    if (!entry || entry->resource != resource || !entry->shadow) return real_unmap(resource, index);
    hr = real_unmap(real_texture_resource(entry->shadow), index);
    if (entry->map_flags & MAP_WRITE)
    {
        RECT asked = { 0, 0, entry->as_asked.width, entry->as_asked.height }, full;

        scaled_rect(&asked, &full);
        real_blt(real_immediate_context(entry->device), entry->texture, index, &full, entry->shadow, index, &asked, 0, NULL, LINEAR);
    }
    return hr;
}

static BOOL WINAPI ddraw_clip_cursor(const RECT *rect)
{
    return TRUE;
}

static BOOL WINAPI dinput_clip_cursor(const RECT *rect)
{
    dinput_wants_mouse = rect != NULL;
    if (rect) InterlockedIncrement(&dinput_clips);
    return TRUE;
}

/* DirectInput hides the pointer when the game takes the mouse. Wine's Mac
   driver passes that on to macOS as one [NSCursor hide], and on this setup the
   pointer stays on the screen all the same. So DirectInput's call is dropped,
   the Windows cursor stays "shown", and the hook gives it an empty picture.
   The picture is an animated cursor of two empty frames on purpose: the Mac
   driver sets a cursor picture only once, but for an animated one it sets the
   next frame again every 100 ms, so macOS cannot keep its arrow. */
static int WINAPI dinput_show_cursor(BOOL show)
{
    return show ? 0 : -1;
}

static HCURSOR empty_cursor(void)
{
    enum { SIDE = 32, FRAMES = 2, PIXELS = SIDE * SIDE * 4, MASK = SIDE * SIDE / 8,
           FRAME = 22 + sizeof(BITMAPINFOHEADER) + PIXELS + MASK, LIST = 4 + FRAMES * (8 + FRAME) };
    static const BYTE and_mask[MASK * 2] = { [0 ... MASK - 1] = 0xff };
    static const BYTE xor_mask[MASK] = { 0 };
    static HCURSOR cursor;
    DWORD anih[] = { 36, FRAMES, FRAMES, 0, 0, 0, 0, 6, 1 };
    BITMAPINFOHEADER bitmap = { sizeof(bitmap), SIDE, SIDE * 2, 1, 32 };
    WORD dir[] = { 0, 2, 1 };
    DWORD entry[] = { SIDE | SIDE << 8, 0, sizeof(bitmap) + PIXELS + MASK, 22 };
    DWORD riff[] = { 0x46464952, 4 + 8 + sizeof(anih) + 8 + LIST, 0x4e4f4341, 0x68696e61, sizeof(anih) };
    DWORD list[] = { 0x5453494c, LIST, 0x6d617266 }, icon[] = { 0x6e6f6369, FRAME };
    BYTE *file, *at;

    if (cursor) return cursor;
    if ((file = at = calloc(1, sizeof(riff) + sizeof(anih) + sizeof(list) + FRAMES * (8 + FRAME))))
    {
        memcpy(at, riff, sizeof(riff)); at += sizeof(riff);
        memcpy(at, anih, sizeof(anih)); at += sizeof(anih);
        memcpy(at, list, sizeof(list)); at += sizeof(list);
        for (int i = 0; i < FRAMES; i++)
        {
            memcpy(at, icon, sizeof(icon)); at += sizeof(icon);
            memcpy(at, dir, sizeof(dir)); at += sizeof(dir);
            memcpy(at, entry, sizeof(entry)); at += sizeof(entry);
            memcpy(at, &bitmap, sizeof(bitmap)); at += sizeof(bitmap) + PIXELS;
            memset(at, 0xff, MASK); at += MASK;
        }
        cursor = (HCURSOR)CreateIconFromResourceEx(file, at - file, FALSE, 0x00030000, 0, 0, 0);
        free(file);
    }
    if (!cursor)
    {
        say("no animated empty cursor; using a plain one, which the Mac driver sets only once");
        cursor = CreateCursor(GetModuleHandleA(NULL), 0, 0, SIDE, SIDE, and_mask, xor_mask);
    }
    else
    {
        HCURSOR (WINAPI *frame_info)(HCURSOR, DWORD, DWORD, DWORD *, DWORD *) =
            (void *)GetProcAddress(GetModuleHandleA("user32.dll"), "GetCursorFrameInfo");
        DWORD rate = 0, steps = 0;

        if (frame_info) frame_info(cursor, 0, 0, &rate, &steps);
        say("empty cursor %p made: %lu frames, a new one every %lu/60 of a second", (void *)cursor, steps, rate);
    }
    return cursor;
}

static void hide_pointer(BOOL hide)
{
    CURSORINFO info = { sizeof(info) };
    SYSTEMTIME at;

    if (hide == pointer_hidden) return;
    pointer_hidden = hide;
    SetCursor(hide ? empty_cursor() : LoadCursorA(NULL, (const char *)IDC_ARROW));
    GetCursorInfo(&info);
    GetLocalTime(&at);
    say("%02u:%02u:%02u the system pointer is %s; Windows reports its cursor %s with handle %p, the empty cursor is %p",
        at.wHour, at.wMinute, at.wSecond, hide ? "given an empty picture, the mouse belongs to the game" : "the arrow again",
        info.flags & CURSOR_SHOWING ? "shown" : "hidden", (void *)info.hCursor, (void *)empty_cursor());
}

static void hide_pointer_while_held(BOOL held)
{
    static BOOL asked;

    if (held == asked || !next_proc) return;
    asked = held;
    PostMessageA(game_window, HIDE_POINTER, held, 0);
}

static BOOL WINAPI dinput_set_cursor_pos(int x, int y)
{
    InterlockedIncrement(&dinput_moves);
    return SetCursorPos(x, y);
}

/* The game moves its menu pointer by mouse_sensitivity / 1000 times the
   square of each mouse move, in pixels of its own picture. It squares what
   DirectInput hands it, and that is counted in the window's pixels: twice the
   number on a Retina screen, so four times the way, in a picture that is no
   larger on the screen. The slider cannot undo a square.
   So while the game shows its pointer, each move is replaced by the one whose
   square takes the pointer as far over the picture as the Mac pointer went
   over the window. That is at the game's own mouse_sensitivity, 100; the
   slider makes the way longer or shorter in proportion. What rounding leaves
   over goes into the next move. In a flight the game hides its pointer, and
   the moves stay as they are.
   Wine's DirectInput takes a move as the place in the event minus the place
   of the cursor, so the event gets another place. Only a build whose code
   does that square is touched. */
enum { GAME_SENSITIVITY = 100 };
static HOOKPROC dinput_mouse_hook, dinput_key_hook;
static float pointer_step, pointer_speed;
static volatile LONG moves_seen[2], moves_given[2];
static void *(__cdecl *game_main)(void);
static unsigned char (__thiscall *game_pointer_shown)(void *main);

static void read_pointer_step(void)
{
    enum { MOVE_CODE = 0x45f81, STEP_FOR_ONE = 0x7dc60 };
    static const BYTE before[] = { 0xdb, 0x44, 0x24, 0x10, 0x8b, 0x47, 0x10, 0x85, 0xc0, 0x89, 0x44, 0x24, 0x10, 0xd8, 0x0d };
    static const BYTE after[] = { 0xdb, 0x44, 0x24, 0x10, 0xd9, 0xc0, 0xd8, 0xc9, 0xde, 0xca, 0xdd, 0xd8 };
    static void *(__thiscall *get_console)(void *main);
    static int (__thiscall *get_value)(void *console, const char *name);
    static unsigned int frames;
    static int said_for = -1, said;
    static BOOL unknown;
    BYTE *engine;
    void *main, *console;
    int sensitivity;

    if (!match_pointer || unknown || frames++ % 32) return;
    if (!get_value)
    {
        BYTE *code;

        if (!(engine = (BYTE *)GetModuleHandleA("AfEngine.dll"))) return;
        code = engine + MOVE_CODE;
        game_main = (void *)GetProcAddress((HMODULE)engine, "?Get@NfMain@@SAPAV1@XZ");
        get_console = (void *)GetProcAddress((HMODULE)engine, "?GetConsole@NfMain@@QAEPAVNfConsole@@XZ");
        game_pointer_shown = (void *)GetProcAddress((HMODULE)engine, "?IsMouseCursorVisible@NfMain@@QAE_NXZ");
        if (!game_main || !get_console || !game_pointer_shown || IsBadReadPtr(code, sizeof(before) + 4 + sizeof(after))
            || memcmp(code, before, sizeof(before)) || *(BYTE **)(code + sizeof(before)) != engine + STEP_FOR_ONE
            || memcmp(code + sizeof(before) + 4, after, sizeof(after)))
        {
            unknown = TRUE;
            say("this is not the known game build; the menu pointer keeps the game's own speed");
            return;
        }
        get_value = (void *)GetProcAddress((HMODULE)engine, "?GetValueVariable@NfConsole@@QAEHPAD@Z");
        if (!get_value)
        {
            unknown = TRUE;
            return;
        }
    }
    engine = (BYTE *)GetModuleHandleA("AfEngine.dll");
    if (!engine || !(main = game_main()) || !(console = get_console(main))) return;
    sensitivity = get_value(console, "mouse_sensitivity");
    pointer_speed = (float)sensitivity / GAME_SENSITIVITY;
    pointer_step = sensitivity > 0 ? sensitivity * *(float *)(engine + STEP_FOR_ONE) : 0.0f;
    if (sensitivity != said_for && said++ < 20)
        say("the game's mouse_sensitivity is %d; its menu pointer is made to move %.2f times as far as the Mac pointer%s",
            sensitivity, pointer_speed, dinput_mouse_hook ? "" : ", once DirectInput watches the mouse");
    said_for = sensitivity;
}

static LONG move_for_game(LONG moved, LONG picture, LONG window, float step, float *owed)
{
    LONG give;

    if (!moved) return 0;
    *owed += (float)moved * picture / window * pointer_speed;
    if ((*owed < 0) != (moved < 0)) return 0;
    give = lroundf(sqrtf(fabsf(*owed) / step));
    if (moved < 0) give = -give;
    *owed -= give * labs(give) * step;
    return give;
}

static LRESULT CALLBACK matched_mouse_hook(int code, WPARAM wp, LPARAM lp)
{
    static float owed_x, owed_y;
    MSLLHOOKSTRUCT *event = (MSLLHOOKSTRUCT *)lp, given;
    float step = pointer_step;
    RECT client;
    POINT at;
    void *main;

    if (code == HC_ACTION && wp != WM_MOUSEMOVE && commands_before_input > 0)
    {
        InterlockedIncrement(&inputs_kept);
        return CallNextHookEx(NULL, code, wp, lp);
    }
    if (code != HC_ACTION || wp != WM_MOUSEMOVE || !event || step <= 0.0f || !mode_set || !game_main
        || !(main = game_main()) || !game_pointer_shown(main) || !picture_target(&client) || !GetCursorPos(&at))
        return dinput_mouse_hook(code, wp, lp);
    given = *event;
    given.pt.x = at.x + move_for_game(event->pt.x - at.x, game_mode.width, client.right, step, &owed_x);
    given.pt.y = at.y + move_for_game(event->pt.y - at.y, game_mode.height, client.bottom, step, &owed_y);
    InterlockedExchangeAdd(&moves_seen[0], event->pt.x - at.x);
    InterlockedExchangeAdd(&moves_seen[1], event->pt.y - at.y);
    InterlockedExchangeAdd(&moves_given[0], given.pt.x - at.x);
    InterlockedExchangeAdd(&moves_given[1], given.pt.y - at.y);
    return dinput_mouse_hook(code, wp, (LPARAM)&given);
}

static LRESULT CALLBACK scripted_key_hook(int code, WPARAM wp, LPARAM lp)
{
    KBDLLHOOKSTRUCT *event = (KBDLLHOOKSTRUCT *)lp;

    if (code == HC_ACTION && event && event->dwExtraInfo != SCRIPTED_KEY && commands_before_input > 0)
    {
        InterlockedIncrement(&inputs_kept);
        return CallNextHookEx(NULL, code, wp, lp);
    }
    return dinput_key_hook(code, wp, lp);
}

static HHOOK WINAPI dinput_set_hook(int id, HOOKPROC proc, HINSTANCE module, DWORD thread)
{
    if (id == WH_KEYBOARD_LL && proc && proc != scripted_key_hook && commands_before_input > 0)
    {
        if (!dinput_key_hook) say("DirectInput watches the keyboard through a hook; keys and clicks wait for the last scripted console command");
        dinput_key_hook = proc;
        proc = scripted_key_hook;
    }
    if (id == WH_MOUSE_LL && proc && proc != matched_mouse_hook)
    {
        if (!dinput_mouse_hook) say("DirectInput watches the mouse through a hook; the menu pointer's moves go through the helper");
        dinput_mouse_hook = proc;
        proc = matched_mouse_hook;
    }
    return SetWindowsHookExW(id, proc, module, thread);
}

/* Test runs only: the console command "pointer" is not the game's. */
static void say_where_pointer_is(void)
{
    HMODULE engine = GetModuleHandleA("AfEngine.dll");
    void *(__cdecl *get_main)(void) = (void *)GetProcAddress(engine, "?Get@NfMain@@SAPAV1@XZ");
    void *(__thiscall *get_place)(void *main, float *place) = (void *)GetProcAddress(engine, "?GetMousePos@NfMain@@QAE?AVCcCoord2d@@XZ");
    unsigned char (__thiscall *shown)(void *main) = (void *)GetProcAddress(engine, "?IsMouseCursorVisible@NfMain@@QAE_NXZ");
    float place[2] = { 0 };
    void *main;

    if (!get_main || !get_place || !shown || !(main = get_main()))
    {
        say("the game's pointer cannot be asked for its place");
        return;
    }
    get_place(main, place);
    say("the game's pointer is at %.1f,%.1f and %s; mouse moves changed by the helper add up to %ld,%ld and were handed on as %ld,%ld; the game takes a move of 1 as %.3f pixels",
        place[0], place[1], shown(main) ? "shown" : "hidden", moves_seen[0], moves_seen[1],
        moves_given[0], moves_given[1], pointer_step);
}

static BOOL patch_import(HMODULE module, const char *dll, const char *name, void *replacement)
{
    BYTE *base = (BYTE *)module;
    IMAGE_NT_HEADERS *nt;
    IMAGE_DATA_DIRECTORY *dir;
    void *target = GetProcAddress(GetModuleHandleA(dll), name);
    DWORD old;

    if (!module || !target) return FALSE;
    nt = (IMAGE_NT_HEADERS *)(base + ((IMAGE_DOS_HEADER *)base)->e_lfanew);
    dir = &nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT];
    if (!dir->VirtualAddress) return FALSE;
    for (IMAGE_IMPORT_DESCRIPTOR *imp = (IMAGE_IMPORT_DESCRIPTOR *)(base + dir->VirtualAddress); imp->Name; imp++)
    {
        if (lstrcmpiA((const char *)base + imp->Name, dll)) continue;
        for (void **slot = (void **)(base + imp->FirstThunk); slot[0]; slot++)
        {
            if (slot[0] != target) continue;
            if (!VirtualProtect(slot, sizeof(void *), PAGE_READWRITE, &old)) return FALSE;
            slot[0] = replacement;
            VirtualProtect(slot, sizeof(void *), old, &old);
            return TRUE;
        }
    }
    return FALSE;
}

static BOOL install_hooks(void)
{
    static const struct { const char *dll, *name; void *replacement; BOOL needed; } ddraw_hooks[] =
    {
        { "wined3d.dll", "wined3d_swapchain_present", scaled_present, TRUE },
        { "wined3d.dll", "wined3d_swapchain_get_front_buffer", noted_front_buffer, TRUE },
        { "wined3d.dll", "wined3d_device_context_blt", scaled_blt, TRUE },
        { "wined3d.dll", "wined3d_swapchain_create", windowed_swapchain_create, TRUE },
        { "wined3d.dll", "wined3d_output_set_display_mode", kept_set_display_mode, TRUE },
        { "wined3d.dll", "wined3d_output_get_display_mode", faked_get_display_mode, TRUE },
        { "wined3d.dll", "wined3d_output_get_mode", listed_mode, TRUE },
        { "wined3d.dll", "wined3d_restore_display_modes", kept_restore_display_modes, TRUE },
        { "user32.dll", "GetForegroundWindow", game_is_foreground, TRUE },
        { "user32.dll", "ClipCursor", ddraw_clip_cursor, TRUE },
        { "gdi32.dll", "BitBlt", counted_bitblt, FALSE },
    };
    HMODULE ddraw = LoadLibraryA("ddraw.dll"), wined3d = GetModuleHandleA("wined3d.dll");
    HMODULE dinput = LoadLibraryA("dinput.dll");

    if (!ddraw || !wined3d) return FALSE;
    real_present = (void *)GetProcAddress(wined3d, "wined3d_swapchain_present");
    real_front_buffer = (void *)GetProcAddress(wined3d, "wined3d_swapchain_get_front_buffer");
    real_back_buffer = (void *)GetProcAddress(wined3d, "wined3d_swapchain_get_back_buffer");
    real_blt = (void *)GetProcAddress(wined3d, "wined3d_device_context_blt");
    real_get_display_mode = (void *)GetProcAddress(wined3d, "wined3d_output_get_display_mode");
    real_swapchain_create = (void *)GetProcAddress(wined3d, "wined3d_swapchain_create");
    if (!real_swapchain_create || !real_present || !real_front_buffer || !real_back_buffer || !real_blt || !real_get_display_mode)
        return FALSE;

    for (unsigned int i = 0; i < ARRAYSIZE(ddraw_hooks); i++)
    {
        if (patch_import(ddraw, ddraw_hooks[i].dll, ddraw_hooks[i].name, ddraw_hooks[i].replacement)) continue;
        say("ddraw.dll does not import %s", ddraw_hooks[i].name);
        if (ddraw_hooks[i].needed) return FALSE;
    }
    real_swapchain_device = (void *)GetProcAddress(wined3d, "wined3d_swapchain_get_device");
    real_immediate_context = (void *)GetProcAddress(wined3d, "wined3d_device_get_immediate_context");
    real_get_viewports = (void *)GetProcAddress(wined3d, "wined3d_device_context_get_viewports");
    real_set_viewports = (void *)GetProcAddress(wined3d, "wined3d_device_context_set_viewports");
    if (!real_swapchain_device || !real_immediate_context || !real_get_viewports || !real_set_viewports)
    {
        real_set_viewports = NULL;
        say("this Wine cannot be told to set its viewport again; the picture is cut when the window and the game's picture differ in size");
    }
    real_sampler_state = (void *)GetProcAddress(wined3d, "wined3d_stateblock_set_sampler_state");
    if (anisotropy > 1 && real_sampler_state
        && !patch_import(ddraw, "wined3d.dll", "wined3d_stateblock_set_sampler_state", sharper_sampler_state))
        say("ddraw.dll does not import wined3d_stateblock_set_sampler_state; textures keep the game's filtering");
    real_texture_create = (void *)GetProcAddress(wined3d, "wined3d_texture_create");
    real_stateblock_viewport = (void *)GetProcAddress(wined3d, "wined3d_stateblock_set_viewport");
    real_upload = (void *)GetProcAddress(wined3d, "wined3d_streaming_buffer_upload");
    real_clear = (void *)GetProcAddress(wined3d, "wined3d_device_clear");
    real_map = (void *)GetProcAddress(wined3d, "wined3d_resource_map");
    real_unmap = (void *)GetProcAddress(wined3d, "wined3d_resource_unmap");
    real_texture_decref = (void *)GetProcAddress(wined3d, "wined3d_texture_decref");
    real_texture_resource = (void *)GetProcAddress(wined3d, "wined3d_texture_get_resource");
    real_texture_pitch = (void *)GetProcAddress(wined3d, "wined3d_texture_get_pitch");
    real_device_reset = (void *)GetProcAddress(wined3d, "wined3d_device_reset");
    real_update_desc = (void *)GetProcAddress(wined3d, "wined3d_texture_update_desc");
    real_view_resource = (void *)GetProcAddress(wined3d, "wined3d_rendertarget_view_get_resource");
    real_clear_view = (void *)GetProcAddress(wined3d, "wined3d_device_context_clear_rendertarget_view");
    real_set_views = (void *)GetProcAddress(wined3d, "wined3d_device_context_set_rendertarget_views");
    real_get_dc = (void *)GetProcAddress(wined3d, "wined3d_texture_get_dc");
    real_release_dc = (void *)GetProcAddress(wined3d, "wined3d_texture_release_dc");
    if (full_size && (!real_set_viewports || !real_texture_create || !real_texture_resource || !real_texture_pitch
        || !real_update_desc || !patch_import(ddraw, "wined3d.dll", "wined3d_texture_update_desc", full_size_update_desc)
        || !real_view_resource || !real_clear_view || !real_set_views || !real_get_dc || !real_release_dc
        || !patch_import(ddraw, "wined3d.dll", "wined3d_device_context_clear_rendertarget_view", scaled_clear_view)
        || !patch_import(ddraw, "wined3d.dll", "wined3d_device_context_set_rendertarget_views", noted_set_views)
        || !patch_import(ddraw, "wined3d.dll", "wined3d_texture_get_dc", shadow_get_dc)
        || !patch_import(ddraw, "wined3d.dll", "wined3d_texture_release_dc", shadow_release_dc)
        || !real_device_reset || !patch_import(ddraw, "wined3d.dll", "wined3d_device_reset", full_size_device_reset)
        || !patch_import(ddraw, "wined3d.dll", "wined3d_texture_get_pitch", shadow_pitch)
        || !patch_import(ddraw, "wined3d.dll", "wined3d_stateblock_set_viewport", scaled_stateblock_viewport)
        || !patch_import(ddraw, "wined3d.dll", "wined3d_streaming_buffer_upload", scaled_upload)
        || !patch_import(ddraw, "wined3d.dll", "wined3d_device_clear", scaled_clear)
        || !patch_import(ddraw, "wined3d.dll", "wined3d_resource_map", shadow_map)
        || !patch_import(ddraw, "wined3d.dll", "wined3d_resource_unmap", shadow_unmap)
        || !patch_import(ddraw, "wined3d.dll", "wined3d_texture_decref", noted_texture_decref)
        || !patch_import(ddraw, "wined3d.dll", "wined3d_swapchain_get_back_buffer", noted_back_buffer)))
    {
        say("this Wine's ddraw.dll lacks a call the full-size picture needs; the picture keeps the game's size");
        full_size = FALSE;
    }
    if (!real_texture_create || !patch_import(ddraw, "wined3d.dll", "wined3d_texture_create", better_texture_create))
        say("ddraw.dll does not import wined3d_texture_create; edges and depth stay as the game makes them");
    else no_depth_surface_yet = TRUE;
    if (!patch_import(dinput, "user32.dll", "ClipCursor", dinput_clip_cursor))
        say("dinput.dll does not import ClipCursor; the mouse is not kept inside the picture");
    if (!patch_import(dinput, "user32.dll", "SetCursorPos", dinput_set_cursor_pos))
        say("dinput.dll does not import SetCursorPos; its pointer moves are not counted");
    if (!patch_import(dinput, "user32.dll", "ShowCursor", dinput_show_cursor))
        say("dinput.dll does not import ShowCursor; the system pointer cannot be given an empty picture");
    if ((match_pointer || commands_before_input) && !patch_import(dinput, "user32.dll", "SetWindowsHookExW", dinput_set_hook))
    {
        if (match_pointer) say("dinput.dll does not import SetWindowsHookExW; the menu pointer keeps the game's own speed");
        if (commands_before_input) say("dinput.dll does not import SetWindowsHookExW; keys and clicks are not kept from the game");
        match_pointer = FALSE;
        commands_before_input = 0;
    }
    return TRUE;
}

/* The game's console does not know "+primattack". For a key bound to it the
   game runs "primattack 1" when the key goes down and "primattack 0" when it
   comes up, and so does this for "+name" and "-name". */
static void run_console_command(const char *command)
{
    HMODULE engine = GetModuleHandleA("AfEngine.dll");
    void *(__cdecl *get_main)(void) = (void *)GetProcAddress(engine, "?Get@NfMain@@SAPAV1@XZ");
    void *(__thiscall *get_console)(void *) = (void *)GetProcAddress(engine, "?GetConsole@NfMain@@QAEPAVNfConsole@@XZ");
    void (__cdecl *execute)(void *, const char *, ...) = (void *)GetProcAddress(engine, "?Execute@NfConsole@@QAAXPADZZ");
    void *main;

    if (!strcmp(command, "pointer"))
    {
        say_where_pointer_is();
        return;
    }
    if (!strcmp(command, "fullshot"))
    {
        say(full_size ? "the full-size picture is saved in two frames" : "fullshot needs full resolution; nothing is saved");
        if (full_size) test_shot_in = 2;
        return;
    }
    if (!get_main || !get_console || !execute || !(main = get_main())) return;
    if ((*command == '+' || *command == '-') && command[1] && !strchr(command, ' '))
    {
        say("running the console command: %s, as the game does for a key: %s %d", command, command + 1, *command == '+');
        execute(get_console(main), "%s %d", command + 1, *command == '+');
        return;
    }
    say("running the console command: %s", command);
    execute(get_console(main), "%s", command);
}

/* The game's camera takes one horizontal angle, 90 degrees, made for a 4:3
   picture. A wider picture then loses its top and bottom. This angle keeps the
   4:3 height and adds to the sides. */
static void widen_view_for(UINT width, UINT height)
{
    char command[32];

    if (!width || !height) return;
    snprintf(command, sizeof(command), "fov %.1f", atan(width * 3.0 / (height * 4.0)) * 360.0 / 3.14159265358979);
    run_console_command(command);
}

enum { FIT_INSIDE, WIDTH_LEADS, HEIGHT_LEADS };

static SIZE picture_shaped(HWND hwnd, LONG width, LONG height, int rule)
{
    RECT frame = { 0, 0, 0, 0 };
    SIZE client, fitted;

    AdjustWindowRectEx(&frame, GetWindowLongA(hwnd, GWL_STYLE), FALSE, GetWindowLongA(hwnd, GWL_EXSTYLE));
    client.cx = width - (frame.right - frame.left);
    client.cy = height - (frame.bottom - frame.top);
    if (client.cx > 0 && client.cy > 0)
    {
        fitted.cx = (client.cy * (LONG)game_mode.width + (LONG)game_mode.height / 2) / (LONG)game_mode.height;
        fitted.cy = (client.cx * (LONG)game_mode.height + (LONG)game_mode.width / 2) / (LONG)game_mode.width;
        if (rule == WIDTH_LEADS || (rule == FIT_INSIDE && client.cy > fitted.cy + 1)) client.cy = fitted.cy;
        else if (rule == HEIGHT_LEADS || client.cx > fitted.cx + 1) client.cx = fitted.cx;
    }
    client.cx += frame.right - frame.left;
    client.cy += frame.bottom - frame.top;
    return client;
}

/* Wine's Mac driver asks with WM_SIZING during a drag and only ever names a
   corner, also for a drag of one edge. So the side that moved further since
   the last size is taken as the one the user drags, and the other follows. */
static BOOL keep_picture_shape(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp)
{
    static int said;
    SIZE size;

    if (!keep_shape || !game_mode.width || !game_mode.height || IsIconic(hwnd)) return FALSE;
    if (msg == WM_WINDOWPOSCHANGING)
    {
        WINDOWPOS *pos = (WINDOWPOS *)lp;

        if (pos->flags & SWP_NOSIZE) return FALSE;
        SetRectEmpty(&given_area);
        size = picture_shaped(hwnd, pos->cx, pos->cy, FIT_INSIDE);
        if (!(pos->flags & SWP_NOMOVE))
        {
            pos->x += (pos->cx - size.cx) / 2;
            pos->y += (pos->cy - size.cy) / 2;
        }
        if ((size.cx != pos->cx || size.cy != pos->cy) && said++ < 20)
            say("window asked to be %dx%d; made %ldx%ld to keep the picture's shape", pos->cx, pos->cy, size.cx, size.cy);
        pos->cx = size.cx;
        pos->cy = size.cy;
        return FALSE;
    }
    else
    {
        RECT *rect = (RECT *)lp, now = { 0 };
        LONG wider, higher;

        GetWindowRect(hwnd, &now);
        wider = labs((rect->right - rect->left) - (now.right - now.left));
        higher = labs((rect->bottom - rect->top) - (now.bottom - now.top));
        size = picture_shaped(hwnd, rect->right - rect->left, rect->bottom - rect->top,
                              higher * (LONG)game_mode.width > wider * (LONG)game_mode.height ? HEIGHT_LEADS : WIDTH_LEADS);
        if (wp == WMSZ_TOPLEFT || wp == WMSZ_BOTTOMLEFT || wp == WMSZ_LEFT) rect->left = rect->right - size.cx;
        else rect->right = rect->left + size.cx;
        if (wp == WMSZ_TOPLEFT || wp == WMSZ_TOPRIGHT || wp == WMSZ_TOP) rect->top = rect->bottom - size.cy;
        else rect->bottom = rect->top + size.cy;
        return TRUE;
    }
}

static LRESULT CALLBACK hook_proc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp)
{
    if (msg == WIDEN_VIEW)
    {
        widen_view_for(wp, lp);
        return 0;
    }
    if (msg == HIDE_POINTER)
    {
        hide_pointer(wp);
        return 0;
    }
    if (msg == WM_SETCURSOR && pointer_hidden && LOWORD(lp) == HTCLIENT)
    {
        SetCursor(empty_cursor());
        return TRUE;
    }
    if (msg == WM_LBUTTONDOWN && mouse_free)
    {
        mouse_free = FALSE;
        say("a click in the picture: the mouse belongs to the game again");
    }
    if ((msg == WM_WINDOWPOSCHANGING || msg == WM_SIZING) && keep_picture_shape(hwnd, msg, wp, lp)) return TRUE;
    if (msg >= WM_KEYFIRST && msg <= WM_KEYLAST && commands_before_input > 0 && GetMessageExtraInfo() == SCRIPTED_KEY)
        scripted_char_owed = msg == WM_KEYDOWN || msg == WM_SYSKEYDOWN;
    else if ((msg == WM_CHAR || msg == WM_SYSCHAR) && scripted_char_owed)
        scripted_char_owed = FALSE;
    else if (msg >= WM_KEYFIRST && msg <= WM_KEYLAST && commands_before_input > 0)
    {
        InterlockedIncrement(&inputs_kept);
        return 0;
    }
    if (msg == WM_COPYDATA && ((COPYDATASTRUCT *)lp)->dwData == CONSOLE_COMMAND)
    {
        COPYDATASTRUCT *data = (COPYDATASTRUCT *)lp;
        static BOOL said;
        if (no_depth_surface_yet)
        {
            if (!said) say("the game has not reached its main menu yet; console commands wait until it has");
            said = TRUE;
            return CONSOLE_COMMAND_LATER;
        }
        if (data->cbData && !((const char *)data->lpData)[data->cbData - 1]) run_console_command(data->lpData);
        if (commands_before_input > 0 && !InterlockedDecrement(&commands_before_input))
            say("the last scripted console command has run; keys and clicks reach the game again, %ld key and button events were kept from it", inputs_kept);
        return CONSOLE_COMMAND_RUN;
    }
    if (msg == WM_ACTIVATEAPP || msg == WM_ACTIVATE || msg == WM_KILLFOCUS || msg == WM_SETFOCUS)
        say("message %s wp=%lx lp=%lx", msg == WM_ACTIVATEAPP ? "WM_ACTIVATEAPP" : msg == WM_ACTIVATE ? "WM_ACTIVATE"
            : msg == WM_KILLFOCUS ? "WM_KILLFOCUS" : "WM_SETFOCUS", (DWORD)wp, (DWORD)lp);
    if ((msg == WM_ACTIVATEAPP && !wp) || (msg == WM_ACTIVATE && !LOWORD(wp)) || msg == WM_KILLFOCUS)
        return 0;
    if (msg == WM_ACTIVATEAPP)
        return CallWindowProcA(game_proc, hwnd, msg, wp, lp);

    LRESULT result = CallWindowProcA(next_proc, hwnd, msg, wp, lp);

    if (max_client.cx && msg == WM_GETMINMAXINFO)
    {
        MINMAXINFO *info = (MINMAXINFO *)lp;
        info->ptMaxTrackSize.x = info->ptMaxTrackSize.y = 16384;
        if (mac_screen.cx && !test_on_right_display)
        {
            info->ptMaxPosition.x = info->ptMaxPosition.y = 0;
            info->ptMaxSize.x = mac_screen.cx;
            info->ptMaxSize.y = mac_screen.cy;
        }
    }
    return result;
}

/* F12 writes no screenshot in 32-bit colour, for two reasons in the game's own
   code. Its Direct3D driver cannot name a 32-bit screen without an alpha
   channel: the first change makes it answer "32-bit with alpha", which has the
   same bytes per pixel. The game then refuses to turn a picture with alpha into
   the 24-bit file: the second change sets its "do it anyway" argument. Only
   builds with these exact bytes are touched. The game unloads and reloads the
   driver, so this runs on every tick of the watch thread. */
static void let_screenshots_work_in_32_bit(void)
{
    static const struct { const char *module; DWORD at; BYTE before[10], was, now; } changes[] =
    {
        { "gtDirect3D.dll", 0x2550, { 0x83, 0xfe, 0x20, 0x75, 0x7e, 0xf6, 0xc2, 0x01, 0x74 }, 0x79, 0x28 },
        { NULL, 0x12411, { 0x85, 0xc0, 0x74, 0x36, 0x6a }, 0x00, 0x01 },
    };
    static BOOL said;

    for (unsigned int i = 0; i < ARRAYSIZE(changes); i++)
    {
        BYTE *code = (BYTE *)GetModuleHandleA(changes[i].module), *byte;
        size_t length = strlen((const char *)changes[i].before);
        DWORD old;

        if (!code) return;
        code += changes[i].at;
        byte = code + length;
        if (IsBadReadPtr(code, length + 1) || memcmp(code, changes[i].before, length)
            || (*byte != changes[i].was && *byte != changes[i].now))
        {
            if (!said) say("this is not the known game build; F12 screenshots stay off in 32-bit colour");
            said = TRUE;
            return;
        }
        if (*byte == changes[i].now || !VirtualProtect(byte, 1, PAGE_EXECUTE_READWRITE, &old)) continue;
        *byte = changes[i].now;
        VirtualProtect(byte, 1, old, &old);
        FlushInstructionCache(GetCurrentProcess(), byte, 1);
        if (i == 0 && !said) say("F12 screenshots made to work in 32-bit colour");
        if (i == 0) said = TRUE;
    }
}

static void skip_intros(void)
{
    enum { INTRO_LIST = 0x4256c, COMPANIES = 0x42544, AIRFIX = 0x42558, INTROS = 2 };
    static const char missing_file_that_ends_the_intro[] = "video\\shown-by-the-launcher.avi";
    BYTE *game = (BYTE *)GetModuleHandleA(NULL);
    const char **list = (const char **)(game + INTRO_LIST);
    int skip = env_size("DOGFIGHTER_SKIP_INTROS").cx;
    DWORD old;

    if (skip <= 0) return;
    if (skip > INTROS) skip = INTROS;
    if (!game || IsBadReadPtr(list, (INTROS + 1) * sizeof(*list))
        || list[0] != (const char *)game + COMPANIES || list[1] != (const char *)game + AIRFIX || list[INTROS]
        || strcmp(list[0], "video\\companies.avi") || strcmp(list[1], "video\\airfix.avi"))
    {
        say("this is not the known game build; the game plays its own intro videos as well");
        return;
    }
    if (!VirtualProtect(list, (INTROS + 1) * sizeof(*list), PAGE_READWRITE, &old))
    {
        say("could not change the list of intro videos; the game plays its own as well");
        return;
    }
    for (int i = 0; i < INTROS; i++) list[i] = i + skip < INTROS ? list[i + skip] : NULL;
    if (!list[0]) list[0] = missing_file_that_ends_the_intro;
    VirtualProtect(list, (INTROS + 1) * sizeof(*list), old, &old);
    say("the launcher showed the first %d intro video%s; the game leaves %s out", skip, skip > 1 ? "s" : "",
        skip > 1 ? "them" : "it");
}

static void raise_texture_size_limit(void)
{
    enum { MAX_TEXTURE_SIDE_FUNCTION = 0x70f0, ORIGINAL_LIMIT = 256 };
    static const BYTE returns_a_constant[] = { 0xb8, 0x00 }, rest[] = { 0x00, 0x00, 0xc3 };
    static BOOL done;
    BYTE *code = (BYTE *)GetModuleHandleA("Cc.dll"), wanted = texture_limit >> 8;
    DWORD old;

    if (done || !texture_limit || !code) return;
    done = TRUE;
    code += MAX_TEXTURE_SIDE_FUNCTION;
    if (IsBadReadPtr(code, 6) || memcmp(code, returns_a_constant, 2) || memcmp(code + 3, rest, 3)
        || (code[2] != ORIGINAL_LIMIT >> 8 && code[2] != wanted))
    {
        say("this is not the known game build; textures stay at most %d pixels", ORIGINAL_LIMIT);
        return;
    }
    if (code[2] != wanted)
    {
        if (!VirtualProtect(code + 2, 1, PAGE_EXECUTE_READWRITE, &old))
        {
            say("could not change the texture size limit; textures stay at most %d pixels", ORIGINAL_LIMIT);
            return;
        }
        code[2] = wanted;
        VirtualProtect(code + 2, 1, old, &old);
        FlushInstructionCache(GetCurrentProcess(), code, 6);
    }
    say("texture size limit raised from %d to %u pixels", ORIGINAL_LIMIT, texture_limit);
}

/* Enters a function of the game through a jump written over its first bytes,
   which must be whole instructions that do not depend on where they stand.
   Returns a copy of those bytes that jumps on into the function, to call the
   game's own code with; NULL, and nothing changed, when the bytes are not
   the expected ones. */
static void *enter_game_function(BYTE *code, const BYTE *expected, SIZE_T stolen, void *replacement)
{
    enum { JUMP = 0xe9, NOP = 0x90, JUMP_SIZE = 5 };
    BYTE *copy;
    DWORD old;

    if (stolen < JUMP_SIZE || IsBadReadPtr(code, stolen) || memcmp(code, expected, stolen)
        || !(copy = VirtualAlloc(NULL, stolen + JUMP_SIZE, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE)))
        return NULL;
    if (!VirtualProtect(code, stolen, PAGE_EXECUTE_READWRITE, &old))
    {
        VirtualFree(copy, 0, MEM_RELEASE);
        return NULL;
    }
    memcpy(copy, code, stolen);
    copy[stolen] = JUMP;
    *(LONG *)(copy + stolen + 1) = (code + stolen) - (copy + stolen + JUMP_SIZE);
    code[0] = JUMP;
    *(LONG *)(code + 1) = (BYTE *)replacement - (code + JUMP_SIZE);
    memset(code + JUMP_SIZE, NOP, stolen - JUMP_SIZE);
    VirtualProtect(code, stolen, old, &old);
    FlushInstructionCache(GetCurrentProcess(), code, stolen);
    return copy;
}

/* The game draws a flat picture as large as the size stored in its file, and
   takes texture coordinates as pixels of that size. A file with more pixels
   would be drawn larger. For a file that has a marker next to it,
   cache\<file>.2x or cache\<file>.4x, the stored size is divided by 2 or 4
   after loading, so the picture keeps its place and size and only gains
   pixels. The window and gadget code lays its pieces out with
   GtImage::GetWidth and GetHeight, which give the real pixel count; for a
   marked picture the calls from AfEngine.dll and the game itself get the
   stored size instead. gtDirect3D.dll keeps the real one. The game's loader is
   entered through a jump written over its first five bytes, which are whole
   instructions; only a build with exactly those bytes is touched. */
enum { TEXTURE_FILE_NAME = 0x88, TEXTURE_STORED_WIDTH = 0x6c, TEXTURE_STORED_HEIGHT = 0x70, MAX_ENLARGED = 4096 };
static struct enlarged { void *texture; const char *file; int width, height; } enlarged[MAX_ENLARGED];
static int enlarged_used;
static unsigned char (__fastcall *game_texture_load)(void *texture, void *unused, void *device);
static int (__fastcall *game_image_width)(void *image, void *unused, int level);
static int (__fastcall *game_image_height)(void *image, void *unused, int level);

static BOOL still_enlarged(const struct enlarged *entry)
{
    BYTE *texture = entry->texture;

    return !IsBadReadPtr(texture, TEXTURE_FILE_NAME + sizeof(char *))
        && *(const char **)(texture + TEXTURE_FILE_NAME) == entry->file
        && *(int *)(texture + TEXTURE_STORED_WIDTH) == entry->width
        && *(int *)(texture + TEXTURE_STORED_HEIGHT) == entry->height;
}

static struct enlarged *enlarged_entry(void *texture)
{
    for (int i = 0; i < enlarged_used; i++)
    {
        if (enlarged[i].texture != texture) continue;
        if (still_enlarged(&enlarged[i])) return &enlarged[i];
        enlarged[i].texture = NULL;
    }
    return NULL;
}

static BOOL note_enlarged(void *texture, const char *file, int width, int height)
{
    int slot = -1;

    for (int pass = 0; pass < 2 && slot < 0; pass++)
    {
        for (int i = 0; i < enlarged_used && slot < 0; i++)
        {
            if (pass && enlarged[i].texture && !still_enlarged(&enlarged[i])) enlarged[i].texture = NULL;
            if (!enlarged[i].texture) slot = i;
        }
        if (slot < 0 && enlarged_used < MAX_ENLARGED) slot = enlarged_used++;
    }
    if (slot < 0) return FALSE;
    enlarged[slot].file = file;
    enlarged[slot].width = width;
    enlarged[slot].height = height;
    enlarged[slot].texture = texture;
    return TRUE;
}

static int __fastcall drawn_image_width(void *image, void *unused, int level)
{
    int real = game_image_width(image, unused, level);
    struct enlarged *entry = real ? enlarged_entry(image) : NULL;

    return entry ? entry->width >> level : real;
}

static int __fastcall drawn_image_height(void *image, void *unused, int level)
{
    int real = game_image_height(image, unused, level);
    struct enlarged *entry = real ? enlarged_entry(image) : NULL;

    return entry ? entry->height >> level : real;
}

static unsigned char __fastcall marked_texture_load(void *texture, void *unused, void *device)
{
    unsigned char loaded = game_texture_load(texture, unused, device);
    const char *file = *(const char **)((BYTE *)texture + TEXTURE_FILE_NAME);
    int *width = (int *)((BYTE *)texture + TEXTURE_STORED_WIDTH), *height = (int *)((BYTE *)texture + TEXTURE_STORED_HEIGHT);
    struct enlarged *entry = enlarged_entry(texture);
    char marker[MAX_PATH];

    if (entry) entry->texture = NULL;
    if (!loaded || !file || IsBadStringPtrA(file, MAX_PATH)) return loaded;
    if (test_shot_on[0] && snprintf(marker, sizeof(marker), "%s", file) < (int)sizeof(marker) && strstr(CharLowerA(marker), test_shot_on))
        test_shot_in = 4;
    for (int times = 4; times >= 2; times -= 2)
    {
        if (snprintf(marker, sizeof(marker), "cache\\%s.%dx", file, times) >= (int)sizeof(marker)
            || GetFileAttributesA(marker) == INVALID_FILE_ATTRIBUTES)
            continue;
        if (*width % times || *height % times || !note_enlarged(texture, file, *width / times, *height / times))
        {
            say("picture %s has a marker for %d times the pixels that cannot be used; it is drawn as it is", file, times);
            break;
        }
        *width /= times;
        *height /= times;
        say("picture %s has %d times the pixels a side; it is drawn at %dx%d", file, times, *width, *height);
        break;
    }
    return loaded;
}

/* Test runs only: one log line for the first time each picture is drawn flat,
   with its place on the game's screen. Every flat draw of the game ends in
   this one function of GtScreen. */
static void (__fastcall *game_draw_flat)(void *screen, void *unused, void *texture, float x, float y, float width, float height,
                                         float left, float top, float right, float bottom, DWORD colour);

static void __fastcall noted_draw_flat(void *screen, void *unused, void *texture, float x, float y, float width, float height,
                                       float left, float top, float right, float bottom, DWORD colour)
{
    static struct { void *texture; const char *file; } seen[2048];
    static int used;
    const char *file = texture && !IsBadReadPtr(texture, TEXTURE_FILE_NAME + sizeof(char *)) ? *(const char **)((BYTE *)texture + TEXTURE_FILE_NAME) : NULL;
    int i;

    for (i = 0; i < used && (seen[i].texture != texture || seen[i].file != file); i++) ;
    if (i == used && used < (int)ARRAYSIZE(seen) && file && !IsBadStringPtrA(file, MAX_PATH))
    {
        seen[used].texture = texture;
        seen[used++].file = file;
        say("first draw of %s: at %g,%g size %gx%g, part %g,%g to %g,%g", file, x, y, width, height, left, top, right, bottom);
    }
    game_draw_flat(screen, unused, texture, x, y, width, height, left, top, right, bottom, colour);
}

static void note_flat_draws(BYTE *cc)
{
    enum { DRAW_FUNCTION = 0x44eb0 };
    static const BYTE start[] = { 0x81, 0xec, 0xcc, 0x01, 0x00, 0x00 };

    game_draw_flat = enter_game_function(cc + DRAW_FUNCTION, start, sizeof(start), noted_draw_flat);
    say(game_draw_flat ? "test run: the first flat draw of each picture is noted"
                       : "test run: this is not the known game build; flat draws are not noted");
}

static BOOL give_stored_image_sizes(void)
{
    static const char *const width_name = "?GetWidth@GtImage@@QAEHH@Z", *const height_name = "?GetHeight@GtImage@@QAEHH@Z";
    static const BYTE reads_real_size[] = { 0x8b, 0xc1, 0x8b, 0x4c, 0x24, 0x04, 0x85, 0xc9, 0x7c, 0x0d, 0x3b, 0x48, 0x08, 0x7d, 0x08, 0x8b, 0x40 };
    HMODULE cc = GetModuleHandleA("Cc.dll"), users[] = { GetModuleHandleA("AfEngine.dll"), GetModuleHandleA(NULL) };
    BYTE *width = (BYTE *)GetProcAddress(cc, width_name), *height = (BYTE *)GetProcAddress(cc, height_name);

    if (!width || !height || memcmp(width, reads_real_size, sizeof(reads_real_size)) || width[sizeof(reads_real_size)] != 0x14
        || memcmp(height, reads_real_size, sizeof(reads_real_size)) || height[sizeof(reads_real_size)] != 0x18)
        return FALSE;
    game_image_width = (void *)width;
    game_image_height = (void *)height;
    if (!patch_import(users[0], "Cc.dll", width_name, drawn_image_width)
        || !patch_import(users[0], "Cc.dll", height_name, drawn_image_height))
        return FALSE;
    if (!patch_import(users[1], "Cc.dll", width_name, drawn_image_width)) say("the game itself does not ask for picture widths");
    if (!patch_import(users[1], "Cc.dll", height_name, drawn_image_height)) say("the game itself does not ask for picture heights");
    return TRUE;
}

static void hook_texture_load(void)
{
    enum { LOAD_FUNCTION = 0x46350 };
    static const BYTE start[] = { 0x83, 0xec, 0x48, 0x53, 0x55 };
    static BOOL done;
    BYTE *cc = (BYTE *)GetModuleHandleA("Cc.dll");

    if (done || !cc || !GetModuleHandleA("AfEngine.dll")) return;
    done = TRUE;
    if (IsBadReadPtr(cc + LOAD_FUNCTION, sizeof(start)) || memcmp(cc + LOAD_FUNCTION, start, sizeof(start)) || !give_stored_image_sizes()
        || !(game_texture_load = enter_game_function(cc + LOAD_FUNCTION, start, sizeof(start), marked_texture_load)))
    {
        say("this is not the known game build; pictures with more pixels are drawn too large");
        return;
    }
    say("the game's texture loader is watched for pictures with 2 or 4 times the pixels");
    if (test_notes_draws) note_flat_draws(cc);
}

static BOOL CALLBACK note_display(HMONITOR monitor, HDC dc, RECT *rect, LPARAM lp)
{
    MONITORINFO info = { sizeof(info) };

    if (!GetMonitorInfoA(monitor, &info)) return TRUE;
    say("display at %ld,%ld %ldx%ld, room for windows at %ld,%ld %ldx%ld", info.rcMonitor.left, info.rcMonitor.top,
        info.rcMonitor.right - info.rcMonitor.left, info.rcMonitor.bottom - info.rcMonitor.top,
        info.rcWork.left, info.rcWork.top, info.rcWork.right - info.rcWork.left, info.rcWork.bottom - info.rcWork.top);
    if (IsRectEmpty(&test_display) || info.rcWork.left > test_display.left) test_display = info.rcWork;
    return TRUE;
}

static void fit_on_test_display(DWORD style, DWORD ex)
{
    RECT frame = { 0, 0, 0, 0 };
    LONG wide, high;

    EnumDisplayMonitors(NULL, NULL, note_display, 0);
    if (IsRectEmpty(&test_display))
    {
        test_on_right_display = FALSE;
        return;
    }
    AdjustWindowRectEx(&frame, style, FALSE, ex);
    wide = test_display.right - test_display.left - (frame.right - frame.left);
    high = test_display.bottom - test_display.top - (frame.bottom - frame.top);
    if (max_client.cx > wide) max_client.cx = wide;
    if (max_client.cy > high) max_client.cy = high;
}

static void centre_picture_in(HWND w, const RECT *area)
{
    LONG wide = area->right - area->left, high = area->bottom - area->top;
    SIZE size = { wide, wide * (LONG)game_mode.height / (LONG)game_mode.width };
    RECT frame;

    if (size.cy > high)
    {
        size.cy = high;
        size.cx = high * (LONG)game_mode.width / (LONG)game_mode.height;
    }
    SetRect(&frame, area->left + (wide - size.cx) / 2, area->top + (high - size.cy) / 2, 0, 0);
    frame.right = frame.left + size.cx;
    frame.bottom = frame.top + size.cy;
    say("the window was given %ldx%ld at %ld,%ld without being asked; the picture, %ldx%ld, goes in its middle at %ld,%ld",
        wide, high, area->left, area->top, size.cx, size.cy, frame.left, frame.top);
    AdjustWindowRectEx(&frame, GetWindowLongA(w, GWL_STYLE), FALSE, GetWindowLongA(w, GWL_EXSTYLE));
    fitted_for.cx = game_mode.width;
    fitted_for.cy = game_mode.height;
    SetWindowPos(w, NULL, frame.left, frame.top, frame.right - frame.left, frame.bottom - frame.top,
                 SWP_NOSENDCHANGING | SWP_NOZORDER | SWP_NOACTIVATE);
}

static void keep_middle_on_display(HWND w, RECT *frame)
{
    MONITORINFO display = { sizeof(display) };
    RECT now, *room = &display.rcWork;
    LONG wide = frame->right - frame->left, high = frame->bottom - frame->top, x, y;

    if (!GetWindowRect(w, &now) || !GetMonitorInfoA(MonitorFromWindow(w, MONITOR_DEFAULTTONEAREST), &display)) return;
    x = now.left + (now.right - now.left - wide) / 2;
    y = now.top;
    if (x + wide > room->right) x = room->right - wide;
    if (x < room->left) x = room->left;
    if (y + high > room->bottom) y = room->bottom - high;
    if (y < room->top) y = room->top;
    SetRect(frame, x, y, x + wide, y + high);
}

/* macOS full screen. Wine's Mac driver hands the window its new size with
   SWP_NOSENDCHANGING, so WM_WINDOWPOSCHANGING never comes and the size is only
   seen afterwards. The picture is then centred in the area that was given, and
   again when the game changes its mode. A size the window is asked about ends
   this: that is how leaving full screen arrives. */
static BOOL fill_given_area(HWND w, BOOL same_shape)
{
    static RECT seen;
    static int steady, tries;
    LONG width = game_mode.width, height = game_mode.height, off;
    RECT client = { 0 };

    GetClientRect(w, &client);
    MapWindowPoints(w, NULL, (POINT *)&client, 2);
    if (!IsRectEmpty(&given_area))
    {
        if (same_shape && (!EqualRect(&client, &given_area) || ++tries > 3)) return TRUE;
        centre_picture_in(w, &given_area);
        return TRUE;
    }
    tries = 0;
    if (!same_shape) return FALSE;
    off = (client.right - client.left) * height - (client.bottom - client.top) * width;
    if (labs(off) <= 2 * max(width, height))
    {
        steady = 0;
        return FALSE;
    }
    if (!EqualRect(&client, &seen)) steady = 0;
    seen = client;
    if (++steady < 4) return TRUE;
    given_area = client;
    centre_picture_in(w, &given_area);
    return TRUE;
}

static void make_normal_window(HWND w)
{
    static BOOL placed;
    DWORD style = GetWindowLongA(w, GWL_STYLE), ex = GetWindowLongA(w, GWL_EXSTYLE);
    BOOL normal = (style & WS_OVERLAPPEDWINDOW) == WS_OVERLAPPEDWINDOW && !(ex & WS_EX_TOPMOST);
    BOOL same_shape = fitted_for.cx && fitted_for.cx * (LONG)game_mode.height == fitted_for.cy * (LONG)game_mode.width;
    RECT client = { 0 }, frame;
    SIZE size;

    if (!game_mode.width || !game_mode.height || IsIconic(w)) return;
    if (keep_shape && normal && fitted_for.cx && fill_given_area(w, same_shape)) return;
    if (normal && same_shape) return;
    if (IsZoomed(w))
    {
        MONITORINFO display = { sizeof(display) };

        if (!keep_shape || same_shape || !GetMonitorInfoA(MonitorFromWindow(w, MONITOR_DEFAULTTONEAREST), &display)) return;
        fitted_for.cx = game_mode.width;
        fitted_for.cy = game_mode.height;
        SetWindowPos(w, NULL, display.rcWork.left, display.rcWork.top, display.rcWork.right - display.rcWork.left,
                     display.rcWork.bottom - display.rcWork.top, SWP_NOZORDER | SWP_NOACTIVATE);
        GetClientRect(w, &client);
        say("picture %ux%u, zoomed window given its shape: client area now %ldx%ld",
            game_mode.width, game_mode.height, client.right, client.bottom);
        return;
    }

    style = (style & ~WS_POPUP) | WS_OVERLAPPEDWINDOW;
    ex &= ~WS_EX_TOPMOST;
    if (!placed && test_on_right_display) fit_on_test_display(style, ex);

    GetClientRect(w, &client);
    size.cx = client.right;
    size.cy = client.bottom;
    if (!same_shape)
    {
        size = fitted_client();
    }
    fitted_for.cx = game_mode.width;
    fitted_for.cy = game_mode.height;

    SetRect(&frame, 0, 0, size.cx, size.cy);
    AdjustWindowRectEx(&frame, style, FALSE, ex);
    SetWindowLongA(w, GWL_STYLE, style);
    SetWindowLongA(w, GWL_EXSTYLE, ex);
    OffsetRect(&frame, test_display.left - frame.left, test_display.top - frame.top);
    if (placed) keep_middle_on_display(w, &frame);
    SetWindowPos(w, HWND_NOTOPMOST, frame.left, frame.top, frame.right - frame.left,
                 frame.bottom - frame.top, SWP_FRAMECHANGED | SWP_NOACTIVATE);
    placed = TRUE;
    if (test_on_right_display && GetWindowRect(w, &frame))
        say("test run: window at %ld,%ld %ldx%ld, on the display with room at %ld,%ld %ldx%ld", frame.left, frame.top,
            frame.right - frame.left, frame.bottom - frame.top, test_display.left, test_display.top,
            test_display.right - test_display.left, test_display.bottom - test_display.top);

    GetClientRect(w, &client);
    say("picture %ux%u, window client area now %ldx%ld (asked for %ldx%ld), style %08lx",
        game_mode.width, game_mode.height, client.right, client.bottom, size.cx, size.cy,
        (DWORD)GetWindowLongA(w, GWL_STYLE));
}

static void keep_mouse_inside(void)
{
    static BOOL keys_were_down, ours, ctrl_was_down, option_was_down;
    static const char *titled_as;
    const char *title;
    static int keys_noted;
    static HWND titled;
    static RECT wanted, applied;
    BOOL ctrl_down = (GetAsyncKeyState(VK_CONTROL) & 0x8000) != 0, option_down = (GetAsyncKeyState(VK_MENU) & 0x8000) != 0;
    BOOL keys_down = ctrl_down && option_down;
    SYSTEMTIME at;
    BOOL front = game_window && GetForegroundWindow() == game_window && !IsIconic(game_window);
    RECT client = { 0 }, now = { 0 };
    BOOL held;

    GetLocalTime(&at);
    if ((ctrl_down != ctrl_was_down || option_down != option_was_down) && keys_noted < 200)
    {
        keys_noted++;
        say("%02u:%02u:%02u keys: Ctrl is %s, Option is %s%s", at.wHour, at.wMinute, at.wSecond,
            ctrl_down ? "down" : "up", option_down ? "down" : "up", front ? "" : "; the game is not in front");
    }
    ctrl_was_down = ctrl_down;
    option_was_down = option_down;

    if (!front) mouse_free = FALSE;
    else if (keys_down && !keys_were_down)
    {
        mouse_free = !mouse_free;
        say("%02u:%02u:%02u Ctrl+Option: the mouse %s; so far DirectInput asked %ld times to hold it and moved the pointer itself %ld times",
            at.wHour, at.wMinute, at.wSecond, mouse_free ? "is free" : "belongs to the game again", dinput_clips, dinput_moves);
    }
    keys_were_down = keys_down;

    held = front && dinput_wants_mouse && !mouse_free && GetClientRect(game_window, &client) && client.right;
    hide_pointer_while_held(held);
    if (held)
    {
        MapWindowPoints(game_window, NULL, (POINT *)&client, 2);
        GetClipCursor(&now);
        if (!ours || !EqualRect(&client, &wanted) || !EqualRect(&now, &applied))
        {
            if (!test_leaves_mouse) ClipCursor(&client);
            GetClipCursor(&applied);
            if (!ours || !EqualRect(&client, &wanted))
                say("%s %ld,%ld %ldx%ld; the picture is at %ld,%ld %ldx%ld",
                    test_leaves_mouse ? "test run, the mouse is not held; it can move in" : "mouse kept inside",
                    applied.left, applied.top, applied.right - applied.left, applied.bottom - applied.top,
                    client.left, client.top, client.right - client.left, client.bottom - client.top);
            wanted = client;
            ours = TRUE;
        }
    }
    else if (ours)
    {
        if (!test_leaves_mouse) ClipCursor(NULL);
        ours = FALSE;
        say("mouse let go");
    }

    title = commands_before_input > 0 ? "Airfix Dogfighter - starting by itself, keys and clicks wait"
        : mouse_free ? "Airfix Dogfighter - the mouse is free, Ctrl+Option gives it back"
        : "Airfix Dogfighter - Ctrl+Option frees the mouse";
    if (game_window && mode_set && (titled != game_window || titled_as != title))
    {
        titled = game_window;
        titled_as = title;
        SendMessageTimeoutA(game_window, WM_SETTEXT, 0, (LPARAM)title, SMTO_ABORTIFHUNG, 500, NULL);
    }
}

static void end_input_wait_when_late(void)
{
    static DWORD since;
    static BOOL counting;

    if (commands_before_input <= 0 || !input_wait_limit || !mode_set || no_depth_surface_yet) return;
    if (!counting) since = GetTickCount();
    counting = TRUE;
    if (GetTickCount() - since < input_wait_limit * 1000) return;
    LONG missing = InterlockedExchange(&commands_before_input, 0);
    if (missing > 0)
        say("gave up waiting for %ld scripted console command%s after %lu seconds in the game; keys and clicks reach the game again, %ld key and button events were kept from it",
            missing, missing == 1 ? "" : "s", input_wait_limit, inputs_kept);
}

static DWORD WINAPI watch(void *arg)
{
    DWORD pid = GetCurrentProcessId(), owner, ticks = 0, reported_at = GetTickCount();
    LONG reported = 0, reported_flips = 0;
    SIZE viewed = { 0, 0 };

    for (;;)
    {
        HWND w = FindWindowA("AirfixClass", NULL);
        if (w && GetWindowThreadProcessId(w, &owner) && owner == pid)
        {
            WNDPROC cur = (WNDPROC)GetWindowLongPtrA(w, GWLP_WNDPROC);
            WNDPROC cls = (WNDPROC)GetClassLongPtrA(w, GCLP_WNDPROC);
            game_window = w;
            if (cur != hook_proc && cur != cls)
            {
                game_proc = cls;
                next_proc = cur;
                SetWindowLongPtrA(w, GWLP_WNDPROC, (LONG_PTR)hook_proc);
            }
            if (max_client.cx && cur == hook_proc) make_normal_window(w);
            if (widen_view && cur == hook_proc && (viewed.cx != (LONG)game_mode.width || viewed.cy != (LONG)game_mode.height))
            {
                viewed.cx = game_mode.width;
                viewed.cy = game_mode.height;
                PostMessageA(w, WIDEN_VIEW, viewed.cx, viewed.cy);
            }
        }
        let_screenshots_work_in_32_bit();
        raise_texture_size_limit();
        if (texture_limit || test_shot_on[0]) hook_texture_load();
        end_input_wait_when_late();
        if (max_client.cx) keep_mouse_inside();
        if (max_client.cx && ++ticks % 100 == 0 && flips + direct_draws + gdi_draws + unscaled_draws != reported)
        {
            RECT client = { 0 };
            if (game_window) GetClientRect(game_window, &client);
            DWORD at = GetTickCount();
            LONG now = flips;
            say("%.1f flips a second over the last %.1f seconds, picture %ux%u format %d",
                (now - reported_flips) * 1000.0 / (at - reported_at + 1), (at - reported_at) / 1000.0,
                game_mode.width, game_mode.height, game_mode.format_id);
            reported_flips = now;
            reported_at = at;
            reported = flips + direct_draws + gdi_draws + unscaled_draws;
            say("so far %ld flips and %ld direct draws scaled into client area %ldx%ld; not scaled: %ld through GDI, %ld without a back buffer; DirectInput asked %ld times to hold the mouse and moved the pointer itself %ld times",
                flips, direct_draws, client.right, client.bottom, gdi_draws, unscaled_draws, dinput_clips, dinput_moves);
        }
        Sleep(50);
    }
    return 0;
}

BOOL WINAPI DllMain(HINSTANCE inst, DWORD reason, void *reserved)
{
    if (reason == DLL_PROCESS_ATTACH)
    {
        DisableThreadLibraryCalls(inst);
        max_client = env_size("DOGFIGHTER_WINDOW");
        mac_screen = env_size("DOGFIGHTER_SCREEN");
        read_mode_list();
        widen_view = GetEnvironmentVariableA("DOGFIGHTER_WIDEN_VIEW", NULL, 0) != 0;
        test_on_right_display = GetEnvironmentVariableA("DOGFIGHTER_TEST_DISPLAY", NULL, 0) != 0;
        test_leaves_mouse = GetEnvironmentVariableA("DOGFIGHTER_TEST_LEAVES_MOUSE", NULL, 0) != 0;
        commands_before_input = env_size("DOGFIGHTER_TEST_INPUT_AFTER_COMMANDS").cx;
        input_wait_limit = env_size("DOGFIGHTER_TEST_INPUT_WAIT_LIMIT").cx;
        anisotropy = env_size("DOGFIGHTER_ANISOTROPY").cx;
        texture_limit = env_size("DOGFIGHTER_TEXTURE_LIMIT").cx;
        edge_samples = env_size("DOGFIGHTER_EDGE_SAMPLES").cx;
        if (edge_samples > 16) edge_samples = 0;
        deep_z = GetEnvironmentVariableA("DOGFIGHTER_DEEP_Z", NULL, 0) != 0;
        keep_shape = GetEnvironmentVariableA("DOGFIGHTER_KEEP_SHAPE", NULL, 0) != 0;
        match_pointer = GetEnvironmentVariableA("DOGFIGHTER_MATCH_POINTER", NULL, 0) != 0;
        frames_a_second = env_size("DOGFIGHTER_FPS").cx;
        if (frames_a_second > 1000) frames_a_second = 0;
        full_size = GetEnvironmentVariableA("DOGFIGHTER_FULL_SIZE", NULL, 0) != 0;
        test_saves_full_size = GetEnvironmentVariableA("DOGFIGHTER_TEST_FULL_SIZE_SHOTS", NULL, 0) != 0;
        if (texture_limit != 512 && texture_limit != 1024) texture_limit = 0;
        test_notes_draws = GetEnvironmentVariableA("DOGFIGHTER_TEST_NOTES_DRAWS", NULL, 0) != 0;
        if (GetEnvironmentVariableA("DOGFIGHTER_TEST_SHOT_ON", test_shot_on, sizeof(test_shot_on)) >= sizeof(test_shot_on)) test_shot_on[0] = 0;
        CharLowerA(test_shot_on);
        if (max_client.cx && max_client.cy)
        {
            log_file = fopen("C:\\dogfighter-focushook.log", "w");
            if (mode_count && install_hooks())
                say("scaling the picture into a window of up to %ldx%ld; %u display modes offered to the game",
                    max_client.cx, max_client.cy, mode_count);
            else
            {
                say("could not hook Wine's ddraw; the picture is not scaled");
                max_client.cx = 0;
            }
        }
        if (!max_client.cx) tell_helper_about_picture();
        skip_intros();
        CloseHandle(CreateThread(NULL, 0, watch, NULL, 0, NULL));
    }
    return TRUE;
}
