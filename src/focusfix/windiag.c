#include <windows.h>
#include <tlhelp32.h>
#include <stdarg.h>
#include <stdio.h>
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

static BOOL accept_setup, focus_test;
static DWORD sized_at;
static HWND setup_dialog;
static DWORD game;

static BOOL CALLBACK add_window(HWND w, LPARAM depth)
{
    char cls[64] = "", title[64] = "";
    RECT wr = { 0 }, cr = { 0 };
    DWORD pid = 0;

    if (!depth && !IsWindowVisible(w)) return TRUE;
    GetClassNameA(w, cls, sizeof(cls));
    GetWindowTextA(w, title, sizeof(title));
    GetWindowThreadProcessId(w, &pid);
    for (char *c = title; *c; c++) if (*c < 32 || *c > 126) *c = '?';
    if (!depth && w != setup_dialog && !strcmp(cls, "#32770") && title[0] && pid == game)
    {
        setup_dialog = w;
        add("  crash logger %s\n", load_crashlog(pid) ? "loaded" : "not loaded");
        if (accept_setup)
        {
            Sleep(1000);
            PostMessageA(w, WM_COMMAND, IDOK, 0);
            add("  pressed OK in the setup dialog\n");
        }
    }
    GetWindowRect(w, &wr);
    GetClientRect(w, &cr);
    if (!depth && !sized_at && cr.right && pid == game && !strcmp(cls, "AirfixClass")) sized_at = GetTickCount();
    add("%s%p pid=%lx class=%s title=\"%s\" style=%08lx ex=%08lx window=%ld,%ld %ldx%ld client=%ldx%ld%s%s%s\n",
        depth ? "    child " : "  ", (void *)w, pid, cls, title,
        (DWORD)GetWindowLongA(w, GWL_STYLE), (DWORD)GetWindowLongA(w, GWL_EXSTYLE),
        wr.left, wr.top, wr.right - wr.left, wr.bottom - wr.top, cr.right, cr.bottom,
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

int main(int argc, char **argv)
{
    BOOL seen = FALSE;
    DWORD start = GetTickCount();

    HWND thief = NULL;

    for (int i = 1; i < argc; i++)
    {
        if (!strcmp(argv[i], "accept-setup")) accept_setup = TRUE;
        if (!strcmp(argv[i], "focus-test")) focus_test = TRUE;
    }

    logf = fopen("C:\\dogfighter-windiag.log", "w");
    if (!logf) return 1;
    for (;;)
    {
        game = game_pid();
        if (game) seen = TRUE;
        else if (seen || GetTickCount() - start > 30000) break;

        if (focus_test && sized_at && !thief && GetTickCount() - sized_at > 15000)
        {
            thief = CreateWindowExA(0, "Static", "windiag focus test", WS_POPUP | WS_VISIBLE,
                                    40, 80, 240, 60, NULL, NULL, NULL, NULL);
            fprintf(logf, "windiag: focus test, took the foreground: %d\n", SetForegroundWindow(thief));
        }
        if (thief && focus_test && GetTickCount() - sized_at > 20000)
        {
            DestroyWindow(thief);
            focus_test = FALSE;
            fprintf(logf, "windiag: focus test, gave the foreground back\n");
        }

        snapshot();
        if (strcmp(now, before))
        {
            fprintf(logf, "windiag: +%.1fs\n%s", (GetTickCount() - start) / 1000.0, now);
            fflush(logf);
            memcpy(before, now, sizeof(now));
        }
        Sleep(500);
    }
    fprintf(logf, "windiag: game gone\n");
    fclose(logf);
    return 0;
}
