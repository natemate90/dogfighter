#include <windows.h>
#include <stdio.h>

static LONG logged;

static void where(FILE *f, DWORD addr)
{
    MEMORY_BASIC_INFORMATION info;
    char name[MAX_PATH];

    if (!VirtualQuery((void *)addr, &info, sizeof(info)) || info.Type != MEM_IMAGE) return;
    if (!GetModuleFileNameA(info.AllocationBase, name, sizeof(name))) return;
    char *base = strrchr(name, '\\');
    fprintf(f, " %s+0x%lx", base ? base + 1 : name, addr - (DWORD)info.AllocationBase);
}

static BOOL readable(const void *p, SIZE_T size)
{
    MEMORY_BASIC_INFORMATION info;
    return VirtualQuery(p, &info, sizeof(info)) && info.State == MEM_COMMIT
        && !(info.Protect & (PAGE_NOACCESS | PAGE_GUARD))
        && (const BYTE *)p + size <= (const BYTE *)info.BaseAddress + info.RegionSize;
}

static void dump_module(DWORD addr)
{
    MEMORY_BASIC_INFORMATION info;
    static const BYTE zeros[0x1000];

    if (!VirtualQuery((void *)addr, &info, sizeof(info)) || info.Type != MEM_IMAGE) return;
    const BYTE *base = info.AllocationBase;
    const IMAGE_NT_HEADERS *nt = (const void *)(base + ((const IMAGE_DOS_HEADER *)base)->e_lfanew);
    FILE *f = fopen("C:\\dogfighter-crash-module.bin", "wb");
    if (!f) return;
    for (DWORD off = 0; off < nt->OptionalHeader.SizeOfImage; off += 0x1000)
        fwrite(readable(base + off, 0x1000) ? base + off : zeros, 1, 0x1000, f);
    fclose(f);
}

static LONG CALLBACK on_exception(EXCEPTION_POINTERS *e)
{
    EXCEPTION_RECORD *r = e->ExceptionRecord;
    CONTEXT *c = e->ContextRecord;

    if (r->ExceptionCode != EXCEPTION_ACCESS_VIOLATION && r->ExceptionCode != EXCEPTION_ILLEGAL_INSTRUCTION
        && r->ExceptionCode != EXCEPTION_STACK_OVERFLOW && r->ExceptionCode != EXCEPTION_INT_DIVIDE_BY_ZERO)
        return EXCEPTION_CONTINUE_SEARCH;
    if (InterlockedIncrement(&logged) > 3) return EXCEPTION_CONTINUE_SEARCH;

    if (logged == 1) dump_module(c->Eip);
    FILE *f = fopen("C:\\dogfighter-crash.log", "a");
    if (!f) return EXCEPTION_CONTINUE_SEARCH;
    fprintf(f, "crashlog: code=%08lx thread=%04lx at %08lx", r->ExceptionCode, GetCurrentThreadId(), c->Eip);
    where(f, c->Eip);
    if (r->NumberParameters >= 2)
        fprintf(f, " %s %08lx", r->ExceptionInformation[0] ? "write" : "read", (DWORD)r->ExceptionInformation[1]);
    fprintf(f, "\n  eax=%08lx ebx=%08lx ecx=%08lx edx=%08lx esi=%08lx edi=%08lx ebp=%08lx esp=%08lx\n",
            c->Eax, c->Ebx, c->Ecx, c->Edx, c->Esi, c->Edi, c->Ebp, c->Esp);

    const BYTE *code = (const BYTE *)c->Eip - 64;
    if (readable(code, 128))
    {
        fprintf(f, "  code from %08lx:", (DWORD)code);
        for (int i = 0; i < 128; i++) fprintf(f, " %02x", code[i]);
        fprintf(f, "\n");
    }
    const struct { const char *name; DWORD value; } regs[] =
        { { "esi", c->Esi }, { "edi", c->Edi }, { "ebx", c->Ebx }, { "ecx", c->Ecx } };
    for (int r = 0; r < 4; r++)
    {
        const DWORD *mem = (const DWORD *)regs[r].value;
        if (!readable(mem, 0x180)) continue;
        fprintf(f, "  memory at %s:", regs[r].name);
        for (int i = 0; i < 0x60; i++) fprintf(f, "%s%08lx", i % 8 ? " " : "\n    ", mem[i]);
        fprintf(f, "\n");
    }
    const DWORD *stack = (const DWORD *)c->Esp;
    for (int i = 0; i < 192 && readable(stack + i, sizeof(DWORD)); i++)
    {
        MEMORY_BASIC_INFORMATION info;
        if (!VirtualQuery((void *)stack[i], &info, sizeof(info)) || info.Type != MEM_IMAGE) continue;
        fprintf(f, "  esp+%03x: %08lx", i * 4, stack[i]);
        where(f, stack[i]);
        fprintf(f, "\n");
    }
    fclose(f);
    return EXCEPTION_CONTINUE_SEARCH;
}

BOOL WINAPI DllMain(HINSTANCE inst, DWORD reason, void *reserved)
{
    if (reason == DLL_PROCESS_ATTACH)
    {
        DisableThreadLibraryCalls(inst);
        AddVectoredExceptionHandler(1, on_exception);
    }
    return TRUE;
}
