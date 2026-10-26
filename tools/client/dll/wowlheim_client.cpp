// wowlheim_client.dll - DLL injectee dans WoW.exe 1.12.1 (build 5875), 32 bits.
//  1) DllMain : ecrit une ligne dans wowlheim_client.log (temps, chemin du processus, pid, chemin de la DLL).
//  2) Pose des hooks (remplacement d'un CALL rel32 de 5 octets) sur les deux appels de FrameScript_Initialize
//     (WoW.exe 0x402aee au demarrage ; 0x703b8e = JMP de queue, a chaque (re)chargement de l'UI -> 0x7039e0 : cree un nouveau
//     lua_State dans [0xceef74]). Apres l'original, enregistre les API Lua Wowlheim via
//     FrameScript_RegisterFunction (0x704120, __fastcall(nom, fonction)), puis execute un petit Lua de
//     validation via FrameScript_Execute (0x704cd0, __fastcall(code, nom_de_chunk)).
//  3) Apercu fantome (docs/GHOST_PREVIEW.md) : reutilise le mecanisme natif du client qui affiche le modele
//     d'un gameobject sous le curseur pendant le ciblage au sol (globale 0xceca8c) :
//       - point monde sous la souris : hook du CALL 0x481190 (lancer de rayon ecran->monde) dans
//         CGWorldFrame::OnLayerUpdate (0x481790), site 0x48184a ; point touche = hit+8 (C3Vector).
//       - modele : 0x6707c0 (creation objet-modele du monde, comme 0x6e5a6e/0x6e518f), 0x670d40, 0x6709a0
//         (deplacement, comme 0x4821d5), 0x670d50 (liberation, comme 0x6e49e5).
//       - teinte/alpha : champs du CM2Model (def+0x88) : +0x180 alpha, +0x184 couleur diffuse (multiplie),
//         +0x190 couleur ajoutee (lu par 0x714260).
//       - dechargement de carte : hooks des CALL 0x697ac0 (CMap::Unload) en 0x66fc45 et 0x6920cc -> on libere
//         le fantome avant que le monde ne soit detruit.
// Toutes les adresses sont celles de WoW.exe build 5875 (ImageBase 0x400000 fixe, pas d'ASLR) et sont
// verifiees (octets attendus, table g_sigs ci-dessous, aussi verifiee hors ligne par verify_addrs.py) avant
// toute ecriture ou tout appel ; sinon la partie concernee reste inactive.
// Ne reutilise aucun asset ; aucun reseau.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <stdarg.h>
#include <string.h>

static char g_logPath[MAX_PATH];

