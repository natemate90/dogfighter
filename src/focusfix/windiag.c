#include <windows.h>
#include <ddraw.h>
#include <tlhelp32.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static FILE *logf;
static char now[16384], before[16384];
static size_t used;

static void add(const char *fmt, ...)
{
    va_list args;
    va_start(args, fmt);
    if (used < sizeof(now))
        used += vsnprintf(now + used, sizeof(now) - used, fmt, args);
    va_end(args);
}

static void note(const char *fmt, ...)
{
    va_list args;
    va_start(args, fmt);
    fprintf(logf, "windiag: ");
    vfprintf(logf, fmt, args);
    fprintf(logf, "\n");
    fflush(logf);
    va_end(args);
}

static DWORD game_pid(void)
{
    PROCESSENTRY32 entry = { sizeof(entry) };
    DWORD pid = 0;
    HANDLE snap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    if (snap == INVALID_HANDLE_VALUE) return 0;
    if (Process32First(snap, &entry))
        do if (!lstrcmpiA(entry.szExeFile, "Dogfighter.exe")) pid = entry.th32ProcessID;
        while (!pid && Process32Next(snap, &entry));
    CloseHandle(snap);
    return pid;
}

static BOOL load_crashlog(DWORD pid)
{
    static const char path[] = "C:\\dogfighter-crashlog.dll";
    HANDLE process = OpenProcess(PROCESS_ALL_ACCESS, FALSE, pid);
    if (!process) return FALSE;
    void *remote = VirtualAllocEx(process, NULL, sizeof(path), MEM_COMMIT, PAGE_READWRITE);
    HANDLE thread = NULL;
    if (remote && WriteProcessMemory(process, remote, path, sizeof(path), NULL))
        thread = CreateRemoteThread(process, NULL, 0, (LPTHREAD_START_ROUTINE)(void *)
            GetProcAddress(GetModuleHandleA("kernel32.dll"), "LoadLibraryA"), remote, 0, NULL);
    if (thread) CloseHandle(thread);
    CloseHandle(process);
    return thread != NULL;
}

static DWORD sized_at, game, crashlog_pid;
static HWND game_hwnd;

static BOOL CALLBACK add_window(HWND w, LPARAM depth)
{
    char cls[64] = "", title[64] = "";
    RECT wr = { 0 }, cr = { 0 };
    POINT origin = { 0, 0 };
    DWORD pid = 0;

    if (!depth && !IsWindowVisible(w)) return TRUE;
    GetClassNameA(w, cls, sizeof(cls));
    GetWindowTextA(w, title, sizeof(title));
    GetWindowThreadProcessId(w, &pid);
    for (char *c = title; *c; c++) if (*c < 32 || *c > 126) *c = '?';
    GetWindowRect(w, &wr);
    GetClientRect(w, &cr);
    ClientToScreen(w, &origin);
    if (!depth && pid == game && !strcmp(cls, "AirfixClass"))
    {
        game_hwnd = w;
        if (!sized_at && cr.right) sized_at = GetTickCount();
    }
    if (!depth && pid == game && crashlog_pid != pid
        && ((!strcmp(cls, "#32770") && title[0]) || (w == game_hwnd && cr.right)))
    {
        crashlog_pid = pid;
        add("  crash logger %s\n", load_crashlog(pid) ? "loaded" : "not loaded");
    }
    add("%s%p pid=%lx class=%s title=\"%s\" style=%08lx ex=%08lx window=%ld,%ld %ldx%ld client=%ldx%ld at %ld,%ld%s%s%s\n",
        depth ? "    child " : "  ", (void *)w, pid, cls, title,
        (DWORD)GetWindowLongA(w, GWL_STYLE), (DWORD)GetWindowLongA(w, GWL_EXSTYLE),
        wr.left, wr.top, wr.right - wr.left, wr.bottom - wr.top, cr.right, cr.bottom, origin.x, origin.y,
        IsWindowVisible(w) ? "" : " hidden", IsIconic(w) ? " minimized" : "",
        IsHungAppWindow(w) ? " not-responding" : "");
    if (!depth) EnumChildWindows(w, add_window, 1);
    return TRUE;
}

static void snapshot(void)
{
    DEVMODEA mode = { .dmSize = sizeof(mode) };
    CURSORINFO cursor = { sizeof(cursor) };
    char cls[64] = "";
    HWND front = GetForegroundWindow();
    RECT clip = { 0 };

    used = 0;
    now[0] = 0;
    EnumDisplaySettingsA(NULL, ENUM_CURRENT_SETTINGS, &mode);
    GetCursorInfo(&cursor);
    if (front) GetClassNameA(front, cls, sizeof(cls));
    GetClipCursor(&clip);
    add("display=%lux%lu@%lubpp foreground=%p(%s) cursor=%s, kept inside %ld,%ld %ldx%ld\n",
        mode.dmPelsWidth, mode.dmPelsHeight, mode.dmBitsPerPel,
        (void *)front, cls, cursor.flags & CURSOR_SHOWING ? "shown" : "hidden",
        clip.left, clip.top, clip.right - clip.left, clip.bottom - clip.top);
    EnumWindows(add_window, 0);
}

