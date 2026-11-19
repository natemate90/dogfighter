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

static HWND game_window(DWORD pid)
{
    DWORD owner;
    HWND w = FindWindowA("AirfixClass", NULL);
    return w && GetWindowThreadProcessId(w, &owner) && owner == pid ? w : NULL;
}

static BOOL CALLBACK find_setup_dialog(HWND w, LPARAM found)
{
    char cls[16] = "";
    DWORD owner = 0;
    DWORD *pid_then_result = (DWORD *)found;

    GetClassNameA(w, cls, sizeof(cls));
    if (IsWindowVisible(w) && !strcmp(cls, "#32770") && GetWindowTextLengthA(w)
        && GetWindowThreadProcessId(w, &owner) && owner == pid_then_result[0])
    {
        pid_then_result[1] = TRUE;
        return FALSE;
    }
    return TRUE;
}

/**
 * Starting a thread in the game while it sets up Direct3D seemed to make
 * Wine's start-up crash under Rosetta more likely. The game is idle once its
 * setup dialog is open, or once its window has a size.
 */
static BOOL safe_to_load_hook(DWORD pid)
{
    DWORD pid_then_result[2] = { pid, FALSE };
    RECT client;
    HWND game = game_window(pid);

    if (!game) return FALSE;
    if (GetClientRect(game, &client) && client.right) return TRUE;
    EnumWindows(find_setup_dialog, (LPARAM)pid_then_result);
    return pid_then_result[1];
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

static void start_diagnostics(void)
{
    STARTUPINFOA si = { sizeof(si) };
    PROCESS_INFORMATION pi;
    char mode[32], cmd[96];

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
    if (!CreateProcessA(NULL, cmd, NULL, NULL, FALSE, 0, NULL, slash ? dir : NULL, &si, &pi))
    {
        say("could not start the game");
        return 1;
    }
    say("game started");
    start_diagnostics();
    BOOL hook_tried = FALSE;
    DWORD started = GetTickCount();

    while (WaitForSingleObject(pi.hProcess, 100) == WAIT_TIMEOUT)
    {
        if (!hook_tried && safe_to_load_hook(pi.dwProcessId))
        {
            hook_tried = TRUE;
            say(load_hook(pi.hProcess) ? "loaded the focus hook into the game"
                                       : "could not load the focus hook");
        }
        if (!hook_tried && GetTickCount() - started > 30000)
        {
            say("the game got stuck while starting Direct3D; ending it");
            TerminateProcess(pi.hProcess, 3);
            break;
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