static void Log(const char* fmt, ...)
{
    if (!g_logPath[0]) return;
    char msg[1024];
    SYSTEMTIME t; GetLocalTime(&t);
    int n = _snprintf(msg, sizeof msg - 2, "%04d-%02d-%02d %02d:%02d:%02d.%03d [pid %lu tid %lu] ",
                      t.wYear, t.wMonth, t.wDay, t.wHour, t.wMinute, t.wSecond, t.wMilliseconds,
                      GetCurrentProcessId(), GetCurrentThreadId());
    va_list ap; va_start(ap, fmt);
    n += _vsnprintf(msg + n, sizeof msg - 2 - n, fmt, ap);
    va_end(ap);
    if (n < 0 || n > (int)sizeof msg - 3) n = sizeof msg - 3;
    msg[n++] = '\r'; msg[n++] = '\n';
    HANDLE h = CreateFileA(g_logPath, FILE_APPEND_DATA, FILE_SHARE_READ | FILE_SHARE_WRITE, NULL,
                           OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (h == INVALID_HANDLE_VALUE) return;
    DWORD w; WriteFile(h, msg, n, &w, NULL); CloseHandle(h);
}

// ---- Adresses WoW.exe 5875 (voir docs/CLIENT_PATCH.md et docs/GHOST_PREVIEW.md) ----
static const DWORD VA_CALLSITE_INIT_BOOT   = 0x402aee; // CALL 0x7039e0 dans l'init moteur (demarrage)
static const DWORD VA_CALLSITE_INIT_RELOAD = 0x703b8e; // CALL 0x7039e0 dans FrameScript reset (UI load / ReloadUI)
static const DWORD VA_FRAMESCRIPT_INIT     = 0x7039e0; // FrameScript_Initialize : lua_open + libs, ecrit [0xceef74]
// Apercu fantome
static const DWORD VA_CALLSITE_RAYCAST     = 0x48184a; // CALL 0x481190 dans CGWorldFrame::OnLayerUpdate (0x481790), chaque image
static const DWORD VA_WORLD_RAYCAST        = 0x481190; // __thiscall(worldFrame, x, y, CHitResult*) -> 0 rien / 1 sol / 2 objet ; RET 0xc
static const DWORD VA_CALLSITE_UNLOAD_A    = 0x66fc45; // CALL 0x697ac0 dans CWorld::UnloadMap-like 0x66fc40
static const DWORD VA_CALLSITE_UNLOAD_B    = 0x6920cc; // CALL 0x697ac0 dans 0x6920c0
static const DWORD VA_MAP_UNLOAD           = 0x697ac0; // CMap::Unload-like (libere toutes les defs de modeles du monde)

typedef void (__fastcall *FrameScript_RegisterFunction_t)(const char* name, void* fn); // 0x704120
typedef void (__fastcall *FrameScript_Execute_t)(const char* code, const char* chunk);   // 0x704cd0
typedef const char* (__fastcall *lua_tostring_t)(void* L, int idx);                      // 0x6f3690
typedef void   (__fastcall *lua_pushstring_t)(void* L, const char* s);                   // 0x6f3890
typedef double (__fastcall *lua_tonumber_t)(void* L, int idx);                           // 0x6f3620 (resultat dans ST0)
typedef int    (__fastcall *lua_isnumber_t)(void* L, int idx);                           // 0x6f34d0
typedef int    (__fastcall *lua_isstring_t)(void* L, int idx);                           // 0x6f3510
typedef void   (__fastcall *lua_pushnumber_t)(void* L, double n);                        // 0x6f3810 (RET 8)
typedef void   (__fastcall *lua_pushnil_t)(void* L);                                     // 0x6f37f0
static FrameScript_RegisterFunction_t FrameScript_RegisterFunction = (FrameScript_RegisterFunction_t)0x704120;
static FrameScript_Execute_t          FrameScript_Execute          = (FrameScript_Execute_t)0x704cd0;
static lua_tostring_t                 lua_tostring_                = (lua_tostring_t)0x6f3690;
static lua_pushstring_t               lua_pushstring_              = (lua_pushstring_t)0x6f3890;
static lua_tonumber_t                 lua_tonumber_                = (lua_tonumber_t)0x6f3620;
static lua_isnumber_t                 lua_isnumber_                = (lua_isnumber_t)0x6f34d0;
static lua_isstring_t                 lua_isstring_                = (lua_isstring_t)0x6f3510;
static lua_pushnumber_t               lua_pushnumber_              = (lua_pushnumber_t)0x6f3810;
static lua_pushnil_t                  lua_pushnil_                 = (lua_pushnil_t)0x6f37f0;

// Objet-modele du monde (meme objet que les gameobjects et que le fantome natif 0xceca8c).
// 0x6707c0 : __fastcall(chemin, const C3Vector* pos, [pile] float orientation, int chargerTout, int placerSurGrille,
//            DWORD guidLo, DWORD guidHi) -> def* ; RET 0x14. ".wmo" -> def WMO (flag +8 & 0x08), sinon def M2 (flag +8 & 0x40).
typedef void* (__fastcall *WorldModel_Create_t)(const char* path, const float* pos, float facing, int loadAll, int snap, DWORD guidLo, DWORD guidHi);
// 0x6709a0 : __fastcall(def, const C3Vector* pos, [pile] float orientation, int placerSurGrille) ; RET 8
typedef void  (__fastcall *WorldModel_Update_t)(void* def, const float* pos, float facing, int snap);
typedef void  (__fastcall *WorldModel_SetFlag_t)(void* def, int v);          // 0x670d40 : v==0 -> [def+0xd] |= 1 (appel natif avec 0)
typedef void  (__fastcall *WorldModel_Release_t)(void* def);                 // 0x670d50 : --ref [def+0xe], libere a 0
typedef void  (__fastcall *DoodadDef_UpdateBounds_t)(void* def);            // 0x6952a0 : recalcule boite/rayon (rayon * [def+0x30])
typedef void  (__fastcall *C44Matrix_Scale_t)(float* m, void* edxUnused, const float* s3); // 0x7bdca0 : __thiscall, RET 4
static WorldModel_Create_t      WorldModel_Create      = (WorldModel_Create_t)0x6707c0;
static WorldModel_Update_t      WorldModel_Update      = (WorldModel_Update_t)0x6709a0;
static WorldModel_SetFlag_t     WorldModel_SetFlag     = (WorldModel_SetFlag_t)0x670d40;
static WorldModel_Release_t     WorldModel_Release     = (WorldModel_Release_t)0x670d50;
static DoodadDef_UpdateBounds_t DoodadDef_UpdateBounds = (DoodadDef_UpdateBounds_t)0x6952a0;
static C44Matrix_Scale_t        C44Matrix_Scale        = (C44Matrix_Scale_t)0x7bdca0;

// Decalages dans la def / le CM2Model (voir GHOST_PREVIEW.md pour les preuves)
static const int DEF_FLAGS   = 0x08;  // 0x08 = WMO, 0x40 = M2
static const int DEF_SCALE   = 0x30;  // float, mis a 1.0 par 0x698e20 a chaque deplacement
static const int DEF_MATRIX  = 0xcc;  // C44Matrix monde (identite, translation, rotation Z) ecrite par 0x698e20
static const int DEF_M2MODEL = 0x88;  // CM2Model* (0x695100)
static const int M2_LOADED   = 0x10;  // != 0 quand le M2 est charge (teste par 0x7103d0)
static const int M2_ALPHA    = 0x180; // float alpha (SetAlpha 0x710cb0 ; fondu des objets 0x614a90)
static const int M2_DIFFUSE  = 0x184; // C3Vector multiplie a l'eclairage diffus (0x710cf0 ; lu par 0x714260)
static const int M2_EMISSIVE = 0x190; // C3Vector ajoute a l'eclairage ambiant (0x710d40 ; lu par 0x714260)

// ---- Verification des octets attendus (table aussi lue par verify_addrs.py : garder le format) ----
struct Sig { DWORD va; const char* hex; int group; }; // group 0 base, 1 fantome DLL, 2 voie native
static const Sig g_sigs[] = {
    // ghost = 0 : deja controle a l'execution par InstallCallHook (cible du CALL) ; liste ici pour verify_addrs.py
    { 0x402aee, "e8ed0e3000", 0 },   // CALL 0x7039e0 (demarrage)
    { 0x703b8e, "e94dfeffff", 0 },   // JMP  0x7039e0 (reload UI)
    { 0x75d401, "cccccccccccccccccccccccccccccccccccccccccccccccc", 0 }, // cave : 48 octets 0xCC (6 trampolines)
    { 0x843b54, "53656e64436861744d657373616765", 0 },               // "SendChatMessage" (garde-fou build)
    // ghost = 1 : controle a l'execution avant d'activer l'apercu fantome
    { 0x48184a, "e841f9ffff", 1 },   // CALL 0x481190 (OnLayerUpdate -> lancer de rayon)
    { 0x66fc45, "e8767e0200", 1 },   // CALL 0x697ac0 (dechargement carte)
    { 0x6920cc, "e8ef590000", 1 },   // CALL 0x697ac0 (dechargement carte)
    { 0x481190, "558bec81ec9c000000", 1 },
    { 0x697ac0, "5657e849ec0000", 1 },
    { 0x6707c0, "558bec515356 8bda57ba a47a8600", 1 },
    { 0x6709a0, "558bec8b450c85c0538b5d08", 1 },
    { 0x670d40, "85d2740580610dfec380490d", 1 },
    { 0x670d50, "568bf18b4e20f6c101", 1 },
    { 0x6952a0, "558bec83ec5853568bd9", 1 },
    { 0x7bdca0, "558bec8b4508d900d9c0d809", 1 },
    { 0x6f3620, "558bec83ec10e8e5fdffff", 1 },
    { 0x6f34d0, "558bec83ec10e835ffffff", 1 },
    { 0x6f3510, "e8ebfeffff83f804", 1 },
    { 0x6f3810, "558bec8b4108c70003000000", 1 },
    { 0x6f37f0, "8b4108c70000000000", 1 },
    { 0x867aa4, "2e776d6f00", 1 },   // ".wmo" (critere WMO/M2 de 0x6707c0)
    // ghost = 2 : voie native (sort de pose 40001, fantome du client) - controle avant d'activer cette partie
    { 0x75f048, "cccccccccccccccccccccccccccccccccccccccccccccccccccccccc", 0 }, // cave 2 : 56 octets 0xCC
    { 0x54073b, "b980d7c000e88bf80000", 2 }, // MOV ECX,0xc0d780 ; CALL 0x54ffd0 (WowClientDB<SpellRec>::Load)
    { 0x55007e, "3dad000000", 2 },   // CMP EAX,0xad  : 173 colonnes
    { 0x5500bb, "3db4020000", 2 },   // CMP EAX,0x2b4 : 692 octets par enregistrement
    { 0x6e5140, "8b84bea8010000", 2 }, // MOV EAX,[ESI+EDI*4+0x1a8] : EffectMiscValue[i] (champ 106+i) lu au lancement
    { 0x4821c5, "e8b6472600", 2 },   // CALL 0x6e6980 (orientation du fantome natif)
    { 0x6e6980, "a090cace0084c07533", 2 }, // MOV AL,[0xceca90] ; TEST AL,AL ; JNZ (mode maison)
};

static int HexNib(char c) { return c >= '0' && c <= '9' ? c - '0' : c >= 'a' && c <= 'f' ? c - 'a' + 10 : -1; }
static bool CheckSig(const Sig& s)
{
    const BYTE* p = (const BYTE*)s.va; int i = 0;
    for (const char* h = s.hex; *h; ) {
        if (*h == ' ') { ++h; continue; }
        int a = HexNib(h[0]), b = HexNib(h[1]);
        if (a < 0 || b < 0) return false;
        if (IsBadReadPtr(p + i, 1) || p[i] != (BYTE)(a * 16 + b)) return false;
        ++i; h += 2;
    }
    return true;
}
static bool g_ghostOk = false; // toutes les signatures "ghost" correspondent et les hooks sont poses

// WoW valide chaque pointeur de fonction C de Lua (WoW.exe 0x42a320) : il doit tomber dans la section .text
// de WoW.exe ([0x401000,0x7fedac) ; sinon "ERROR #134 Invalid function pointer"). On ne peut donc pas
// enregistrer directement une fonction de la DLL : on loge un petit JMP rel32 dans une zone de padding 0xCC
// de .text et on enregistre l'adresse de ce trampoline. 8 octets par trampoline. Cave 1 : 0x75d401 (63 octets,
// 7 places) ; cave 2 : 0x75f048 (56 octets de padding 0xCC apres le RET 0xc de 0x75f042, 7 places).
// Utilisation : WowlheimPing + 5 API fantome + 3 API voie native = 9 trampolines.
static BYTE* g_cave = (BYTE*)0x75d401;
static int   g_caveLeft = 63;
static bool  g_cave2Used = false;
static void* MakeTrampoline(void* target)
{
    if (g_caveLeft < 8 && !g_cave2Used) { g_cave = (BYTE*)0x75f048; g_caveLeft = 56; g_cave2Used = true; }
    if (g_caveLeft < 8) { Log("ERREUR: plus de place dans les caves"); return NULL; }
    for (int i = 0; i < 8; ++i) if (g_cave[i] != 0xCC) { Log("ERREUR: la cave n'est pas du padding 0xCC"); return NULL; }
    DWORD old;
    VirtualProtect(g_cave, 8, PAGE_EXECUTE_READWRITE, &old);
    g_cave[0] = 0xE9; *(INT32*)(g_cave + 1) = (INT32)((DWORD)target - ((DWORD)g_cave + 5));
    VirtualProtect(g_cave, 8, old, &old);
    FlushInstructionCache(GetCurrentProcess(), g_cave, 8);
    void* r = g_cave; g_cave += 8; g_caveLeft -= 8; return r;
}

static volatile LONG g_pingCount = 0;

// API Lua de test : WowlheimPing([texte]) -> "pong"
static int __fastcall Lua_WowlheimPing(void* L)
{
    const char* arg = lua_tostring_(L, 1);
    LONG n = InterlockedIncrement(&g_pingCount);
    Log("Lua->DLL WowlheimPing #%ld arg=\"%s\"", n, arg ? arg : "(nil)");
    lua_pushstring_(L, "pong");
    return 1; // un resultat
}

// =====================================================================================================
// Apercu fantome. Tout s'execute sur le thread principal du jeu (Lua et CGWorldFrame::OnLayerUpdate).
// =====================================================================================================
struct GhostState {
    bool  want;            // l'addon a demande l'affichage
    char  path[MAX_PATH];  // modele demande
    float scale;           // echelle uniforme
    float facing;          // orientation (radians, autour de Z)
    float rgb[3];          // multiplicateur de couleur diffuse (1,1,1 = neutre)
    float alpha;           // 0..1
    float glow;            // part de rgb ajoutee en couleur "emissive" (0 = aucune)
    void* def;             // def de modele du monde creee par 0x6707c0 (NULL si aucune)
    char  defPath[MAX_PATH];
    bool  havePos;         // un point monde valide a ete calcule
    float pos[3];          // dernier point sous la souris
    int   kind;            // 1 = sol/WMO, 2 = objet (GUID dans hit+0)
    DWORD frames;          // compteur d'images ou le fantome a ete mis a jour
    bool  faulted;         // une exception a ete interceptee : fantome desactive
};
static GhostState g_ghost = { false, "", 1.0f, 0.0f, { 0.4f, 1.0f, 0.4f }, 0.5f, 0.25f, NULL, "", false, { 0, 0, 0 }, 0, 0, false };

static void Ghost_Release(const char* why)
{
    if (!g_ghost.def) return;
    void* d = g_ghost.def; g_ghost.def = NULL; g_ghost.defPath[0] = 0;
    __try { WorldModel_Release(d); }
    __except (EXCEPTION_EXECUTE_HANDLER) { g_ghost.faulted = true; Log("ERREUR exception en liberant le fantome %p", d); return; }
    Log("fantome libere (%s) def=%p", why, d);
}

static void Ghost_ApplyLook()
{
    BYTE* d = (BYTE*)g_ghost.def;
    DWORD flags = *(DWORD*)(d + DEF_FLAGS);
    if (!(flags & 0x40)) return; // WMO : ni echelle ni teinte (non etudie)
    if (g_ghost.scale != 1.0f) {
        float s3[3] = { g_ghost.scale, g_ghost.scale, g_ghost.scale };
        C44Matrix_Scale((float*)(d + DEF_MATRIX), NULL, s3);
        *(float*)(d + DEF_SCALE) = g_ghost.scale;
    }
    BYTE* m = *(BYTE**)(d + DEF_M2MODEL);
    if (!m) return;
    if (g_ghost.scale != 1.0f && *(DWORD*)(m + M2_LOADED)) DoodadDef_UpdateBounds(d);
    *(float*)(m + M2_ALPHA) = g_ghost.alpha;
    for (int i = 0; i < 3; ++i) {
        ((float*)(m + M2_DIFFUSE))[i]  = g_ghost.rgb[i];
        ((float*)(m + M2_EMISSIVE))[i] = g_ghost.rgb[i] * g_ghost.glow;
    }
}

// Appele a chaque image depuis le hook du lancer de rayon (meme contexte que la mise a jour du fantome natif 0x4821d5).
static void Ghost_Tick()
{
    if (g_ghost.faulted) return;
    if (!g_ghost.want) { Ghost_Release("masque"); return; }
    if (!g_ghost.havePos) return;
    if (g_ghost.def && strcmp(g_ghost.defPath, g_ghost.path) != 0) Ghost_Release("changement de modele");
    if (!g_ghost.def) {
        g_ghost.def = WorldModel_Create(g_ghost.path, g_ghost.pos, g_ghost.facing, 0, 0, 0, 0);
        if (!g_ghost.def) { Log("ERREUR creation du fantome \"%s\" (0x6707c0 -> NULL)", g_ghost.path); g_ghost.want = false; return; }
        WorldModel_SetFlag(g_ghost.def, 0); // meme appel que le client apres creation (0x6e5a7c)
        strcpy(g_ghost.defPath, g_ghost.path);
        Log("fantome cree \"%s\" def=%p flags=0x%08lx pos=(%.2f,%.2f,%.2f)", g_ghost.path, g_ghost.def,
            *(DWORD*)((BYTE*)g_ghost.def + DEF_FLAGS), g_ghost.pos[0], g_ghost.pos[1], g_ghost.pos[2]);
    }
    WorldModel_Update(g_ghost.def, g_ghost.pos, g_ghost.facing, 0);
    Ghost_ApplyLook();
    ++g_ghost.frames;
}

typedef int (__fastcall *WorldRaycast_t)(void* self, void* edx, DWORD x, DWORD y, BYTE* hit);
static int __fastcall Hook_WorldRaycast(void* self, void* edx, DWORD x, DWORD y, BYTE* hit)
{
    int r = ((WorldRaycast_t)VA_WORLD_RAYCAST)(self, edx, x, y, hit);
    __try {
        if ((r == 1 || r == 2) && hit) {
            // 0x480df0 ecrit le point touche en hit+8 (C3Vector) ; c'est ce que lit 0x4820f0 pour le ciblage au sol.
            const float* p = (const float*)(hit + 8);
            g_ghost.pos[0] = p[0]; g_ghost.pos[1] = p[1]; g_ghost.pos[2] = p[2];
            g_ghost.kind = r; g_ghost.havePos = true;
        }
        Ghost_Tick();
    }
    __except (EXCEPTION_EXECUTE_HANDLER) {
        g_ghost.faulted = true; g_ghost.def = NULL;
        Log("ERREUR exception 0x%08lx dans la mise a jour du fantome : fantome desactive", GetExceptionCode());
    }
    return r;
}

typedef void (__fastcall *MapUnload_t)(void* ecx, void* edx);
static void __fastcall Hook_MapUnload(void* ecx, void* edx)
{
    // Le monde va liberer toutes ses defs de modeles : on libere la notre avant (comme l'annulation du ciblage natif).
    if (g_ghost.def) Ghost_Release("dechargement de la carte");
    g_ghost.want = false; g_ghost.havePos = false;
    ((MapUnload_t)VA_MAP_UNLOAD)(ecx, edx);
}

static bool LuaNum(void* L, int idx, float* out) { if (!lua_isnumber_(L, idx)) return false; *out = (float)lua_tonumber_(L, idx); return true; }
static float Clamp01(float v) { return v < 0 ? 0 : v > 1 ? 1 : v; }

// WowlheimGhostShow(cheminModele [, echelle]) -> true/nil
static int __fastcall Lua_GhostShow(void* L)
{
    if (!g_ghostOk || g_ghost.faulted || !lua_isstring_(L, 1)) { lua_pushnil_(L); return 1; }
    const char* p = lua_tostring_(L, 1);
    if (!p || !*p || strlen(p) >= MAX_PATH) { lua_pushnil_(L); return 1; }
    float s = 1.0f;
    if (LuaNum(L, 2, &s) && (s < 0.01f || s > 100.0f)) s = 1.0f;
    strcpy(g_ghost.path, p);
    g_ghost.scale = s;
    g_ghost.want = true;
    Log("Lua WowlheimGhostShow(\"%s\", %.3f)", g_ghost.path, s);
    lua_pushnumber_(L, 1.0);
    return 1;
}

// WowlheimGhostRotate(radians) : orientation absolue autour de l'axe Z
static int __fastcall Lua_GhostRotate(void* L)
{
    float f;
    if (LuaNum(L, 1, &f)) {
        const float twoPi = 6.28318530718f;
        while (f < 0) f += twoPi;
        while (f >= twoPi) f -= twoPi;
        g_ghost.facing = f;
    }
    return 0;
}

// WowlheimGhostHide()
static int __fastcall Lua_GhostHide(void* L)
{
    (void)L;
    g_ghost.want = false;
    Ghost_Release("WowlheimGhostHide");
    return 0;
}

// WowlheimGhostGetPos() -> x, y, z, orientation, type (1 sol/WMO, 2 objet) ; nil si aucun point connu
static int __fastcall Lua_GhostGetPos(void* L)
{
    if (!g_ghost.havePos) { lua_pushnil_(L); return 1; }
    lua_pushnumber_(L, g_ghost.pos[0]);
    lua_pushnumber_(L, g_ghost.pos[1]);
    lua_pushnumber_(L, g_ghost.pos[2]);
    lua_pushnumber_(L, g_ghost.facing);
    lua_pushnumber_(L, (double)g_ghost.kind);
    return 5;
}

// WowlheimGhostSetColor(r, g, b [, a [, lueur]]) : composantes 0..1 ; lueur = part de (r,g,b) ajoutee en emissif
static int __fastcall Lua_GhostSetColor(void* L)
{
    float v;
    for (int i = 0; i < 3; ++i) if (LuaNum(L, i + 1, &v)) g_ghost.rgb[i] = Clamp01(v);
    if (LuaNum(L, 4, &v)) g_ghost.alpha = Clamp01(v);
    if (LuaNum(L, 5, &v)) g_ghost.glow = Clamp01(v);
    return 0;
}

// =====================================================================================================
// Voie native : le client affiche lui-meme le modele du gameobject invoque par le sort pendant le ciblage
// au sol (docs/GHOST_PREVIEW.md section 1). On change en memoire EffectMiscValue du sort de pose (Spell.dbc
// client) pour choisir la piece, et on peut imposer l'orientation du fantome natif.
// =====================================================================================================
// WowClientDB<SpellRec> (0xc0d780, charge par 0x54ffd0) : +0 enregistrements contigus (0x2b4 octets),
// +4 nombre, +8 table d'index [id] -> enregistrement*, +0xc id max, +0x10 charge (1). Lookups du client en ligne :
// "if (id < 0 || [0xc0d78c] < id) ... rec = [[0xc0d788] + id*4]".
static const DWORD VA_SPELL_DB          = 0xc0d780;
static const DWORD VA_CALLSITE_FACING   = 0x4821c5; // CALL 0x6e6980 dans 0x4820f0 (mise a jour du fantome natif)
static const DWORD VA_NATIVE_FACING     = 0x6e6980; // orientation du fantome natif (joueur, ou [0xcecad4] en mode maison)
static const DWORD WL_PLACE_SPELL       = 40001;    // sort de pose du marteau (Spell.dbc du patch client)
static const int   SPELL_FIELD_EFFECT   = 61;       // Effect[3]          (rec[0x3d+i], lu en 0x6e50e0)
static const int   SPELL_FIELD_MISC     = 106;      // EffectMiscValue[3] (rec[0x6a+i], lu en 0x6e5140)
static bool  g_nativeOk = false;
static bool  g_placeFacingSet = false;
static float g_placeFacing = 0.0f;

static DWORD* SpellRec(DWORD id)
{
    const DWORD* db = (const DWORD*)VA_SPELL_DB;
    if (!db[4] || !db[2] || id > db[3]) return NULL;   // pas charge / hors bornes (meme test que le client)
    DWORD* r = ((DWORD**)db[2])[id];
    return (r && r[0] == id) ? r : NULL;
}
// Index (0..2) du premier effet qui fait apparaitre le fantome natif (meme liste que 0x6e50e0..0x6e5103), ou -1.
static int SummonEffectIndex(const DWORD* r)
{
    for (int i = 0; i < 3; ++i) {
        DWORD e = r[SPELL_FIELD_EFFECT + i];
        if (e == 50 || e == 76 || e == 81 || (e >= 104 && e <= 107)) return i;
    }
    return -1;
}

// WowlheimSetPlaceObject(goEntry [, spellId=40001]) -> ancienne valeur, ou nil (sort absent / sans effet d'invocation)
static int __fastcall Lua_SetPlaceObject(void* L)
{
    float f, s = (float)WL_PLACE_SPELL;
    if (!g_nativeOk || !LuaNum(L, 1, &f) || f < 1 || f > 2147483647.0f) { lua_pushnil_(L); return 1; }
    LuaNum(L, 2, &s);
    DWORD spell = (DWORD)s, entry = (DWORD)lua_tonumber_(L, 1); // relu en double : pas de perte de precision float
    DWORD* r = SpellRec(spell);
    int i = r ? SummonEffectIndex(r) : -1;
    if (i < 0) { Log("WowlheimSetPlaceObject: sort %lu absent ou sans effet d'invocation d'objet", spell); lua_pushnil_(L); return 1; }
    DWORD old = r[SPELL_FIELD_MISC + i];
    r[SPELL_FIELD_MISC + i] = entry;   // enregistrement sur le tas (alloue par 0x54ffd0) : inscriptible
    Log("WowlheimSetPlaceObject: sort %lu effet %d (type %lu) EffectMiscValue %lu -> %lu", spell, i + 1,
        r[SPELL_FIELD_EFFECT + i], old, entry);
    lua_pushnumber_(L, (double)old);
    return 1;
}

// WowlheimGetPlaceObject([spellId=40001]) -> EffectMiscValue de l'effet d'invocation, ou nil
static int __fastcall Lua_GetPlaceObject(void* L)
{
    float s = (float)WL_PLACE_SPELL;
    LuaNum(L, 1, &s);
    DWORD* r = g_nativeOk ? SpellRec((DWORD)s) : NULL;
    int i = r ? SummonEffectIndex(r) : -1;
    if (i < 0) { lua_pushnil_(L); return 1; }
    lua_pushnumber_(L, (double)r[SPELL_FIELD_MISC + i]);
    return 1;
}

// WowlheimSetPlaceFacing(radians) impose l'orientation du fantome natif ; WowlheimSetPlaceFacing() (sans
// argument) rend la main au client (orientation du joueur ; mode maison : [0xcecad4], +pi/2 par clic droit).
static int __fastcall Lua_SetPlaceFacing(void* L)
{
    float f;
    if (LuaNum(L, 1, &f)) {
        const float twoPi = 6.28318530718f;
        while (f < 0) f += twoPi;
        while (f >= twoPi) f -= twoPi;
        g_placeFacing = f; g_placeFacingSet = true;
    } else {
        g_placeFacingSet = false;
    }
    return 0;
}

// Remplace le CALL 0x6e6980 de 0x4820f0 : renvoie (dans ST0) l'orientation passee a 0x6709a0 pour le fantome natif.
static float __cdecl Hook_NativeFacing()
{
    float f = ((float (__cdecl*)())VA_NATIVE_FACING)();   // conserve le comportement d'origine (ecrit [0xcecad4])
    return g_placeFacingSet ? g_placeFacing : f;
}

struct LuaApi { const char* name; void* fn; int group; void* tramp; };
static LuaApi g_api[] = {
    { "WowlheimPing",           (void*)&Lua_WowlheimPing,   0, NULL },
    { "WowlheimGhostShow",      (void*)&Lua_GhostShow,      1, NULL },
    { "WowlheimGhostRotate",    (void*)&Lua_GhostRotate,    1, NULL },
    { "WowlheimGhostHide",      (void*)&Lua_GhostHide,      1, NULL },
    { "WowlheimGhostGetPos",    (void*)&Lua_GhostGetPos,    1, NULL },
    { "WowlheimGhostSetColor",  (void*)&Lua_GhostSetColor,  1, NULL },
    { "WowlheimSetPlaceObject", (void*)&Lua_SetPlaceObject, 2, NULL },
    { "WowlheimGetPlaceObject", (void*)&Lua_GetPlaceObject, 2, NULL },
    { "WowlheimSetPlaceFacing", (void*)&Lua_SetPlaceFacing, 2, NULL },
};

static int __cdecl Hook_InitLua()
{
    int r = ((int (__cdecl*)())VA_FRAMESCRIPT_INIT)();   // comportement d'origine
    Log("FrameScript_Initialize termine (retour %d), lua_State global [0xceef74]=%p", r, *(void**)0xceef74);
    // Nouvel etat Lua (demarrage, ReloadUI, changement de personnage) : l'addon qui pilotait le fantome a disparu.
    g_ghost.want = false;
    if (g_ghost.def) Ghost_Release("reinitialisation Lua");
    int n = 0;
    for (size_t i = 0; i < sizeof g_api / sizeof g_api[0]; ++i) {
        LuaApi& a = g_api[i];
        if ((a.group == 1 && !g_ghostOk) || (a.group == 2 && !g_nativeOk)) continue;
        if (!a.tramp || *(BYTE*)a.tramp != 0xE9) a.tramp = MakeTrampoline(a.fn);
        if (!a.tramp) continue;
        FrameScript_RegisterFunction(a.name, a.tramp);
        Log("%s enregistree (trampoline .text a 0x%08lx -> DLL 0x%08lx)", a.name, (DWORD)a.tramp, (DWORD)a.fn);
        ++n;
    }
    if (!g_api[0].tramp) return r;
    // auto-test sans interface : le client execute lui-meme du Lua qui appelle nos API (sans monde : GetPos -> nil)
    FrameScript_Execute(
        "local r = WowlheimPing('hello from lua ' .. tostring(1+1)) "
        "WowlheimPing('retour=' .. tostring(r)) "
        "if WowlheimGhostGetPos then "
        "  WowlheimGhostSetColor(0.4, 1, 0.4, 0.5) WowlheimGhostRotate(1.5) WowlheimGhostHide() "
        "  WowlheimPing('ghost getpos=' .. tostring(WowlheimGhostGetPos())) "
        "end "
        "if WowlheimGetPlaceObject then "
        "  WowlheimSetPlaceFacing() "
        "  WowlheimPing('place object=' .. tostring(WowlheimGetPlaceObject())) "
        "end",
        "WowlheimSelfTest");
    Log("auto-test Lua termine ; %d API enregistrees ; WowlheimPing appelee %ld fois", n, (long)g_pingCount);
    return r;
}

static bool InstallCallHook(DWORD site, DWORD expectedTarget, void* hook)
{
    BYTE* p = (BYTE*)site;
    if (IsBadReadPtr(p, 5) || (p[0] != 0xE8 && p[0] != 0xE9)) { Log("ERREUR hook: ni CALL ni JMP rel32 en 0x%08lx", site); return false; }
    DWORD target = site + 5 + *(INT32*)(p + 1);
    if (target != expectedTarget) { Log("ERREUR hook: cible 0x%08lx != attendue 0x%08lx", target, expectedTarget); return false; }
    DWORD old;
    if (!VirtualProtect(p, 5, PAGE_EXECUTE_READWRITE, &old)) { Log("ERREUR VirtualProtect %lu", GetLastError()); return false; }
    *(INT32*)(p + 1) = (INT32)((DWORD)hook - (site + 5));
    VirtualProtect(p, 5, old, &old);
    FlushInstructionCache(GetCurrentProcess(), p, 5);
    return true;
}

static bool LooksLikeWow5875()
{
    // Chaines de reference : "SendChatMessage" a 0x843b54 et "Usage: SendAddonMessage" a 0x844b64
    const char* a = (const char*)0x843b54; const char* b = (const char*)0x844b64;
    if (IsBadReadPtr(a, 16) || IsBadReadPtr(b, 24)) return false;
    return memcmp(a, "SendChatMessage", 15) == 0 && memcmp(b, "Usage: SendAddonMessage", 23) == 0;
}

static void InstallGhostHooks()
{
    for (size_t i = 0; i < sizeof g_sigs / sizeof g_sigs[0]; ++i) {
        if (g_sigs[i].group != 1) continue;
        if (!CheckSig(g_sigs[i])) { Log("apercu fantome DESACTIVE : octets inattendus en 0x%08lx (attendu %s)", g_sigs[i].va, g_sigs[i].hex); return; }
    }
    // Le hook du lancer de rayon en premier : sans lui le fantome ne fait rien ; les hooks de dechargement le protegent.
    if (!InstallCallHook(VA_CALLSITE_UNLOAD_A, VA_MAP_UNLOAD, (void*)&Hook_MapUnload)) return;
    if (!InstallCallHook(VA_CALLSITE_UNLOAD_B, VA_MAP_UNLOAD, (void*)&Hook_MapUnload)) return;
    Log("hooks poses en 0x%08lx et 0x%08lx (CALL 0x%08lx -> Hook_MapUnload)", VA_CALLSITE_UNLOAD_A, VA_CALLSITE_UNLOAD_B, VA_MAP_UNLOAD);
    if (!InstallCallHook(VA_CALLSITE_RAYCAST, VA_WORLD_RAYCAST, (void*)&Hook_WorldRaycast)) return;
    Log("hook pose en 0x%08lx (CALL 0x%08lx -> Hook_WorldRaycast)", VA_CALLSITE_RAYCAST, VA_WORLD_RAYCAST);
    g_ghostOk = true;
}

static void InstallNativeHooks()
{
    // les fonctions Lua utilisees (groupe 1 : lua_tonumber, ...) et la voie native (groupe 2) doivent correspondre
    for (size_t i = 0; i < sizeof g_sigs / sizeof g_sigs[0]; ++i) {
        if (g_sigs[i].group == 0) continue;
        if (!CheckSig(g_sigs[i])) { Log("voie native DESACTIVEE : octets inattendus en 0x%08lx (attendu %s)", g_sigs[i].va, g_sigs[i].hex); return; }
    }
    if (!InstallCallHook(VA_CALLSITE_FACING, VA_NATIVE_FACING, (void*)&Hook_NativeFacing)) return;
    Log("hook pose en 0x%08lx (CALL 0x%08lx -> Hook_NativeFacing)", VA_CALLSITE_FACING, VA_NATIVE_FACING);
    g_nativeOk = true;
}

BOOL APIENTRY DllMain(HMODULE hMod, DWORD reason, LPVOID)
{
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(hMod);
        char dll[MAX_PATH] = {0}, exe[MAX_PATH] = {0};
        GetModuleFileNameA(hMod, dll, MAX_PATH);
        GetModuleFileNameA(NULL, exe, MAX_PATH);
        strcpy(g_logPath, dll);
        char* s = strrchr(g_logPath, '\\'); if (s) s[1] = 0; else g_logPath[0] = 0;
        strcat(g_logPath, "wowlheim_client.log");
        Log("DllMain DLL_PROCESS_ATTACH  processus=\"%s\"  dll=\"%s\"", exe, dll);
        if (!LooksLikeWow5875()) {
            Log("le binaire hote n'est pas WoW 1.12.1 build 5875 (chaines de reference absentes) : aucun hook");
        } else {
            if (InstallCallHook(VA_CALLSITE_INIT_BOOT, VA_FRAMESCRIPT_INIT, (void*)&Hook_InitLua))
                Log("hook pose en 0x%08lx (CALL 0x%08lx -> Hook_InitLua)", VA_CALLSITE_INIT_BOOT, VA_FRAMESCRIPT_INIT);
            if (InstallCallHook(VA_CALLSITE_INIT_RELOAD, VA_FRAMESCRIPT_INIT, (void*)&Hook_InitLua))
                Log("hook pose en 0x%08lx (CALL 0x%08lx -> Hook_InitLua)", VA_CALLSITE_INIT_RELOAD, VA_FRAMESCRIPT_INIT);
            InstallNativeHooks(); // avant InstallGhostHooks : controle les octets avant tout patch
            InstallGhostHooks();
        }
    } else if (reason == DLL_PROCESS_DETACH) {
        Log("DllMain DLL_PROCESS_DETACH (WowlheimPing appelee %ld fois ; fantome mis a jour sur %lu images)",
            (long)g_pingCount, g_ghost.frames);
    }
    return TRUE;
}
