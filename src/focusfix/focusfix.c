#include <windows.h>
#include <stdio.h>

static FILE *logf;

static void say(const char *msg)
{
    if (!logf) return;
    fprintf(logf, "focusfix: %s\n", msg);
    fflush(logf);
}

static HWND game_window(DWORD pid)
{
    DWORD owner;
    HWND w = FindWindowA("AirfixClass", NULL);
    return w && GetWindowThreadProcessId(w, &owner) && owner == pid ? w : NULL;
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
    WaitForSingleObject(thread, 5000);
    GetExitCodeThread(thread, &loaded);
    CloseHandle(thread);
    return loaded != 0;
}

int main(int argc, char **argv)
{
    STARTUPINFOA si = { sizeof(si) };
    PROCESS_INFORMATION pi;
    DWORD code = 1;
    char cmd[MAX_PATH + 3];

    if (argc != 3) return 2;
    const char *flag = argv[1];

    logf = fopen("C:\\dogfighter-focusfix.log", "w");
    DeleteFileA(flag);
    snprintf(cmd, sizeof(cmd), "\"%s\"", argv[2]);
    if (!CreateProcessA(NULL, cmd, NULL, NULL, FALSE, 0, NULL, NULL, &si, &pi))
    {
        say("could not start the game");
        return 1;
    }
    say("game started");
    BOOL hook_tried = FALSE;

    while (WaitForSingleObject(pi.hProcess, 100) == WAIT_TIMEOUT)
    {
        if (!hook_tried && game_window(pi.dwProcessId))
        {
            hook_tried = TRUE;
            say(load_hook(pi.hProcess) ? "loaded the focus hook into the game"
                                       : "could not load the focus hook");
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

    GetExitCodeProcess(pi.hProcess, &code);
    say("game exited");
    return (int)code;
}
