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

static const char *pointer_place(POINT at)
{
    RECT window = { 0 }, client = { 0 };

    GetWindowRect(game_hwnd, &window);
    GetClientRect(game_hwnd, &client);
    MapWindowPoints(game_hwnd, NULL, (POINT *)&client, 2);
    if (PtInRect(&client, at)) return "in the picture";
    if (PtInRect(&window, at)) return at.y < client.top ? "on the title bar" : "on the window frame";
    return "outside the window";
}

static void note_pointer(void)
{
    POINT at = { 0, 0 };
    RECT clip = { 0 };

    GetCursorPos(&at);
    GetClipCursor(&clip);
    note("window test, the pointer is at %ld,%ld, %s, %s the rectangle it is kept in", at.x, at.y,
         pointer_place(at), PtInRect(&clip, at) ? "inside" : "outside");
}

/* Wine hands these moves to DirectInput but does not move the Mac pointer for
   them, so an unchanged position is the good result: a jump to the middle of
   the picture means DirectInput warped the pointer. GetCursorPos only asks the
   Mac when Wine's own position is older than 100 ms, hence the waits. */
static void push_mouse(int dx, int dy)
{
    INPUT move = { .type = INPUT_MOUSE, .mi.dx = dx / 20, .mi.dy = dy / 20, .mi.dwFlags = MOUSEEVENTF_MOVE };
    POINT from = { 0, 0 }, to = { 0, 0 };
    UINT sent = 0;

    Sleep(300);
    GetCursorPos(&from);
    for (int i = 0; i < 20; i++)
    {
        sent += SendInput(1, &move, sizeof(INPUT));
        Sleep(25);
    }
    Sleep(300);
    GetCursorPos(&to);
    note("window test, %u mouse moves adding up to %d,%d: the pointer went from %ld,%ld (%s) to %ld,%ld (%s)",
         sent, dx / 20 * 20, dy / 20 * 20, from.x, from.y, pointer_place(from), to.x, to.y, pointer_place(to));
}