static void press_ctrl_option(void)
{
    INPUT keys[2] = { { .type = INPUT_KEYBOARD, .ki.wVk = VK_CONTROL }, { .type = INPUT_KEYBOARD, .ki.wVk = VK_MENU } };

    SendInput(2, keys, sizeof(INPUT));
    Sleep(300);
    keys[0].ki.dwFlags = keys[1].ki.dwFlags = KEYEVENTF_KEYUP;
    SendInput(2, keys, sizeof(INPUT));
}

static void note_pointer(void)
{
    POINT at = { 0, 0 };
    RECT clip = { 0 };

    GetCursorPos(&at);
    GetClipCursor(&clip);
    note("window test, the pointer is at %ld,%ld, %s the rectangle it is kept in", at.x, at.y,
         PtInRect(&clip, at) ? "inside" : "outside");
}

static void resize_client(int width, int height)
{
    RECT frame = { 0, 0, width, height };

    AdjustWindowRectEx(&frame, GetWindowLongA(game_hwnd, GWL_STYLE), FALSE, GetWindowLongA(game_hwnd, GWL_EXSTYLE));
    SetWindowPos(game_hwnd, NULL, 0, 0, frame.right - frame.left, frame.bottom - frame.top,
                 SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE);
}

static void end_game(const char *why)
{
    HANDLE process = OpenProcess(PROCESS_TERMINATE, FALSE, game);
    note("%s; ending the game: %d", why, process && TerminateProcess(process, 0));
    if (process) CloseHandle(process);
}

static BOOL window_test_step(int step)
{
    static HWND thief;

    switch (step)
    {
    case 0:
        thief = CreateWindowExA(0, "Static", "windiag focus test", WS_POPUP | WS_VISIBLE,
                                40, 80, 240, 60, NULL, NULL, NULL, NULL);
        note("window test, another window took the foreground: %d", SetForegroundWindow(thief));
        break;
    case 5:
        DestroyWindow(thief);
        note("window test, gave the foreground back");
        break;
    case 8:
        note("window test, pressing Ctrl+Option to free the mouse");
        press_ctrl_option();
        break;
    case 10:
        note_pointer();
        break;
    case 11:
        note("window test, pressing Ctrl+Option to give the mouse back");
        press_ctrl_option();
        break;
    case 13:
        note_pointer();
        break;
    case 14:
        note("window test, resizing the window to a 800x600 picture");
        resize_client(800, 600);
        break;
    case 17:
        note_pointer();
        note("window test, zooming the window");
        ShowWindowAsync(game_hwnd, SW_MAXIMIZE);
        break;
    case 20:
        note_pointer();
        note("window test, restoring the window");
        ShowWindowAsync(game_hwnd, SW_RESTORE);
        break;
    case 23:
        end_game("window test finished");
        return FALSE;
    }
    return TRUE;
}

static struct { DWORD second, scan; } keys[32];
static int key_count, keys_pressed;

static void read_keys(const char *list)
{
    int used;

    while (key_count < 32 && sscanf(list, "%lu:%lx%n", &keys[key_count].second, &keys[key_count].scan, &used) == 2)
    {
        key_count++;
        list += used;
        if (*list == ',') list++;
    }
}

static void press_key(DWORD scan)
{
    INPUT key = { .type = INPUT_KEYBOARD, .ki.wScan = scan, .ki.dwFlags = KEYEVENTF_SCANCODE };

    SendInput(1, &key, sizeof(INPUT));
    Sleep(150);
    key.ki.dwFlags |= KEYEVENTF_KEYUP;
    SendInput(1, &key, sizeof(INPUT));
    note("pressed the key with scan code %02lx", scan);
}

static struct { DWORD second; char text[200]; } commands[8];
static int command_count, commands_sent;

static void read_command(const char *arg)
{
    int used = 0;

    if (command_count == 8 || sscanf(arg, "%lu:%n", &commands[command_count].second, &used) != 1 || !used) return;
    snprintf(commands[command_count].text, sizeof(commands[0].text), "%s", arg + used);
    for (char *c = commands[command_count].text; *c; c++) if (*c == '+') *c = ' ';
    command_count++;
}

static void send_command(char *text)
{
    COPYDATASTRUCT data = { 0x41664463, strlen(text) + 1, text };
    DWORD_PTR taken = 0;

    SendMessageTimeoutA(game_hwnd, WM_COPYDATA, 0, (LPARAM)&data, SMTO_ABORTIFHUNG, 5000, &taken);
    note("console command for the game: %s: %s", text, taken ? "run" : "not taken");
}

