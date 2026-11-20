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

#define WINED3DERR_INVALIDCALL ((HRESULT)0x8876086c)
#define CONSOLE_COMMAND 0x41664463
#define WIDEN_VIEW (WM_APP + 0x4466)

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

static FILE *log_file;
static HWND game_window;
static WNDPROC game_proc, next_proc;
static SIZE max_client, mac_screen, fitted_for, modes[32];
static unsigned int mode_count;
static struct wined3d_display_mode_copy game_mode;
static BOOL mode_set, dinput_wants_mouse, mouse_free, widen_view;
static void *front_swapchain, *front_texture;
static DWORD front_thread;
static unsigned int anisotropy;
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
        say("%s: picture %ux%u drawn into client area %ldx%ld", path,
            game_mode.width, game_mode.height, client->right, client->bottom);
}

static HRESULT __cdecl scaled_present(void *swapchain, const RECT *src, const RECT *dst,
                                      HWND override, unsigned int interval, uint32_t flags)
{
    RECT client;
    HRESULT hr;

    if (picture_target(&client))
    {
        count_scaled(&flips, "flip", &client);
        dst = &client;
    }
    hr = real_present(swapchain, src, dst, override, interval, flags);
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

static HRESULT __cdecl scaled_blt(void *context, void *dst, unsigned int dst_index, const RECT *dst_rect,
                                  void *src, unsigned int src_index, const RECT *src_rect,
                                  unsigned int flags, const void *fx, int filter)
{
    void *back;
    RECT client;
    HRESULT hr;

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
    say("ddraw asked for a %s swapchain of %ux%u; wined3d gets a windowed one",
        desc->windowed ? "windowed" : "fullscreen", desc->backbuffer_width, desc->backbuffer_height);
    desc->windowed = TRUE;
    return real_swapchain_create(device, desc, state_parent, parent, parent_ops, swapchain);
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

static BOOL WINAPI dinput_set_cursor_pos(int x, int y)
{
    InterlockedIncrement(&dinput_moves);
    return SetCursorPos(x, y);
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
    real_sampler_state = (void *)GetProcAddress(wined3d, "wined3d_stateblock_set_sampler_state");
    if (anisotropy > 1 && real_sampler_state
        && !patch_import(ddraw, "wined3d.dll", "wined3d_stateblock_set_sampler_state", sharper_sampler_state))
        say("ddraw.dll does not import wined3d_stateblock_set_sampler_state; textures keep the game's filtering");
    if (!patch_import(dinput, "user32.dll", "ClipCursor", dinput_clip_cursor))
        say("dinput.dll does not import ClipCursor; the mouse is not kept inside the picture");
    if (!patch_import(dinput, "user32.dll", "SetCursorPos", dinput_set_cursor_pos))
        say("dinput.dll does not import SetCursorPos; its pointer moves are not counted");
    return TRUE;
}

static void run_console_command(const char *command)
{
    HMODULE engine = GetModuleHandleA("AfEngine.dll");
    void *(__cdecl *get_main)(void) = (void *)GetProcAddress(engine, "?Get@NfMain@@SAPAV1@XZ");
    void *(__thiscall *get_console)(void *) = (void *)GetProcAddress(engine, "?GetConsole@NfMain@@QAEPAVNfConsole@@XZ");
    void (__cdecl *execute)(void *, const char *, ...) = (void *)GetProcAddress(engine, "?Execute@NfConsole@@QAAXPADZZ");
    void *main;

    if (!get_main || !get_console || !execute || !(main = get_main())) return;
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

static LRESULT CALLBACK hook_proc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp)
{
    if (msg == WIDEN_VIEW)
    {
        widen_view_for(wp, lp);
        return 0;
    }
    if (msg == WM_COPYDATA && ((COPYDATASTRUCT *)lp)->dwData == CONSOLE_COMMAND)
    {
        COPYDATASTRUCT *data = (COPYDATASTRUCT *)lp;
        if (data->cbData && !((const char *)data->lpData)[data->cbData - 1]) run_console_command(data->lpData);
        return TRUE;
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
        if (mac_screen.cx)
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

static void make_normal_window(HWND w)
{
    static BOOL placed;
    DWORD style = GetWindowLongA(w, GWL_STYLE), ex = GetWindowLongA(w, GWL_EXSTYLE);
    BOOL normal = (style & WS_OVERLAPPEDWINDOW) == WS_OVERLAPPEDWINDOW && !(ex & WS_EX_TOPMOST);
    BOOL same_shape = fitted_for.cx && fitted_for.cx * (LONG)game_mode.height == fitted_for.cy * (LONG)game_mode.width;
    RECT client = { 0 }, frame;
    SIZE size;

    if (!game_mode.width || !game_mode.height || (normal && same_shape)) return;
    if (IsIconic(w) || IsZoomed(w)) return;

    GetClientRect(w, &client);
    size.cx = client.right;
    size.cy = client.bottom;
    if (!same_shape)
    {
        size.cx = max_client.cx;
        size.cy = max_client.cx * game_mode.height / game_mode.width;
        if (size.cy > max_client.cy)
        {
            size.cy = max_client.cy;
            size.cx = max_client.cy * game_mode.width / game_mode.height;
        }
    }
    fitted_for.cx = game_mode.width;
    fitted_for.cy = game_mode.height;

    style = (style & ~WS_POPUP) | WS_OVERLAPPEDWINDOW;
    ex &= ~WS_EX_TOPMOST;
    SetRect(&frame, 0, 0, size.cx, size.cy);
    AdjustWindowRectEx(&frame, style, FALSE, ex);
    SetWindowLongA(w, GWL_STYLE, style);
    SetWindowLongA(w, GWL_EXSTYLE, ex);
    SetWindowPos(w, HWND_NOTOPMOST, 0, 0, frame.right - frame.left, frame.bottom - frame.top,
                 SWP_FRAMECHANGED | SWP_NOACTIVATE | (placed ? SWP_NOMOVE : 0));
    placed = TRUE;

    GetClientRect(w, &client);
    say("picture %ux%u, window client area now %ldx%ld (asked for %ldx%ld), style %08lx",
        game_mode.width, game_mode.height, client.right, client.bottom, size.cx, size.cy,
        (DWORD)GetWindowLongA(w, GWL_STYLE));
}

static void keep_mouse_inside(void)
{
    static BOOL keys_were_down, ours, titled_free;
    static HWND titled;
    static RECT wanted, applied;
    BOOL keys_down = (GetAsyncKeyState(VK_CONTROL) & 0x8000) && (GetAsyncKeyState(VK_MENU) & 0x8000);
    BOOL front = game_window && GetForegroundWindow() == game_window && !IsIconic(game_window);
    RECT client = { 0 }, now = { 0 };

    if (!front) mouse_free = FALSE;
    else if (keys_down && !keys_were_down)
    {
        mouse_free = !mouse_free;
        say("Ctrl+Option: the mouse %s; so far DirectInput asked %ld times to hold it and moved the pointer itself %ld times",
            mouse_free ? "is free" : "belongs to the game again", dinput_clips, dinput_moves);
    }
    keys_were_down = keys_down;

    if (front && dinput_wants_mouse && !mouse_free && GetClientRect(game_window, &client) && client.right)
    {
        MapWindowPoints(game_window, NULL, (POINT *)&client, 2);
        GetClipCursor(&now);
        if (!ours || !EqualRect(&client, &wanted) || !EqualRect(&now, &applied))
        {
            ClipCursor(&client);
            GetClipCursor(&applied);
            if (!ours || !EqualRect(&client, &wanted))
                say("mouse kept inside %ld,%ld %ldx%ld; the picture is at %ld,%ld %ldx%ld",
                    applied.left, applied.top, applied.right - applied.left, applied.bottom - applied.top,
                    client.left, client.top, client.right - client.left, client.bottom - client.top);
            wanted = client;
            ours = TRUE;
        }
    }
    else if (ours)
    {
        ClipCursor(NULL);
        ours = FALSE;
        say("mouse let go");
    }

    if (game_window && mode_set && (titled != game_window || titled_free != mouse_free))
    {
        titled = game_window;
        titled_free = mouse_free;
        SendMessageTimeoutA(game_window, WM_SETTEXT, 0,
                            (LPARAM)(mouse_free ? "Airfix Dogfighter - the mouse is free, Ctrl+Option gives it back"
                                                : "Airfix Dogfighter - Ctrl+Option frees the mouse"),
                            SMTO_ABORTIFHUNG, 500, NULL);
    }
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
        anisotropy = env_size("DOGFIGHTER_ANISOTROPY").cx;
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
        CloseHandle(CreateThread(NULL, 0, watch, NULL, 0, NULL));
    }
    return TRUE;
}
