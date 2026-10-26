// launch.exe (x86) : cree WoW.exe SUSPENDU, injecte une DLL (VirtualAllocEx + WriteProcessMemory +
// CreateRemoteThread(LoadLibraryA)), reprend, attend, verifie le journal, termine WoW.exe.
// usage: launch.exe <WoW.exe> <dll> [secondes=15]
// Garde-fou : refuse de lancer un WoW.exe qui n'est pas sous un dossier "client_test" (le client d'origine
// ne doit jamais etre execute ni modifie).
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>

static bool Contains(const char* s, const char* sub)
{
    size_t n = strlen(sub);
    for (; *s; ++s) {
        size_t i = 0;
        while (i < n && s[i] && tolower((unsigned char)s[i]) == tolower((unsigned char)sub[i])) ++i;
        if (i == n) return true;
    }
    return false;
}
static void Die(const char* m, HANDLE proc)
{
    fprintf(stderr, "ECHEC: %s (GetLastError=%lu)\n", m, GetLastError());
    if (proc) TerminateProcess(proc, 1);
    exit(1);
}

int main(int argc, char** argv)
{
    if (argc < 3) { fprintf(stderr, "usage: launch <WoW.exe> <dll> [secondes]\n"); return 2; }
    char exe[MAX_PATH], dll[MAX_PATH], dir[MAX_PATH];
    GetFullPathNameA(argv[1], MAX_PATH, exe, NULL);
    GetFullPathNameA(argv[2], MAX_PATH, dll, NULL);
    int secs = argc > 3 ? atoi(argv[3]) : 15;
    if (!Contains(exe, "client_test")) { fprintf(stderr, "REFUS: %s n'est pas sous un dossier client_test\n", exe); return 3; }
    if (GetFileAttributesA(dll) == INVALID_FILE_ATTRIBUTES) { fprintf(stderr, "DLL introuvable: %s\n", dll); return 2; }
    strcpy(dir, exe); *strrchr(dir, '\\') = 0;
    char logp[MAX_PATH]; strcpy(logp, dll); *strrchr(logp, '\\') = 0; strcat(logp, "\\wowlheim_client.log");
    DeleteFileA(logp);

    STARTUPINFOA si = {}; si.cb = sizeof si;
    PROCESS_INFORMATION pi = {};
    char cmd[MAX_PATH + 8]; _snprintf(cmd, sizeof cmd, "\"%s\"", exe);
    if (!CreateProcessA(exe, cmd, NULL, NULL, FALSE, CREATE_SUSPENDED, NULL, dir, &si, &pi)) Die("CreateProcess", NULL);
    printf("WoW.exe cree suspendu pid=%lu\n", pi.dwProcessId);

    SIZE_T len = strlen(dll) + 1;
    LPVOID remote = VirtualAllocEx(pi.hProcess, NULL, len, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    if (!remote) Die("VirtualAllocEx", pi.hProcess);
    if (!WriteProcessMemory(pi.hProcess, remote, dll, len, NULL)) Die("WriteProcessMemory", pi.hProcess);
    // kernel32 est mappee a la meme adresse dans tous les processus 32 bits de la session
    FARPROC ll = GetProcAddress(GetModuleHandleA("kernel32.dll"), "LoadLibraryA");
    HANDLE th = CreateRemoteThread(pi.hProcess, NULL, 0, (LPTHREAD_START_ROUTINE)ll, remote, 0, NULL);
    if (!th) Die("CreateRemoteThread", pi.hProcess);
    DWORD w = WaitForSingleObject(th, 15000);
    DWORD hmod = 0; GetExitCodeThread(th, &hmod);
    printf("LoadLibraryA distant : wait=%lu HMODULE=0x%08lx\n", w, hmod);
    if (w != WAIT_OBJECT_0 || hmod == 0) Die("LoadLibrary distant a echoue", pi.hProcess);
    CloseHandle(th); VirtualFreeEx(pi.hProcess, remote, 0, MEM_RELEASE);

    ResumeThread(pi.hThread);
    printf("processus repris ; attente %d s...\n", secs);
    DWORD ex = WaitForSingleObject(pi.hProcess, secs * 1000);
    bool alive = (ex == WAIT_TIMEOUT);
    printf("WoW.exe %s apres l'attente\n", alive ? "toujours vivant" : "TERMINE de lui-meme");

    int ok = 0; static char buf[16384];
    FILE* f = fopen(logp, "rb");
    if (f) { size_t n = fread(buf, 1, sizeof buf - 1, f); buf[n] = 0; fclose(f); }
    printf("---- %s ----\n%s----\n", logp, buf);
    if (strstr(buf, "DLL_PROCESS_ATTACH")) ok = 1;
    if (alive) { TerminateProcess(pi.hProcess, 0); WaitForSingleObject(pi.hProcess, 5000); printf("WoW.exe termine par le lanceur\n"); }
    printf(ok ? "RESULTAT: DLL chargee (ligne DLL_PROCESS_ATTACH presente dans le journal)\n" : "RESULTAT: DLL NON chargee\n");
    CloseHandle(pi.hThread); CloseHandle(pi.hProcess);
    return ok ? 0 : 1;
}