static void draw_test(void)
{
    WNDCLASSA cls = { .lpfnWndProc = DefWindowProcA, .hInstance = GetModuleHandleA(NULL), .lpszClassName = "AirfixClass" };
    DDSURFACEDESC2 desc = { .dwSize = sizeof(desc), .dwFlags = DDSD_CAPS, .ddsCaps.dwCaps = DDSCAPS_PRIMARYSURFACE };
    DDSURFACEDESC2 locked = { .dwSize = sizeof(locked) };
    DDBLTFX fill = { .dwSize = sizeof(fill) };
    IDirectDraw7 *ddraw = NULL;
    IDirectDrawSurface7 *primary = NULL;
    LONG blts = 0, locks = 0, failed = 0;
    HRESULT hr;
    HWND window;
    MSG msg;

    RegisterClassA(&cls);
    window = CreateWindowExA(0, "AirfixClass", "Airfix Dogfighter", WS_POPUP | WS_VISIBLE, 0, 0, 0, 0,
                             NULL, NULL, cls.hInstance, NULL);
    hr = DirectDrawCreateEx(NULL, (void **)&ddraw, &IID_IDirectDraw7, NULL);
    if (SUCCEEDED(hr)) hr = IDirectDraw7_SetCooperativeLevel(ddraw, window, DDSCL_EXCLUSIVE | DDSCL_FULLSCREEN);
    if (SUCCEEDED(hr)) hr = IDirectDraw7_SetDisplayMode(ddraw, 640, 480, 16, 0, 0);
    if (SUCCEEDED(hr)) hr = IDirectDraw7_CreateSurface(ddraw, &desc, &primary, NULL);
    note("draw test: a 640x480 16-bit primary surface without a back buffer: %08lx", hr);
    if (FAILED(hr)) return;

    for (DWORD start = GetTickCount(); GetTickCount() - start < 7000; Sleep(15))
    {
        while (PeekMessageA(&msg, NULL, 0, 0, PM_REMOVE)) DispatchMessageA(&msg);
        fill.dwFillColor = blts * 37;
        hr = IDirectDrawSurface7_Blt(primary, NULL, NULL, NULL, DDBLT_COLORFILL | DDBLT_WAIT, &fill);
        if (FAILED(hr)) failed++;
        blts++;
        if (blts % 8) continue;
        hr = IDirectDrawSurface7_Lock(primary, NULL, &locked, DDLOCK_WAIT, NULL);
        if (SUCCEEDED(hr))
        {
            memset(locked.lpSurface, blts, locked.lPitch * 100);
            hr = IDirectDrawSurface7_Unlock(primary, NULL);
        }
        if (FAILED(hr)) failed++;
        locks++;
    }
    note("draw test: %ld fills and %ld locks of the primary surface, %ld failed", blts, locks, failed);
}

int main(int argc, char **argv)
{
    BOOL seen = FALSE, window_test = FALSE, start_test = FALSE;
    DWORD start = GetTickCount(), wait = 10;
    int next_step = 0;

    logf = fopen("C:\\dogfighter-windiag.log", "w");
    if (!logf) return 1;
    if (GetEnvironmentVariableA("DOGFIGHTER_DRAWTEST", NULL, 0))
    {
        draw_test();
        return 0;
    }
    for (int i = 1; i < argc; i++)
    {
        if (!strcmp(argv[i], "focus-test")) window_test = TRUE;
        if (!strcmp(argv[i], "start-test")) start_test = TRUE;
        if (!strncmp(argv[i], "wait=", 5)) wait = atoi(argv[i] + 5);
        if (!strncmp(argv[i], "keys=", 5)) read_keys(argv[i] + 5);
        if (!strncmp(argv[i], "console=", 8)) read_command(argv[i] + 8);
    }

    for (;;)
    {
        game = game_pid();
        if (game) seen = TRUE;
        else if (seen || GetTickCount() - start > 30000) break;

        DWORD shown = sized_at ? (GetTickCount() - sized_at) / 1000 : 0;
        if (start_test && shown >= 8)
        {
            end_game("start test, the game drew for 8 seconds");
            start_test = FALSE;
        }
        while (keys_pressed < key_count && shown >= keys[keys_pressed].second)
            press_key(keys[keys_pressed++].scan);
        while (commands_sent < command_count && shown >= commands[commands_sent].second)
            send_command(commands[commands_sent++].text);
        while (window_test && shown >= wait && (int)(shown - wait) >= next_step)
            window_test = window_test_step(next_step++);

        snapshot();
        if (strcmp(now, before))
        {
            fprintf(logf, "windiag: +%.1fs\n%s", (GetTickCount() - start) / 1000.0, now);
            fflush(logf);
            memcpy(before, now, sizeof(now));
        }
        Sleep(500);
    }
    note("game gone");
    fclose(logf);
    return 0;
}
