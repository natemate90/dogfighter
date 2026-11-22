#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
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

static DWORD env_number(const char *name)
{
    char text[16];
    return GetEnvironmentVariableA(name, text, sizeof(text)) ? strtoul(text, NULL, 10) : 0;
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
    char mode[8192], cmd[8300];

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
    HANDLE picture = CreateEventA(NULL, TRUE, FALSE, "DogfighterFirstPicture");
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
    BOOL hooked = load_hook(pi.hProcess);
    say(hooked ? "game started with the focus hook loaded" : "game started, but the focus hook could not be loaded");
    ResumeThread(pi.hThread);
    start_diagnostics();

    enum { STARTING, IN_SETUP, WAITING_FOR_PICTURE, RUNNING } state = STARTING;
    BOOL accept_setup = env_is("DOGFIGHTER_SETUP", "accept"), stalled = FALSE;
    DWORD began = GetTickCount(), picture_wait = hooked ? env_number("DOGFIGHTER_PICTURE_WAIT_MS") : 0;

    while (WaitForSingleObject(pi.hProcess, 100) == WAIT_TIMEOUT)
    {
        HWND dialog = state < WAITING_FOR_PICTURE ? setup_dialog(pi.dwProcessId) : NULL;

        if (state == STARTING && dialog)
        {
            state = IN_SETUP;
            if (accept_setup)
            {
                Sleep(500);
                PostMessageA(dialog, WM_COMMAND, IDOK, 0);
                say("pressed OK in the game's setup dialog");
            }
        }
        else if (state == STARTING && is_drawing(pi.dwProcessId)) state = RUNNING;
        else if (state == STARTING && GetTickCount() - began > 15000)
        {
            say("the game got stuck while starting; ending it");
            TerminateProcess(pi.hProcess, 3);
            break;
        }
        else if (state == IN_SETUP && !dialog)
        {
            state = picture && picture_wait ? WAITING_FOR_PICTURE : RUNNING;
            began = GetTickCount();
            if (env_is("DOGFIGHTER_END_AFTER_SETUP", "1"))
            {
                say("crash test: ending the game as its setup dialog closed");
                TerminateProcess(pi.hProcess, STATUS_ACCESS_VIOLATION);
            }
        }
        else if (state == WAITING_FOR_PICTURE && WaitForSingleObject(picture, 0) == WAIT_OBJECT_0)
        {
            if (logf) fprintf(logf, "focusfix: first picture %lu ms after the setup dialog closed\n", GetTickCount() - began);
            if (logf) fflush(logf);
            state = RUNNING;
        }
        else if (state == WAITING_FOR_PICTURE && GetTickCount() - began > picture_wait)
        {
            say("the game drew nothing after its setup dialog; ending it");
            stalled = TRUE;
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

    WaitForSingleObject(pi.hProcess, 5000);
    GetExitCodeProcess(pi.hProcess, &code);
    /* With --setup the player may have pressed Cancel, so there only an exception code counts as a crash. */
    BOOL crashed = (state == IN_SETUP || state == WAITING_FOR_PICTURE)
        && (accept_setup || (code & 0xC0000000) == 0xC0000000);
    if (stalled) return (int)code;
    if (state == STARTING) say("the game ended before its setup dialog appeared");
    else if (logf)
    {
        fprintf(logf, crashed ? "focusfix: the game ended before its first picture, exit code 0x%08lx\n"
                              : "focusfix: game exited, exit code 0x%08lx\n", code);
        fflush(logf);
    }
    return (int)code;
}