static void put_pointer_on_title_bar(void)
{
    RECT window = { 0 };

    GetWindowRect(game_hwnd, &window);
    note("window test, putting the pointer on the title bar at %ld,%ld: %d", window.left + 400, window.top + 14,
         SetCursorPos(window.left + 400, window.top + 14));
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

static void note_window(const char *when)
{
    RECT window = { 0 }, client = { 0 }, clip = { 0 };

    GetWindowRect(game_hwnd, &window);
    GetClientRect(game_hwnd, &client);
    MapWindowPoints(game_hwnd, NULL, (POINT *)&client, 2);
    GetClipCursor(&clip);
    note("move test, %s: window at %ld,%ld %ldx%ld, picture at %ld,%ld %ldx%ld, mouse kept inside %ld,%ld %ldx%ld", when,
         window.left, window.top, window.right - window.left, window.bottom - window.top,
         client.left, client.top, client.right - client.left, client.bottom - client.top,
         clip.left, clip.top, clip.right - clip.left, clip.bottom - clip.top);
}

static BOOL move_test_step(int step)
{
    RECT window = { 0 }, client = { 0 };

    switch (step)
    {
    case 0:
        note_window("at the start");
        press_ctrl_option();
        break;
    case 2:
        note_window("after Ctrl+Option");
        GetWindowRect(game_hwnd, &window);
        SendMessageTimeoutA(game_hwnd, WM_ENTERSIZEMOVE, 0, 0, SMTO_ABORTIFHUNG, 2000, NULL);
        for (int i = 1; i <= 4; i++)
        {
            SetWindowPos(game_hwnd, NULL, window.left + 40 * i, window.top + 25 * i, 0, 0,
                         SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE);
            Sleep(100);
        }
        SendMessageTimeoutA(game_hwnd, WM_EXITSIZEMOVE, 0, 0, SMTO_ABORTIFHUNG, 2000, NULL);
        note_window("right after a move by 160,100");
        break;
    case 5:
        note_window("3 seconds after the move");
        GetClientRect(game_hwnd, &client);
        PostMessageA(game_hwnd, WM_LBUTTONDOWN, MK_LBUTTON, MAKELPARAM(client.right / 2, client.bottom - 20));
        PostMessageA(game_hwnd, WM_LBUTTONUP, 0, MAKELPARAM(client.right / 2, client.bottom - 20));
        note("move test, sent a click message for the picture");
        break;
    case 7:
        note_window("after the click in the picture");
        break;
    case 8:
        end_game("move test finished");
        return FALSE;
    }
    return TRUE;
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
        put_pointer_on_title_bar();
        push_mouse(-100, 0);
        push_mouse(0, 300);
        push_mouse(-4000, -4000);
        put_pointer_on_title_bar();
        break;
    case 11:
        note("window test, pressing Ctrl+Option to give the mouse back");
        press_ctrl_option();
        break;
    case 13:
        note_pointer();
        push_mouse(4000, 4000);
        push_mouse(-8000, -8000);
        put_pointer_on_title_bar();
        Sleep(300);
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

static void drag_test(void)
{
    static const struct { const char *what; WPARAM corner; int left, top, right, bottom; } drags[] =
    {
        { "bottom edge 120 down", WMSZ_BOTTOMRIGHT, 0, 0, 0, 120 },
        { "bottom edge 120 up", WMSZ_BOTTOMRIGHT, 0, 0, 0, -120 },
        { "right edge 160 out", WMSZ_BOTTOMRIGHT, 0, 0, 160, 0 },
        { "left edge 160 out", WMSZ_BOTTOMLEFT, -160, 0, 0, 0 },
        { "top edge 120 up", WMSZ_TOPRIGHT, 0, -120, 0, 0 },
        { "bottom right corner 200,40 out", WMSZ_BOTTOMRIGHT, 0, 0, 200, 40 },
        { "top left corner 40,150 out", WMSZ_TOPLEFT, -40, -150, 0, 0 },
    };

    for (unsigned int i = 0; i < ARRAYSIZE(drags); i++)
    {
        RECT window = { 0 }, asked, client = { 0 };
        LRESULT answered;

        GetWindowRect(game_hwnd, &window);
        SetRect(&asked, window.left + drags[i].left, window.top + drags[i].top,
                window.right + drags[i].right, window.bottom + drags[i].bottom);
        window = asked;
        answered = SendMessageA(game_hwnd, WM_SIZING, drags[i].corner, (LPARAM)&window);
        SetWindowPos(game_hwnd, NULL, window.left, window.top, window.right - window.left, window.bottom - window.top,
                     SWP_NOZORDER | SWP_NOACTIVATE);
        Sleep(300);
        GetClientRect(game_hwnd, &client);
        note("drag test, %s: asked for a window of %ldx%ld, answer %ld with %ldx%ld, client area now %ldx%ld",
             drags[i].what, asked.right - asked.left, asked.bottom - asked.top, (long)answered,
             window.right - window.left, window.bottom - window.top, client.right, client.bottom);
    }
}

static DWORD seconds_to_ms(const char *text, char **end)
{
    return (DWORD)(strtod(text, end) * 1000 + 0.5);
}

static DWORD picture_ms(void)
{
    return sized_at ? GetTickCount() - sized_at : 0;
}

enum { TAP_MS = 150 };
static struct { DWORD at, scan, hold, down_at; enum { WAITING, DOWN, DONE } state; } keys[64];
static int key_count;

static void read_keys(const char *list)
{
    char *end;

    while (key_count < 64 && *list)
    {
        keys[key_count].at = seconds_to_ms(list, &end);
        if (end == list || *end != ':') return;
        keys[key_count].scan = strtoul(end + 1, &end, 16);
        keys[key_count].hold = *end == ':' ? seconds_to_ms(end + 1, &end) : 0;
        key_count++;
        list = *end == ',' ? end + 1 : end;
        if (*end != ',') return;
    }
}

/* Codes from 80 up are the extended keys, as DirectInput numbers them: d0 is
   the Down arrow. Windows wants those as the low seven bits plus the extended
   flag. Sent as they are, Wine takes bit 7 for nothing and DirectInput in the
   game never sees the key.
   The extra value tells the helper the key is a scripted one, which it lets
   through while --diag-block-input keeps the player's keys from the game. */
static void send_key(DWORD scan, BOOL down)
{
    INPUT key = { .type = INPUT_KEYBOARD, .ki.wScan = scan & 0x7f, .ki.dwFlags = KEYEVENTF_SCANCODE,
                  .ki.dwExtraInfo = 0x41664464 };

    if (scan & 0x80) key.ki.dwFlags |= KEYEVENTF_EXTENDEDKEY;
    if (!down) key.ki.dwFlags |= KEYEVENTF_KEYUP;
    SendInput(1, &key, sizeof(INPUT));
}

static void work_keys(void)
{
    DWORD now = picture_ms();

    if (!sized_at) return;
    for (int i = 0; i < key_count; i++)
    {
        if (keys[i].state == WAITING && now >= keys[i].at)
        {
            if (keys[i].scan == 0x1d38)
            {
                press_ctrl_option();
                note("pressed Ctrl+Option");
                keys[i].state = DONE;
                continue;
            }
            send_key(keys[i].scan, TRUE);
            keys[i].down_at = now = picture_ms();
            keys[i].state = DOWN;
            if (keys[i].hold) note("holding the key with scan code %02lx down at %.2f s", keys[i].scan, now / 1000.0);
        }
        if (keys[i].state == DOWN && now - keys[i].down_at >= (keys[i].hold ? keys[i].hold : TAP_MS))
        {
            send_key(keys[i].scan, FALSE);
            now = picture_ms();
            keys[i].state = DONE;
            if (keys[i].hold)
                note("let the key with scan code %02lx go at %.2f s, after %.2f s", keys[i].scan, now / 1000.0,
                     (now - keys[i].down_at) / 1000.0);
            else note("pressed the key with scan code %02lx at %.2f s", keys[i].scan, now / 1000.0);
        }
    }
}

static void let_keys_go(void)
{
    for (int i = 0; i < key_count; i++)
        if (keys[i].state == DOWN) send_key(keys[i].scan, FALSE);
}

static struct { DWORD second; int dx, dy; BOOL click, outside; } moves[32];
static int move_count, moves_done;

static void read_moves(const char *list)
{
    int used;

    while (move_count < 32
           && sscanf(list, "%lu:%d:%d%n", &moves[move_count].second, &moves[move_count].dx, &moves[move_count].dy, &used) == 3)
    {
        list += used;
        moves[move_count].outside = !strncmp(list, ":o", 2);
        if ((moves[move_count].click = moves[move_count].outside || !strncmp(list, ":c", 2))) list += 2;
        move_count++;
        if (*list == ',') list++;
    }
}

static void move_mouse(int dx, int dy, BOOL click, BOOL outside)
{
    enum { STEPS = 20 };
    INPUT input = { .type = INPUT_MOUSE, .mi.dwFlags = MOUSEEVENTF_MOVE };
    RECT window = { 0 };
    POINT at = { 0, 0 };

    if (outside && GetWindowRect(game_hwnd, &window))
    {
        SetCursorPos(window.right + 60, window.top + 60);
        Sleep(300);
    }

    for (int i = 0; i < STEPS; i++)
    {
        input.mi.dx = dx * (i + 1) / STEPS - dx * i / STEPS;
        input.mi.dy = dy * (i + 1) / STEPS - dy * i / STEPS;
        SendInput(1, &input, sizeof(INPUT));
        Sleep(15);
    }
    if (click)
    {
        input.mi.dx = input.mi.dy = 0;
        Sleep(300);
        GetCursorPos(&at);
        note("clicking with the system pointer at %ld,%ld, which is %s", at.x, at.y, pointer_place(at));
        input.mi.dwFlags = MOUSEEVENTF_LEFTDOWN;
        SendInput(1, &input, sizeof(INPUT));
        Sleep(150);
        input.mi.dwFlags = MOUSEEVENTF_LEFTUP;
        SendInput(1, &input, sizeof(INPUT));
    }
    note("moved the mouse by %d,%d%s", dx, dy, click ? " and clicked" : "");
}

static struct { DWORD at; char text[200]; } commands[64];
static int command_count, commands_sent;

/* "+" is a space and "++" is a "+". In an odd run of them the first is the
   space, so "bind+x+++fire" is "bind x +fire". */
static void read_command(const char *arg)
{
    char *end, *to, *last;
    BOOL as_written;

    if (command_count == 64) return;
    commands[command_count].at = seconds_to_ms(arg, &end);
    if (end == arg || *end != ':') return;
    as_written = strchr(end, '/') != NULL;
    to = commands[command_count].text;
    last = to + sizeof(commands[0].text) - 1;
    for (const char *c = end + 1; *c && to < last; )
    {
        size_t run = as_written ? 0 : strspn(c, "+");

        if (!run) { *to++ = *c == '/' ? ' ' : *c; c++; continue; }
        c += run;
        if (run % 2) *to++ = ' ';
        for (run /= 2; run && to < last; run--) *to++ = '+';
    }
    *to = 0;
    command_count++;
}

/* FALSE when the helper wants the command again later: the game is still in
   its intro videos, where starting a mission ends it on Mach9. */
static BOOL send_command(char *text)
{
    enum { LATER = 2 };
    static BOOL waiting;
    static DWORD asked_at;
    COPYDATASTRUCT data = { 0x41664463, strlen(text) + 1, text };
    DWORD_PTR taken = 0;
    DWORD at = picture_ms();

    if (waiting && GetTickCount() - asked_at < 500) return FALSE;
    SendMessageTimeoutA(game_hwnd, WM_COPYDATA, 0, (LPARAM)&data, SMTO_ABORTIFHUNG, 5000, &taken);
    if (taken == LATER)
    {
        if (!waiting) note("console command for the game: %s: waits until the game is in its main menu", text);
        waiting = TRUE;
        asked_at = GetTickCount();
        return FALSE;
    }
    waiting = FALSE;
    note("console command for the game at %.2f s: %s: %s", at / 1000.0, text, taken ? "run" : "not taken");
    return TRUE;
}

static void work_commands(void)
{
    while (sized_at && commands_sent < command_count && picture_ms() >= commands[commands_sent].at
           && send_command(commands[commands_sent].text))
        commands_sent++;
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
    BOOL seen = FALSE, window_test = FALSE, move_test = FALSE, start_test = FALSE, press_ok = FALSE, press_cancel = FALSE;
    DWORD start = GetTickCount(), wait = 10, end_after = 0, zoom_at = 0, drag_at = 0;
    int next_step = 0;

    logf = fopen("C:\\dogfighter-windiag.log", "w");
    if (!logf) return 1;
    note("sound: Wine offers %u devices to play on", waveOutGetNumDevs());
    if (GetEnvironmentVariableA("DOGFIGHTER_DRAWTEST", NULL, 0))
    {
        draw_test();
        return 0;
    }
    for (int i = 1; i < argc; i++)
    {
        if (!strcmp(argv[i], "focus-test")) window_test = TRUE;
        if (!strcmp(argv[i], "move-test")) move_test = TRUE;
        if (!strcmp(argv[i], "start-test")) start_test = TRUE;
        if (!strcmp(argv[i], "press-ok")) press_ok = TRUE;
        if (!strcmp(argv[i], "press-cancel")) press_cancel = TRUE;
        if (!strncmp(argv[i], "wait=", 5)) wait = atoi(argv[i] + 5);
        if (!strncmp(argv[i], "end=", 4)) end_after = atoi(argv[i] + 4);
        if (!strncmp(argv[i], "zoom=", 5)) zoom_at = atoi(argv[i] + 5);
        if (!strncmp(argv[i], "drag=", 5)) drag_at = atoi(argv[i] + 5);
        if (!strncmp(argv[i], "keys=", 5)) read_keys(argv[i] + 5);
        if (!strncmp(argv[i], "mouse=", 6)) read_moves(argv[i] + 6);
        if (!strncmp(argv[i], "console=", 8)) read_command(argv[i] + 8);
    }

    for (;;)
    {
        game = game_pid();
        if (game) seen = TRUE;
        else if (seen || GetTickCount() - start > 30000) break;

        HWND setup = press_ok || press_cancel ? FindWindowA("#32770", "Airfix Dogfighter setup") : NULL;
        if (setup && IsWindowVisible(setup))
        {
            PostMessageA(setup, WM_COMMAND, press_ok ? IDOK : IDCANCEL, 0);
            note("pressed %s in the game's setup dialog", press_ok ? "OK" : "Cancel");
            press_ok = press_cancel = FALSE;
        }

        DWORD shown = sized_at ? (GetTickCount() - sized_at) / 1000 : 0;
        if (start_test && shown >= 8)
        {
            end_game("start test, the game drew for 8 seconds");
            start_test = FALSE;
        }
        if (end_after && shown >= end_after)
        {
            end_game("the test run's time is up");
            end_after = 0;
        }
        if (zoom_at && shown >= zoom_at)
        {
            note("zooming the window");
            ShowWindowAsync(game_hwnd, SW_MAXIMIZE);
            zoom_at = 0;
        }
        if (drag_at && shown >= drag_at)
        {
            drag_test();
            drag_at = 0;
        }
        while (moves_done < move_count && shown >= moves[moves_done].second)
        {
            move_mouse(moves[moves_done].dx, moves[moves_done].dy, moves[moves_done].click, moves[moves_done].outside);
            moves_done++;
        }
        while (window_test && shown >= wait && (int)(shown - wait) >= next_step)
            window_test = window_test_step(next_step++);
        while (move_test && shown >= wait && (int)(shown - wait) >= next_step)
            move_test = move_test_step(next_step++);

        snapshot();
        if (strcmp(now, before))
        {
            fprintf(logf, "windiag: +%.1fs\n%s", (GetTickCount() - start) / 1000.0, now);
            fflush(logf);
            memcpy(before, now, sizeof(now));
        }
        for (int i = 0; i < 25; i++)
        {
            work_keys();
            work_commands();
            Sleep(20);
        }
    }
    let_keys_go();
    note("game gone");
    fclose(logf);
    return 0;
}
