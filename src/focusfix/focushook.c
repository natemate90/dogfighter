#include <windows.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef HRESULT (__cdecl *present_fn)(void *swapchain, const RECT *src, const RECT *dst,
                                      HWND override, unsigned int interval, uint32_t flags);
typedef void *(__cdecl *front_buffer_fn)(void *swapchain);

static WNDPROC game_proc, next_proc;
static HWND game_window;
static HWND (WINAPI *real_foreground)(void);
static HRESULT (__cdecl *real_set_display_mode)(void *output, const UINT *wanted);
static present_fn real_present;
static front_buffer_fn real_front_buffer;
static FILE *logf;
static SIZE max_client, mac_screen, want, mode;
static volatile LONG own_move, presents, front_draws;

static void say(const char *fmt, ...)
{
    va_list args;
    if (!logf) return;
    va_start(args, fmt);
    fprintf(logf, "focushook: ");
    vfprintf(logf, fmt, args);
    fprintf(logf, "\n");
    fflush(logf);
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

static HRESULT __cdecl present_to_whole_window(void *swapchain, const RECT *src, const RECT *dst,
                                               HWND override, unsigned int interval, uint32_t flags)
{
    RECT client;
    LONG count = InterlockedIncrement(&presents);

    if (game_window && GetClientRect(game_window, &client) && client.right > 0 && client.bottom > 0)
    {
        if (count <= 3)
            say("frame %ld: picture %ldx%ld drawn into client area %ldx%ld", count,
                src ? src->right - src->left : 0, src ? src->bottom - src->top : 0, client.right, client.bottom);
        dst = &client;
    }
    return real_present(swapchain, src, dst, override, interval, flags);
}

static HWND WINAPI game_is_foreground(void)
{
    return game_window ? game_window : real_foreground();
}

static void *__cdecl counted_front_buffer(void *swapchain)
{
    LONG count = InterlockedIncrement(&front_draws);
    if (count <= 3 || count % 3600 == 0)
        say("front buffer drawn directly, not scaled (%ld times)", count);
    return real_front_buffer(swapchain);
}

static BOOL patch_import(HMODULE module, const char *dll, const char *name, void *replacement, void **original)
{
    BYTE *base = (BYTE *)module;
    IMAGE_NT_HEADERS *nt = (IMAGE_NT_HEADERS *)(base + ((IMAGE_DOS_HEADER *)base)->e_lfanew);
    IMAGE_DATA_DIRECTORY *dir = &nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT];
    void *target = GetProcAddress(GetModuleHandleA(dll), name);
    DWORD old;

    if (!dir->VirtualAddress || !target) return FALSE;
    for (IMAGE_IMPORT_DESCRIPTOR *imp = (IMAGE_IMPORT_DESCRIPTOR *)(base + dir->VirtualAddress); imp->Name; imp++)
    {
        if (lstrcmpiA((const char *)base + imp->Name, dll)) continue;
        for (void **slot = (void **)(base + imp->FirstThunk); slot[0]; slot++)
        {
            if (slot[0] != target) continue;
            if (!VirtualProtect(slot, sizeof(void *), PAGE_READWRITE, &old)) return FALSE;
            original[0] = target;
            slot[0] = replacement;
            VirtualProtect(slot, sizeof(void *), old, &old);
            return TRUE;
        }
    }
    return FALSE;
}

static void fit_to_mode(void)
{
    want.cx = max_client.cx;
    want.cy = max_client.cx * mode.cy / mode.cx;
    if (want.cy > max_client.cy)
    {
        want.cy = max_client.cy;
        want.cx = max_client.cy * mode.cx / mode.cy;
    }
}

static HRESULT __cdecl logged_set_display_mode(void *output, const UINT *wanted)
{
    HRESULT hr = real_set_display_mode(output, wanted);
    if (wanted) say("ddraw set the display mode to %ux%u: %08lx", wanted[0], wanted[1], hr);
    else say("ddraw restored the display mode: %08lx", hr);
    return hr;
}

