#include <windows.h>
#include <stdio.h>
#include <string.h>

static FILE *logf;

static void say(const char *msg)
{
    if (!logf) return;
    fprintf(logf, "focusfix: %s\n", msg);
    fflush(logf);
}

static BOOL env_is(const char *name, const char *value)
{
    char text[32];
    return GetEnvironmentVariableA(name, text, sizeof(text)) && !strcmp(text, value);
}

static HWND game_window(DWORD pid)
{
    DWORD owner;
    HWND w = FindWindowA("AirfixClass", NULL);
    return w && GetWindowThreadProcessId(w, &owner) && owner == pid ? w : NULL;
}

struct dialog_search
{
    DWORD pid;
    HWND found;
};

static BOOL CALLBACK find_setup_dialog(HWND w, LPARAM param)
{
    struct dialog_search *search = (struct dialog_search *)param;
    char cls[16] = "";
    DWORD owner = 0;

    GetClassNameA(w, cls, sizeof(cls));
    if (IsWindowVisible(w) && !strcmp(cls, "#32770") && GetWindowTextLengthA(w)
        && GetWindowThreadProcessId(w, &owner) && owner == search->pid)
    {
        search->found = w;
        return FALSE;
    }
    return TRUE;
}

static HWND setup_dialog(DWORD pid)
{
    struct dialog_search search = { pid, NULL };
    EnumWindows(find_setup_dialog, (LPARAM)&search);
    return search.found;
}

static BOOL is_drawing(DWORD pid)
{
    RECT client;
    HWND game = game_window(pid);
    return game && GetClientRect(game, &client) && client.right;
}

static BOOL load_hook(HANDLE process)
{
    static const char path[] = "C:\\dogfighter-focushook.dll";
    DWORD loaded = 0;
    void *remote = VirtualAllocEx(process, NULL, sizeof(path), MEM_COMMIT, PAGE_READWRITE);
    if (!remote || !WriteProcessMemory(process, remote, path, sizeof(path), NULL)) return FALSE;

    LPTHREAD_START_ROUTINE load = (LPTHREAD_START_ROUTINE)(void *)
        GetProcAddress(GetModuleHandleA("kernel32.dll"), "LoadLibraryA");
    HANDLE thread = CreateRemoteThread(process, NULL, 0, load, remote, 0, NULL);
    if (!thread) return FALSE;
    WaitForSingleObject(thread, 20000);
    GetExitCodeThread(thread, &loaded);
    CloseHandle(thread);
    return loaded != 0 && loaded != STILL_ACTIVE;
}

static void start_diagnostics(void)
{
    STARTUPINFOA si = { sizeof(si) };
    PROCESS_INFORMATION pi;
    char mode[1024], cmd[1100];

    if (!GetEnvironmentVariableA("DOGFIGHTER_DIAG", mode, sizeof(mode))) return;
    snprintf(cmd, sizeof(cmd), "C:\\dogfighter-windiag.exe %s", mode);
    if (!CreateProcessA(NULL, cmd, NULL, NULL, FALSE, 0, NULL, NULL, &si, &pi))
    {
        say("could not start the diagnostics");
        return;
    }
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
}

int main(int argc, char **argv)
{
    STARTUPINFOA si = { sizeof(si) };
    PROCESS_INFORMATION pi;
    DWORD code = 1;
    char cmd[MAX_PATH + 3], dir[MAX_PATH];

    if (argc != 3) return 2;
    const char *flag = argv[1];

    logf = fopen("C:\\dogfighter-focusfix.log", "w");
    DeleteFileA(flag);
    snprintf(cmd, sizeof(cmd), "\"%s\"", argv[2]);
    snprintf(dir, sizeof(dir), "%s", argv[2]);
    char *slash = strrchr(dir, '\\');
    if (slash) slash[0] = 0;
    if (!CreateProcessA(NULL, cmd, NULL, NULL, FALSE, CREATE_SUSPENDED, NULL, slash ? dir : NULL, &si, &pi))
    {
        say("could not start the game");
        return 1;
    }
    say(load_hook(pi.hProcess) ? "game started with the focus hook loaded"
                               : "game started, but the focus hook could not be loaded");
    ResumeThread(pi.hThread);
    start_diagnostics();

    BOOL accept_setup = env_is("DOGFIGHTER_SETUP", "accept"), started = FALSE;
    DWORD began = GetTickCount();

    while (WaitForSingleObject(pi.hProcess, 100) == WAIT_TIMEOUT)
    {
        if (!started)
        {
            HWND dialog = setup_dialog(pi.dwProcessId);
            if (dialog && accept_setup)
            {
                Sleep(500);
                PostMessageA(dialog, WM_COMMAND, IDOK, 0);
                say("pressed OK in the game's setup dialog");
            }
            started = dialog || is_drawing(pi.dwProcessId);
            if (!started && GetTickCount() - began > 15000)
            {
                say("the game got stuck while starting; ending it");
                TerminateProcess(pi.hProcess, 3);
                break;
            }
        }

        if (GetFileAttributesA(flag) == INVALID_FILE_ATTRIBUTES) continue;
        DeleteFileA(flag);

        HWND game = game_window(pi.dwProcessId);
        if (!game) continue;
        BOOL iconic = IsIconic(game);
        if (!iconic && GetForegroundWindow() == game) continue;

        if (iconic) ShowWindowAsync(game, SW_RESTORE);
        SetForegroundWindow(game);
        say(iconic ? "restored the minimized game window" : "reactivated the game window");
    }

    WaitForSingleObject(pi.hProcess, 5000);
    GetExitCodeProcess(pi.hProcess, &code);
    say(started ? "game exited" : "the game ended before its setup dialog appeared");
    return (int)code;
}
