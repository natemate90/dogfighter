#include <windows.h>

static WNDPROC game_proc, next_proc;

static LRESULT CALLBACK hook_proc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp)
{
    if (msg == WM_ACTIVATEAPP)
        return CallWindowProcA(game_proc, hwnd, msg, wp, lp);
    return CallWindowProcA(next_proc, hwnd, msg, wp, lp);
}

static DWORD WINAPI watch(void *arg)
{
    DWORD pid = GetCurrentProcessId(), owner;

    for (;;)
    {
        HWND w = FindWindowA("AirfixClass", NULL);
        if (w && GetWindowThreadProcessId(w, &owner) && owner == pid)
        {
            WNDPROC cur = (WNDPROC)GetWindowLongPtrA(w, GWLP_WNDPROC);
            WNDPROC cls = (WNDPROC)GetClassLongPtrA(w, GCLP_WNDPROC);
            if (cur != hook_proc && cur != cls)
            {
                game_proc = cls;
                next_proc = cur;
                SetWindowLongPtrA(w, GWLP_WNDPROC, (LONG_PTR)hook_proc);
            }
        }
        Sleep(250);
    }
    return 0;
}

BOOL WINAPI DllMain(HINSTANCE inst, DWORD reason, void *reserved)
{
    if (reason == DLL_PROCESS_ATTACH)
    {
        DisableThreadLibraryCalls(inst);
        CloseHandle(CreateThread(NULL, 0, watch, NULL, 0, NULL));
    }
    return TRUE;
}