static LRESULT CALLBACK hook_proc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp)
{
    if (msg == WM_ACTIVATEAPP || msg == WM_ACTIVATE || msg == WM_KILLFOCUS || msg == WM_SETFOCUS
        || msg == WM_DISPLAYCHANGE)
        say("message %s wp=%lx lp=%lx", msg == WM_ACTIVATEAPP ? "WM_ACTIVATEAPP" : msg == WM_ACTIVATE ? "WM_ACTIVATE"
            : msg == WM_KILLFOCUS ? "WM_KILLFOCUS" : msg == WM_SETFOCUS ? "WM_SETFOCUS" : "WM_DISPLAYCHANGE",
            (DWORD)wp, (DWORD)lp);
    if ((msg == WM_ACTIVATEAPP && !wp) || (msg == WM_ACTIVATE && !LOWORD(wp)) || msg == WM_KILLFOCUS)
        return 0;
    if (msg == WM_ACTIVATEAPP)
        return CallWindowProcA(game_proc, hwnd, msg, wp, lp);

    if (max_client.cx && msg == WM_WINDOWPOSCHANGING && !own_move)
    {
        WINDOWPOS *pos = (WINDOWPOS *)lp;
        if (!(pos->flags & SWP_NOSIZE) && pos->cx == mode.cx && pos->cy == mode.cy)
            pos->flags |= SWP_NOSIZE | SWP_NOMOVE;
        if (pos->hwndInsertAfter == HWND_TOPMOST) pos->flags |= SWP_NOZORDER;
    }

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
    if (max_client.cx && msg == WM_SIZE && wp != SIZE_MINIMIZED && !own_move
        && (GetWindowLongA(hwnd, GWL_STYLE) & WS_CAPTION) == WS_CAPTION && LOWORD(lp) && HIWORD(lp))
    {
        want.cx = LOWORD(lp);
        want.cy = HIWORD(lp);
    }
    return result;
}

static void make_normal_window(HWND w)
{
    static BOOL placed;
    DWORD style = GetWindowLongA(w, GWL_STYLE), ex = GetWindowLongA(w, GWL_EXSTYLE);
    SIZE now = { GetSystemMetrics(SM_CXSCREEN), GetSystemMetrics(SM_CYSCREEN) };
    RECT client, frame;

    if (!GetClientRect(w, &client) || !client.right || !now.cx || !now.cy) return;
    if (now.cx != mode.cx || now.cy != mode.cy)
    {
        mode = now;
        fit_to_mode();
    }
    else if ((style & WS_OVERLAPPEDWINDOW) == WS_OVERLAPPEDWINDOW && !(ex & WS_EX_TOPMOST)
             && client.right == want.cx && client.bottom == want.cy)
        return;
    if (IsIconic(w) || IsZoomed(w)) return;

    style = (style & ~WS_POPUP) | WS_OVERLAPPEDWINDOW;
    ex &= ~WS_EX_TOPMOST;
    SetRect(&frame, 0, 0, want.cx, want.cy);
    AdjustWindowRectEx(&frame, style, FALSE, ex);

    InterlockedExchange(&own_move, 1);
    SetWindowLongA(w, GWL_STYLE, style);
    SetWindowLongA(w, GWL_EXSTYLE, ex);
    SetWindowPos(w, HWND_NOTOPMOST, 0, 0, frame.right - frame.left, frame.bottom - frame.top,
                 SWP_FRAMECHANGED | SWP_NOACTIVATE | (placed ? SWP_NOMOVE : 0));
    InterlockedExchange(&own_move, 0);
    placed = TRUE;

    GetClientRect(w, &client);
    say("display mode %ldx%ld, window client area now %ldx%ld (asked for %ldx%ld), style %08lx",
        mode.cx, mode.cy, client.right, client.bottom, want.cx, want.cy, (DWORD)GetWindowLongA(w, GWL_STYLE));
}

static DWORD WINAPI watch(void *arg)
{
    DWORD pid = GetCurrentProcessId(), owner, ticks = 0;
    LONG reported = 0;

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
        }
        if (max_client.cx && ++ticks % 50 == 0 && presents != reported)
        {
            RECT client = { 0 };
            if (game_window) GetClientRect(game_window, &client);
            say("%ld frames drawn so far, client area %ldx%ld", presents, client.right, client.bottom);
            reported = presents;
        }
        Sleep(100);
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
        if (max_client.cx && max_client.cy)
        {
            HMODULE ddraw = GetModuleHandleA("ddraw.dll");
            logf = fopen("C:\\dogfighter-focushook.log", "w");
            if (!ddraw || !patch_import(ddraw, "wined3d.dll", "wined3d_swapchain_present",
                                        present_to_whole_window, (void **)&real_present))
            {
                say("could not hook wined3d_swapchain_present; the picture is not scaled");
                max_client.cx = 0;
            }
            else
            {
                patch_import(ddraw, "wined3d.dll", "wined3d_swapchain_get_front_buffer",
                             counted_front_buffer, (void **)&real_front_buffer);
                patch_import(ddraw, "wined3d.dll", "wined3d_output_set_display_mode",
                             logged_set_display_mode, (void **)&real_set_display_mode);
                patch_import(ddraw, "user32.dll", "GetForegroundWindow",
                             game_is_foreground, (void **)&real_foreground);
                say("scaling the picture into a window of up to %ldx%ld", max_client.cx, max_client.cy);
            }
        }
        CloseHandle(CreateThread(NULL, 0, watch, NULL, 0, NULL));
    }
    return TRUE;
}
