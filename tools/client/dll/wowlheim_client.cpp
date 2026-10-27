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
//       - marqueurs fixes (cercle de portee des stations) : WowlheimMarkerShow/Hide, memes fonctions que le fantome.
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
struct Sig { DWORD va; const char* hex; int group; }; // group 0 base, 1 fantome DLL, 2 voie native, 3 survol, 4 fondu, 5 prechargement, 6 disparition, 7 surbrillance, 8 marteau sans touche
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
    { 0x6e6970, "a18ccace00c3", 2 }, // MOV EAX,[0xceca8c] ; RET : def du fantome natif (appele en 0x4821b1, ESI -> 0x6709a0)
    { 0x482154, "c7052cdc830000000000", 2 }, // MOV [0x83dc2c],0 : point de ciblage dans la portee du sort (1 = hors portee)
    // group 3 : objet sous le curseur (WowlheimGetMouseoverObject, docs/BUILD_CONTROLS.md section 3)
    { 0x4812c1, "e88afdffff", 3 },   // CALL 0x481050 (masque de selection du rayon) dans 0x481190
    { 0x481050, "558bec5156e84638260084c0", 3 }, // calcul du masque (CALL 0x6e48a0 = ciblage en cours ?)
    { 0x6e48a0, "33c0663905c0cace000f95c0", 3 }, // Spell_C_IsTargeting : word [0xcecac0] != 0
    { 0x464870, "558bec8b45088b4d0c8bd00bd1740b5150e8", 3 }, // ClntObjMgrObjectPtr(guidLo, guidHi), __stdcall RET 8
    // group 4 : apparition instantanee des objets Wowlheim (fondu de 2 s du client)
    { 0x5f7c6b, "e880be0100", 4 },   // CALL 0x613af0 (CGObject_C init. du fondu) dans CGGameObject_C 0x5f7c40
    { 0x5fb956, "e895810100", 4 },   // CALL 0x613af0 dans CGUnit_C 0x5fb880
    { 0x5f7e83, "e8b8c70100", 4 },   // CALL 0x614640 (reapparition) dans CGGameObject_C 0x5f7e80
    { 0x5fbd67, "e8d4880100", 4 },   // CALL 0x614640 dans CGUnit_C 0x5fbd60
    { 0x613b0d, "25d0070000", 4 },   // AND EAX,0x7d0 : duree du fondu 2000 ms (ou 0)
    { 0x614f80, "558bec56578b7d0c85ff8bf1", 4 }, // SetAlphaTarget(cible, duree) : +0xec debut, +0xf0 duree, +0xf4 courant, +0xfc cible
    // group 5 : prechargement des modeles M2
    { 0x695107, "8b0d98b2c700", 5 }, // MOV ECX,[0xc7b298] (scene M2 du monde) avant CALL 0x707350
    { 0x707350, "558bec8b4508535633f685c0", 5 }, // CM2Scene::CreateModel(chemin, drapeaux), __thiscall RET 8
    { 0x7103a0, "568bf18b064889067516", 5 }, // CM2Model::Release (--ref, detruit a 0)
    // group 6 : disparition instantanee (fondu de sortie SWModelFadeout de 2 s, docs/BUILD_CONTROLS.md section 4.3)
    { 0x614603, "e8e8e70500", 6 },   // CALL 0x672df0 (fondu de sortie du modele) dans CGObject_C::Disappear 0x6145e0
    { 0x5fbf30, "e8bb6e0700", 6 },   // CALL 0x672df0 dans CGUnit_C 0x5fbe80 (liberation du modele d'une creature)
    { 0x6145e0, "568bf18b86e00000005733ff3bc7", 6 }, // PUSH ESI ; MOV ESI,ECX (ESI = objet jusqu'au CALL) ; [obj+0xe0] = def
    { 0x5fbe80, "558bec51568bf18b86e00000", 6 },     // idem (ESI = objet) pour CGUnit_C
    { 0x672df0, "558bec53568bd933f63bde0f84db0000", 6 }, // ModelFadeout(def, alpha), __thiscall RET 4 ("SWModelFadeout")
    { 0x672e1e, "d94508d81dd0298000", 6 }, // FLD [alpha] ; FCOMP [0x8029d0] (0.01) : alpha < 0.01 -> 0x671ac0 (liberation immediate)
    { 0x8029d0, "0ad7233c", 6 },     // 0.01f
    { 0x672f36, "3dd0070000", 6 },   // CMP EAX,0x7d0 : fondu de sortie de 2000 ms (0x672ef0, chaque image)
    // group 7 : surbrillance de la piece visee (WowlheimHighlightObject, Valheim WearNTear.Highlight)
    { 0x6144f0, "558bec83ec0c8bc18b4d08ba01000000d3e28b88b8000000", 7 }, // CGObject_C::ClearHighlight(bit) : masque [obj+0xb8]
    { 0x614550, "558bec83ec0c568bf18b4d088b96b8000000b801000000d3", 7 }, // CGObject_C::SetHighlight(bit) -> emissif du CM2Model
    { 0x710d40, "558bec8b45088b1081c190010000", 7 }, // CM2Model::SetEmissive : +0x190
    { 0x710cf0, "558bec8b45088b1081c184010000", 7 }, // CM2Model::SetDiffuse  : +0x184
    // group 8 : WowlheimUseHammer (ciblage du marteau sans entree utilisateur ; docs : commentaire de Lua_UseHammer)
    { 0x848518, "14878400e08d4c00", 8 }, // table Lua : "UseInventoryItem" (0x848714) -> 0x4c8de0
    { 0x4c8de0, "558bec83ec0856576a018d55fc8bf1c7", 8 }, // Lua UseInventoryItem(slot [, unite]) : __fastcall(L)
    { 0x4c8df6, "e825f7ffff", 8 },   // CALL 0x4c8520 (validation du slot, sinon luaL_error 0x6f4940)
    { 0x4c8e50, "e81bebffff", 8 },   // CALL 0x4c7970 (utilisation de l'objet du slot)
    { 0x494a50, "a1c0eace0085c0568bf10f84b1000000", 8 }, // CanPerformAction(mode) : [0xceeac0] = souillure (code d'addon)
    { 0x494a92, "e899992e0085c07576e8f04d2e0085c0756d8b0d9012b7008b81d800000085c0755d33c0", 8 }, // mode 2 : touche / clic / commande
    { 0x77e430, "a1c44dcf00c3", 8 }, // MOV EAX,[0xcf4dc4] ; RET : evenement clavier en cours
    { 0x77b438, "c705c44dcf0001000000", 8 }, // MOV [0xcf4dc4],1 avant le script d'un raccourci clavier (0x702690)
    { 0x77b459, "c705c44dcf0000000000", 8 }, // MOV [0xcf4dc4],0 apres
    { 0x6e4bbc, "b902000000e88afedaff85c00f84a004", 8 }, // Spell_C_CastSpell : CanPerformAction(2), echec silencieux
    { 0x6e48a0, "33c0663905c0cace000f95c0", 8 }, // Spell_C_IsTargeting
    { 0x755d16, "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc", 0 }, // cave 3 : 40 octets 0xCC
    { 0x755dd6, "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc", 0 }, // cave 4
    { 0x755e96, "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc", 0 }, // cave 5
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
// WowlheimUseHammer : [0xcf4dc4] force a 1 pendant l'appel ; filet de securite si une erreur Lua (longjmp) saute la
// restauration : remis a l'ancienne valeur a l'image suivante (Hook_WorldRaycast)
static bool g_hwForced = false;
static LONG g_hwSaved = 0;

// WoW valide chaque pointeur de fonction C de Lua (WoW.exe 0x42a320) : il doit tomber dans la section .text
// de WoW.exe ([0x401000,0x7fedac) ; sinon "ERROR #134 Invalid function pointer"). On ne peut donc pas
// enregistrer directement une fonction de la DLL : on loge un petit JMP rel32 dans une zone de padding 0xCC
// de .text et on enregistre l'adresse de ce trampoline. 8 octets par trampoline. Cave 1 : 0x75d401 (63 octets,
// 7 places) ; cave 2 : 0x75f048 (56 octets de padding 0xCC apres le RET 0xc de 0x75f042, 7 places).
// Utilisation : WowlheimPing + 5 API fantome + 3 API voie native + 2 API marqueurs + survol + fondu + prechargement
// = 14 trampolines (cave 2 pleine). Caves 3 a 5 : 0x755d16, 0x755dd6, 0x755e96 (40 octets 0xCC chacune, entre deux
// fonctions apres un RET, 5 places chacune ; 15 places de plus) pour les API suivantes (surbrillance...).
static const DWORD g_caveList[][2] = { { 0x75d401, 63 }, { 0x75f048, 56 }, { 0x755d16, 40 }, { 0x755dd6, 40 }, { 0x755e96, 40 } };
static BYTE* g_cave = (BYTE*)0x75d401;
static int   g_caveLeft = 63;
static int   g_caveIdx = 0;
static void* MakeTrampoline(void* target)
{
    while (g_caveLeft < 8 && g_caveIdx + 1 < (int)(sizeof g_caveList / sizeof g_caveList[0])) {
        ++g_caveIdx; g_cave = (BYTE*)g_caveList[g_caveIdx][0]; g_caveLeft = (int)g_caveList[g_caveIdx][1];
    }
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
    bool  pinned;          // WowlheimGhostPlace(x, y, z) : position imposee (point accroche du serveur) au lieu de la souris
    float pinPos[3];
};
static GhostState g_ghost = { false, "", 1.0f, 0.0f, { 0.4f, 1.0f, 0.4f }, 0.5f, 0.25f, NULL, "", false, { 0, 0, 0 }, 0, 0, false, false, { 0, 0, 0 } };

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
    if (!g_ghost.havePos && !g_ghost.pinned) return;
    const float* pos = g_ghost.pinned ? g_ghost.pinPos : g_ghost.pos; // point accroche (WowlheimGhostPlace) ou souris
    if (g_ghost.def && strcmp(g_ghost.defPath, g_ghost.path) != 0) Ghost_Release("changement de modele");
    if (!g_ghost.def) {
        g_ghost.def = WorldModel_Create(g_ghost.path, pos, g_ghost.facing, 0, 0, 0, 0);
        if (!g_ghost.def) { Log("ERREUR creation du fantome \"%s\" (0x6707c0 -> NULL)", g_ghost.path); g_ghost.want = false; return; }
        WorldModel_SetFlag(g_ghost.def, 0); // meme appel que le client apres creation (0x6e5a7c)
        strcpy(g_ghost.defPath, g_ghost.path);
        Log("fantome cree \"%s\" def=%p flags=0x%08lx pos=(%.2f,%.2f,%.2f)", g_ghost.path, g_ghost.def,
            *(DWORD*)((BYTE*)g_ghost.def + DEF_FLAGS), pos[0], pos[1], pos[2]);
    }
    WorldModel_Update(g_ghost.def, pos, g_ghost.facing, 0);
    Ghost_ApplyLook();
    ++g_ghost.frames;
}

// =====================================================================================================
// Marqueurs fixes (cercle de portee des stations, Valheim CraftingStation.m_areaMarker) : jusqu'a MAX_MARKERS modeles
// poses a des positions donnees par l'addon, avec les MEMES fonctions que le fantome (0x6707c0 / 0x670d40 / 0x6709a0 /
// 0x670d50) ; aucune adresse nouvelle. Creation dans l'appel Lua (comme le fantome natif, cree par le lancement du sort
// depuis Lua : 0x6e4b60 -> 0x6e518f) si le monde est pret, sinon a la prochaine image ; liberation avant le dechargement
// de la carte et a chaque reinitialisation Lua. Les modeles deja poses sont re-positionnes par petits lots a chaque image
// (rattachement aux chunks, comme le fantome natif qui est deplace a chaque image).
// =====================================================================================================
#define MAX_MARKERS 256
struct Marker {
    bool  want;            // l'addon veut ce marqueur
    bool  dirty;           // a creer / recreer / deplacer
    char  path[MAX_PATH];
    float pos[3];
    float facing;
    float scale;
    void* def;
    char  defPath[MAX_PATH];
};
static Marker g_markers[MAX_MARKERS];
static bool   g_worldReady = false;   // une image du monde a ete vue depuis le dernier chargement de carte
static int    g_markerCursor = 0;     // re-positionnement tournant
static DWORD  g_markerCreated = 0;

static void Marker_Release(int i)
{
    Marker& m = g_markers[i];
    if (!m.def) return;
    void* d = m.def; m.def = NULL; m.defPath[0] = 0;
    __try { WorldModel_Release(d); }
    __except (EXCEPTION_EXECUTE_HANDLER) { g_ghost.faulted = true; Log("ERREUR exception en liberant le marqueur %d (%p)", i, d); }
}

static void Markers_ReleaseAll(const char* why)
{
    int n = 0;
    for (int i = 0; i < MAX_MARKERS; ++i) {
        if (g_markers[i].def) { Marker_Release(i); ++n; }
        g_markers[i].want = false; g_markers[i].dirty = false;
    }
    if (n) Log("%d marqueur(s) libere(s) (%s)", n, why);
}

// Place le modele du marqueur (position + orientation + echelle), en le creant si besoin.
static void Marker_Place(int i)
{
    Marker& m = g_markers[i];
    if (m.def && strcmp(m.defPath, m.path) != 0) Marker_Release(i);
    if (!m.def) {
        m.def = WorldModel_Create(m.path, m.pos, m.facing, 0, 0, 0, 0);
        if (!m.def) { Log("ERREUR creation du marqueur %d \"%s\" (0x6707c0 -> NULL)", i, m.path); m.want = false; m.dirty = false; return; }
        WorldModel_SetFlag(m.def, 0);
        strcpy(m.defPath, m.path);
        if (++g_markerCreated <= 3 || (g_markerCreated % 500) == 0)
            Log("marqueur %d cree \"%s\" def=%p pos=(%.2f,%.2f,%.2f) (%lu crees au total)", i, m.path, m.def, m.pos[0], m.pos[1], m.pos[2], g_markerCreated);
    }
    WorldModel_Update(m.def, m.pos, m.facing, 0);
    BYTE* d = (BYTE*)m.def;
    if (m.scale != 1.0f && (*(DWORD*)(d + DEF_FLAGS) & 0x40)) {
        float s3[3] = { m.scale, m.scale, m.scale };
        C44Matrix_Scale((float*)(d + DEF_MATRIX), NULL, s3);
        *(float*)(d + DEF_SCALE) = m.scale;
        BYTE* mm = *(BYTE**)(d + DEF_M2MODEL);
        if (mm && *(DWORD*)(mm + M2_LOADED)) DoodadDef_UpdateBounds(d);
    }
    m.dirty = false;
}

// A chaque image (hook du lancer de rayon) : marqueurs a creer, puis re-positionnement de 16 marqueurs.
static void Markers_Tick()
{
    if (g_ghost.faulted) return;
    for (int i = 0; i < MAX_MARKERS; ++i)
        if (g_markers[i].want && g_markers[i].dirty) Marker_Place(i);
    for (int k = 0; k < 16; ++k) {
        int i = g_markerCursor; g_markerCursor = (g_markerCursor + 1) % MAX_MARKERS;
        if (g_markers[i].want && g_markers[i].def) Marker_Place(i);
    }
}

typedef int (__fastcall *WorldRaycast_t)(void* self, void* edx, DWORD x, DWORD y, BYTE* hit);
static DWORD g_mouseX = 0, g_mouseY = 0; // derniers arguments x, y du lancer de rayon par image (souris sur le monde)
static bool  g_haveMouse = false;
static int __fastcall Hook_WorldRaycast(void* self, void* edx, DWORD x, DWORD y, BYTE* hit)
{
    int r = ((WorldRaycast_t)VA_WORLD_RAYCAST)(self, edx, x, y, hit);
    g_mouseX = x; g_mouseY = y; g_haveMouse = true; // coordonnees deja converties par 0x41ad80 (reutilisees par le survol)
    __try {
        if ((r == 1 || r == 2) && hit) {
            // 0x480df0 ecrit le point touche en hit+8 (C3Vector) ; c'est ce que lit 0x4820f0 pour le ciblage au sol.
            const float* p = (const float*)(hit + 8);
            g_ghost.pos[0] = p[0]; g_ghost.pos[1] = p[1]; g_ghost.pos[2] = p[2];
            g_ghost.kind = r; g_ghost.havePos = true;
        }
        g_worldReady = true;
        if (g_hwForced) { *(volatile LONG*)0xcf4dc4 = g_hwSaved; g_hwForced = false; Log("WowlheimUseHammer : drapeau clavier restaure a l'image suivante (erreur Lua ?)"); }
        Ghost_Tick();
        Markers_Tick();
    }
    __except (EXCEPTION_EXECUTE_HANDLER) {
        g_ghost.faulted = true; g_ghost.def = NULL;
        for (int i = 0; i < MAX_MARKERS; ++i) { g_markers[i].def = NULL; g_markers[i].want = false; }
        Log("ERREUR exception 0x%08lx dans la mise a jour du fantome / des marqueurs : apercu desactive", GetExceptionCode());
    }
    return r;
}

// =====================================================================================================
// Prechargement des modeles M2 (premiere pose sans temps de chargement). CM2Scene du monde = [0xc7b298] (cree au
// demarrage par 0x66f6c0, detruit a l'arret par 0x66fb00 APRES 0x6920c0 -> notre hook 0x6920cc) ; 0x707350 =
// __thiscall(scene, chemin, drapeaux) -> CM2Model* (meme appel que 0x695100 pour les doodads/gameobjects, drapeaux 0) ;
// garder le CM2Model garde le CM2Shared (fichier M2 analyse, 0x706a50) en cache ; 0x7103a0 = CM2Model::Release.
// =====================================================================================================
#define MAX_PRELOAD 512
static const DWORD VA_M2_SCENE = 0xc7b298;
typedef void* (__fastcall *M2Scene_CreateModel_t)(void* scene, void* edx, const char* path, DWORD flags); // 0x707350, RET 8
typedef int   (__fastcall *M2Model_Release_t)(void* model);                                            // 0x7103a0
static M2Scene_CreateModel_t M2Scene_CreateModel = (M2Scene_CreateModel_t)0x707350;
static M2Model_Release_t     M2Model_Release     = (M2Model_Release_t)0x7103a0;
struct Preload { char path[MAX_PATH]; void* model; };
static Preload g_preload[MAX_PRELOAD];
static int     g_preloadN = 0;
static bool    g_preloadOk = false;

static void Preload_ReleaseAll(const char* why)
{
    int n = 0;
    for (int i = 0; i < g_preloadN; ++i) {
        void* m = g_preload[i].model; g_preload[i].model = NULL;
        if (!m) continue;
        __try { M2Model_Release(m); ++n; }
        __except (EXCEPTION_EXECUTE_HANDLER) { Log("ERREUR exception en liberant le modele precharge %d", i); }
    }
    if (n) Log("%d modele(s) precharge(s) libere(s) (%s)", n, why);
    g_preloadN = 0;
}

// WowlheimPreloadModel(chemin) -> 1 (charge ou deja charge) / nil ; WowlheimPreloadModel() libere tout.
static int __fastcall Lua_PreloadModel(void* L)
{
    if (!g_preloadOk) { lua_pushnil_(L); return 1; }
    if (!lua_isstring_(L, 1)) { Preload_ReleaseAll("WowlheimPreloadModel()"); return 0; }
    const char* p = lua_tostring_(L, 1);
    if (!p || !*p || strlen(p) >= MAX_PATH) { lua_pushnil_(L); return 1; }
    for (int i = 0; i < g_preloadN; ++i)
        if (_stricmp(g_preload[i].path, p) == 0) { lua_pushnumber_(L, 1.0); return 1; }
    void* scene = *(void**)VA_M2_SCENE;
    if (!scene || g_preloadN >= MAX_PRELOAD) { lua_pushnil_(L); return 1; }
    void* m = NULL;
    __try { m = M2Scene_CreateModel(scene, NULL, p, 0); }
    __except (EXCEPTION_EXECUTE_HANDLER) { Log("ERREUR exception en prechargeant \"%s\" : prechargement desactive", p); g_preloadOk = false; }
    if (!m) { lua_pushnil_(L); return 1; }
    strcpy(g_preload[g_preloadN].path, p); g_preload[g_preloadN].model = m; ++g_preloadN;
    if (g_preloadN <= 3 || (g_preloadN % 50) == 0) Log("modele precharge \"%s\" (%d au total)", p, g_preloadN);
    lua_pushnumber_(L, 1.0);
    return 1;
}

// =====================================================================================================
// Apparition instantanee. A la creation d'un objet (CGObject_C 0x613af0, appele par CGGameObject_C 0x5f7c40 et CGUnit_C
// 0x5fb880) et a sa reapparition (0x614640), le client lance un fondu d'alpha de 2000 ms (vtable+0x68 != 0) par
// SetAlphaTarget 0x614f80 : +0xec debut, +0xf0 duree, +0xf8 depart, +0xfc cible, +0xf4 courant ; 0x614a90 (mise a jour
// par image) applique alpha = depart + (cible - depart) * t^3 (0,5 s -> 1,6 %, 1 s -> 12,5 %) : la piece parait
// apparaitre avec ~1 s de retard. Apres l'appel d'origine, pour les entrees Wowlheim, on termine le fondu :
// duree = 0 et courant = cible (meme etat que SetAlphaTarget(cible, 0)).
// =====================================================================================================
static bool  g_fadeOk = false;
static DWORD g_instGoMin = 9110000, g_instGoMax = 9119999;     // pieces Wowlheim (gameobjects)
static DWORD g_instUnitMin = 9300000, g_instUnitMax = 9300099; // creatures 93000xx (arbres, buches, roches)
static DWORD g_instPickMin = 9130000, g_instPickMax = 9139999; // ramassables de Valheim (gameobjects 9130001+)
static DWORD g_instantCount = 0;

// Objet Wowlheim dont le fondu (apparition / disparition) est supprime ? 1 = gameobject, 2 = creature, 0 = non.
// Lit les descripteurs (+8 : +0 GUID, +8 OBJECT_FIELD_TYPE, +0xc ENTRY) ; l'appelant protege par __try.
static int InstantKind(const BYTE* obj, DWORD* entryOut)
{
    if (!obj) return 0;
    const BYTE* desc = *(const BYTE* const*)(obj + 8);
    if (!desc) return 0;
    DWORD type = *(const DWORD*)(desc + 8), entry = *(const DWORD*)(desc + 0xc);
    if (entryOut) *entryOut = entry;
    if (type == 0x21 && ((entry >= g_instGoMin && entry <= g_instGoMax) || (entry >= g_instPickMin && entry <= g_instPickMax))) return 1;
    if (type == 0x09 && entry >= g_instUnitMin && entry <= g_instUnitMax) return 2;
    return 0;
}

static void InstantFade(BYTE* obj)
{
    __try {
        DWORD entry = 0;
        int kind = InstantKind(obj, &entry);
        bool go = kind == 1;
        if (!kind) return;
        if (*(DWORD*)(obj + 0xf0) == 0) return;
        *(DWORD*)(obj + 0xf0) = 0;                          // duree du fondu
        *(DWORD*)(obj + 0xf4) = *(DWORD*)(obj + 0xfc);      // alpha courant = cible
        if (++g_instantCount <= 3 || (g_instantCount % 200) == 0)
            Log("apparition instantanee : %s entree %lu (%lu au total)", go ? "gameobject" : "creature", entry, g_instantCount);
    }
    __except (EXCEPTION_EXECUTE_HANDLER) { g_fadeOk = false; Log("ERREUR exception dans InstantFade : desactive"); }
}
// 0x613af0 : __thiscall(obj, 3 arguments inutilises par le fondu), RET 0xc
static void __fastcall Hook_ObjInitFade(BYTE* obj, void* edx, DWORD a, DWORD b, DWORD c)
{
    ((void (__fastcall*)(BYTE*, void*, DWORD, DWORD, DWORD))0x613af0)(obj, edx, a, b, c);
    if (g_fadeOk) InstantFade(obj);
}
// 0x614640 : __fastcall(obj), RET
static void __fastcall Hook_ObjReshowFade(BYTE* obj)
{
    ((void (__fastcall*)(BYTE*))0x614640)(obj);
    if (g_fadeOk) InstantFade(obj);
}

// WowlheimSetInstantFade(goMin, goMax [, unitMin, unitMax [, pickMin, pickMax]]) ; WowlheimSetInstantFade(0) desactive
// (apparition ET disparition) ; sans argument : renvoie actif (1/nil), goMin, goMax, unitMin, unitMax, pickMin, pickMax,
// disparition instantanee active (1/nil). Les ramassables (9130000-9139999) sont couverts par defaut.
static bool g_despawnOk = false;
static int __fastcall Lua_SetInstantFade(void* L)
{
    if (!lua_isnumber_(L, 1)) {
        if (!g_fadeOk) { lua_pushnil_(L); return 1; }
        lua_pushnumber_(L, 1.0);
        lua_pushnumber_(L, (double)g_instGoMin); lua_pushnumber_(L, (double)g_instGoMax);
        lua_pushnumber_(L, (double)g_instUnitMin); lua_pushnumber_(L, (double)g_instUnitMax);
        lua_pushnumber_(L, (double)g_instPickMin); lua_pushnumber_(L, (double)g_instPickMax);
        if (g_despawnOk) lua_pushnumber_(L, 1.0); else lua_pushnil_(L);
        return 8;
    }
    DWORD a = (DWORD)lua_tonumber_(L, 1);
    if (a == 0) { g_instGoMin = 1; g_instGoMax = 0; g_instUnitMin = 1; g_instUnitMax = 0; g_instPickMin = 1; g_instPickMax = 0; return 0; }
    g_instGoMin = a;
    g_instGoMax = lua_isnumber_(L, 2) ? (DWORD)lua_tonumber_(L, 2) : a;
    if (lua_isnumber_(L, 3)) {
        g_instUnitMin = (DWORD)lua_tonumber_(L, 3);
        g_instUnitMax = lua_isnumber_(L, 4) ? (DWORD)lua_tonumber_(L, 4) : g_instUnitMin;
    }
    if (lua_isnumber_(L, 5)) {
        g_instPickMin = (DWORD)lua_tonumber_(L, 5);
        g_instPickMax = lua_isnumber_(L, 6) ? (DWORD)lua_tonumber_(L, 6) : g_instPickMin;
    }
    Log("apparition/disparition instantanees : gameobjects %lu-%lu et %lu-%lu, creatures %lu-%lu", g_instGoMin, g_instGoMax,
        g_instPickMin, g_instPickMax, g_instUnitMin, g_instUnitMax);
    return 0;
}

// =====================================================================================================
// Disparition instantanee (Valheim : WearNTear.Destroy / Pickable -> ZNetScene.Destroy, l'objet disparait a l'image
// suivante). A la destruction d'un objet (SMSG_DESTROY_OBJECT 0x4674a0 -> 0x464920 -> vtable+4 ; hors de portee : meme
// chemin), CGObject_C::Disappear 0x6145e0 (CGGameObject_C 0x5f7e40 y saute ; CGUnit_C passe par 0x5fbe80) ne libere pas
// le modele : 0x672df0(def [obj+0xe0], alpha courant) l'accroche a une liste "SWModelFadeout" (0xc7b2d4/0xc7b2d8) que
// 0x672ef0 fait passer de alpha a 0 en 2000 ms (CMP EAX,0x7d0 en 0x672f36) avant 0x671ac0 (liberation). Si alpha < 0.01
// ([0x8029d0]) ou M2 non charge, 0x672df0 appelle directement 0x671ac0. On remplace les deux CALL 0x672df0 (0x614603,
// 0x5fbf30) par un relais qui lit l'objet dans ESI (MOV ESI,ECX en tete des deux fonctions, ESI preserve jusqu'au CALL)
// et, pour une entree Wowlheim, passe alpha = 0 : meme chemin que le client pour un objet deja invisible.
// =====================================================================================================
static const DWORD VA_MODEL_FADEOUT = 0x672df0; // __thiscall(def, float alpha), RET 4
static BYTE* volatile g_fadeoutObj = NULL;
static DWORD g_despawnCount = 0;
static void __fastcall Hook_ModelFadeout(void* def, void* edx, float alpha)
{
    BYTE* obj = g_fadeoutObj; g_fadeoutObj = NULL;
    if (g_despawnOk && obj) {
        __try {
            DWORD entry = 0;
            int kind = InstantKind(obj, &entry);
            if (kind) {
                alpha = 0.0f;
                if (++g_despawnCount <= 3 || (g_despawnCount % 200) == 0)
                    Log("disparition instantanee : %s entree %lu (%lu au total)", kind == 1 ? "gameobject" : "creature", entry, g_despawnCount);
            }
        }
        __except (EXCEPTION_EXECUTE_HANDLER) { g_despawnOk = false; Log("ERREUR exception dans Hook_ModelFadeout : disparition instantanee desactivee"); }
    }
    ((void (__fastcall*)(void*, void*, float))VA_MODEL_FADEOUT)(def, edx, alpha);
}
// Cible des CALL 0x614603 / 0x5fbf30 : ESI = objet (voir ci-dessus), pile et registres d'arguments intacts.
__declspec(naked) static void Stub_ModelFadeout()
{
    __asm {
        mov g_fadeoutObj, esi
        jmp Hook_ModelFadeout
    }
}

// =====================================================================================================
// Objet sous le curseur (mode construction, clic milieu = detruire). Le lancer de rayon 0x481190 selectionne les objets
// selon un masque calcule par 0x481050 (appel en 0x4812c1) : hors ciblage 0x5c (4 = gameobjects), pendant un ciblage
// au sol (sort 40001, [0xcecac0] & 0x60) seulement 3 (terrain) -> aucun gameobject n'est teste ; de plus le filtre
// 0x480780 (cas 0x21) refuse les gameobjects pendant un ciblage qui ne vise pas d'objet ([0xcecac0] & 0x4800).
// On refait donc, a la demande, le meme lancer de rayon que le client (CGWorldFrame [0xb4b2bc], coordonnees souris de
// la derniere image) avec le masque force a 4 (gameobjects seulement ; 0x480df0 compare toujours a la distance du
// terrain/WMO : un objet cache par le relief n'est pas pris) et [0xcecac0] mis a 0 pendant l'appel. Le client fait de
// meme hors image : 0x514810 -> 0x481f00 appelle 0x481190 avec [0xb4b2bc]. Resultat : hit+0 = GUID, hit+8 = point.
// =====================================================================================================
static const DWORD VA_WORLDFRAME_PTR   = 0xb4b2bc; // CGWorldFrame* (ecrit par le constructeur 0x481960, remis a 0 par 0x481d30)
static const DWORD VA_CALLSITE_PICKMASK = 0x4812c1; // CALL 0x481050 dans 0x481190
static const DWORD VA_PICKMASK         = 0x481050;
static const DWORD VA_SPELL_TARGETING  = 0xcecac0; // drapeaux de cible du sort en ciblage (0 = pas de ciblage)
typedef void* (__stdcall *ObjectPtr_t)(DWORD guidLo, DWORD guidHi); // 0x464870 -> CGObject_C* ou NULL
static ObjectPtr_t ClntObjMgrObjectPtr = (ObjectPtr_t)0x464870;
static bool  g_pickOk = false;
static DWORD g_forcePickMask = 0;

static DWORD __fastcall Hook_PickMask(void* self)
{
    if (g_forcePickMask) return g_forcePickMask;
    return ((DWORD (__fastcall*)(void*))VA_PICKMASK)(self);
}

// WowlheimGetMouseoverObject() -> guidHex ("F1100...", 16 chiffres), entree, guidLo, guidHi, x, y, z ; nil si aucun
// gameobject sous le curseur (ou souris hors du monde / API inactive).
static int __fastcall Lua_GetMouseoverObject(void* L)
{
    void* wf = *(void**)VA_WORLDFRAME_PTR;
    if (!g_pickOk || !g_haveMouse || !wf) { lua_pushnil_(L); return 1; }
    BYTE hit[0x40]; memset(hit, 0, sizeof hit);
    DWORD savedTarget = *(DWORD*)VA_SPELL_TARGETING;
    int r = 0;
    __try {
        *(DWORD*)VA_SPELL_TARGETING = 0;
        g_forcePickMask = 4;
        r = ((WorldRaycast_t)VA_WORLD_RAYCAST)(wf, NULL, g_mouseX, g_mouseY, hit);
    }
    __except (EXCEPTION_EXECUTE_HANDLER) { g_pickOk = false; r = 0; Log("ERREUR exception 0x%08lx dans WowlheimGetMouseoverObject : desactive", GetExceptionCode()); }
    g_forcePickMask = 0;
    *(DWORD*)VA_SPELL_TARGETING = savedTarget;
    if (r != 2) { lua_pushnil_(L); return 1; }
    DWORD lo = *(DWORD*)hit, hi = *(DWORD*)(hit + 4), entry = 0;
    __try {
        BYTE* obj = (BYTE*)ClntObjMgrObjectPtr(lo, hi);
        const BYTE* desc = obj ? *(const BYTE**)(obj + 8) : NULL;
        if (!desc || *(const DWORD*)(desc + 8) != 0x21) { lua_pushnil_(L); return 1; }
        entry = *(const DWORD*)(desc + 0xc);
    }
    __except (EXCEPTION_EXECUTE_HANDLER) { lua_pushnil_(L); return 1; }
    char hex[24]; _snprintf(hex, sizeof hex, "%08lX%08lX", hi, lo); hex[sizeof hex - 1] = 0;
    const float* p = (const float*)(hit + 8);
    lua_pushstring_(L, hex);
    lua_pushnumber_(L, (double)entry);
    lua_pushnumber_(L, (double)lo);
    lua_pushnumber_(L, (double)hi);
    lua_pushnumber_(L, p[0]); lua_pushnumber_(L, p[1]); lua_pushnumber_(L, p[2]);
    return 7;
}

// =====================================================================================================
// Surbrillance de la piece visee (Valheim : Player.UpdateWearNTearHover -> WearNTear.Highlight en mode construction :
// _Color = couleur, _EmissionColor = couleur * 0.4, remis a l'origine 0,2 s apres le dernier appel). Ici le CM2Model de
// l'objet ([obj+0xdc], sinon [obj+0xd8], comme 0x614a90 / 0x6144f0) recoit la couleur diffuse (+0x184, multipliee, comme
// 0x710cf0) et emissive (+0x190, ajoutee a l'ambiant, comme 0x710d40). Pour un gameobject, le client n'ecrit ces champs
// que dans CGObject_C::SetHighlight / ClearHighlight (0x614550 / 0x6144f0 ; masque [obj+0xb8] : survol natif, cible) :
// l'addon reapplique la surbrillance a chaque image ; a l'arret, diffuse d'origine et emissif d'origine (0 si le masque
// natif est vide, comme 0x6144f0). L'objet est retrouve par son GUID (0x464870) a chaque appel : aucun pointeur garde
// d'une image a l'autre, sauf pour comparer (modele remplace -> rien a remettre).
// =====================================================================================================
struct HighlightState { bool on; DWORD lo, hi; BYTE* model; float diff[3], emis[3]; DWORD count; };
static HighlightState g_hl = { false, 0, 0, NULL, { 1, 1, 1 }, { 0, 0, 0 }, 0 };
static bool g_hlOk = false;
static const int OBJ_HIGHLIGHT_MASK = 0xb8; // masque des surbrillances natives (0x614550 / 0x6144f0)

static BYTE* Highlight_Model(BYTE* obj)
{
    BYTE* m = *(BYTE**)(obj + 0xdc);
    return m ? m : *(BYTE**)(obj + 0xd8);
}

static void Highlight_Clear(bool restore)
{
    if (!g_hl.on) return;
    g_hl.on = false;
    if (!restore || !g_hlOk) return;
    __try {
        BYTE* obj = (BYTE*)ClntObjMgrObjectPtr(g_hl.lo, g_hl.hi);
        BYTE* m = obj ? Highlight_Model(obj) : NULL;
        if (!m || m != g_hl.model) return;                     // objet detruit ou modele remplace : rien a remettre
        bool native = *(DWORD*)(obj + OBJ_HIGHLIGHT_MASK) != 0;
        for (int i = 0; i < 3; ++i) {
            ((float*)(m + M2_DIFFUSE))[i]  = g_hl.diff[i];
            ((float*)(m + M2_EMISSIVE))[i] = native ? g_hl.emis[i] : 0.0f;
        }
    }
    __except (EXCEPTION_EXECUTE_HANDLER) { g_hlOk = false; Log("ERREUR exception 0x%08lx en retirant la surbrillance : desactivee", GetExceptionCode()); }
}

static bool ParseGuidHex(const char* s, DWORD* lo, DWORD* hi)
{
    if (!s) return false;
    if (s[0] == '0' && (s[1] == 'x' || s[1] == 'X')) s += 2;
    size_t n = strlen(s);
    if (n == 0 || n > 16) return false;
    unsigned __int64 v = 0;
    for (size_t i = 0; i < n; ++i) {
        int d = HexNib((char)(s[i] >= 'A' && s[i] <= 'F' ? s[i] - 'A' + 'a' : s[i]));
        if (d < 0) return false;
        v = (v << 4) | (unsigned)d;
    }
    *lo = (DWORD)v; *hi = (DWORD)(v >> 32);
    return true;
}

// WowlheimHighlightObject(guidHex, r, g, b [, lueur=0.4]) -> 1 (applique) / nil (objet absent, sans modele, API inactive) ;
// WowlheimHighlightObject() retire la surbrillance. Couleur diffuse = (r,g,b), emissif = (r,g,b) * lueur.
static int __fastcall Lua_HighlightObject(void* L)
{
    if (!lua_isstring_(L, 1)) { Highlight_Clear(true); return 0; }
    DWORD lo = 0, hi = 0;
    if (!g_hlOk || !ParseGuidHex(lua_tostring_(L, 1), &lo, &hi)) { Highlight_Clear(true); lua_pushnil_(L); return 1; }
    float rgb[3] = { 0.6f, 0.8f, 1.0f }, glow = 0.4f;   // Valheim : couleur d'une piece sans calcul de support
    for (int i = 0; i < 3; ++i) if (lua_isnumber_(L, 2 + i)) rgb[i] = (float)lua_tonumber_(L, 2 + i);
    if (lua_isnumber_(L, 5)) glow = (float)lua_tonumber_(L, 5);
    for (int i = 0; i < 3; ++i) rgb[i] = rgb[i] < 0 ? 0 : rgb[i] > 2 ? 2 : rgb[i];
    glow = glow < 0 ? 0 : glow > 2 ? 2 : glow;
    BYTE* obj = NULL; BYTE* m = NULL;
    __try {
        obj = (BYTE*)ClntObjMgrObjectPtr(lo, hi);
        m = obj ? Highlight_Model(obj) : NULL;
    }
    __except (EXCEPTION_EXECUTE_HANDLER) { obj = NULL; m = NULL; }
    if (g_hl.on && (g_hl.lo != lo || g_hl.hi != hi || g_hl.model != m)) Highlight_Clear(true);
    if (!m) { lua_pushnil_(L); return 1; }
    __try {
        if (!g_hl.on) {
            for (int i = 0; i < 3; ++i) { g_hl.diff[i] = ((float*)(m + M2_DIFFUSE))[i]; g_hl.emis[i] = ((float*)(m + M2_EMISSIVE))[i]; }
            g_hl.on = true; g_hl.lo = lo; g_hl.hi = hi; g_hl.model = m;
            if (++g_hl.count <= 3 || (g_hl.count % 200) == 0)
                Log("surbrillance %08lX%08lX modele=%p (%.2f,%.2f,%.2f) lueur %.2f (%lu au total)", hi, lo, m, rgb[0], rgb[1], rgb[2], glow, g_hl.count);
        }
        for (int i = 0; i < 3; ++i) {
            ((float*)(m + M2_DIFFUSE))[i]  = rgb[i];
            ((float*)(m + M2_EMISSIVE))[i] = rgb[i] * glow;
        }
    }
    __except (EXCEPTION_EXECUTE_HANDLER) {
        g_hlOk = false; g_hl.on = false;
        Log("ERREUR exception 0x%08lx dans WowlheimHighlightObject : desactivee", GetExceptionCode());
        lua_pushnil_(L); return 1;
    }
    lua_pushnumber_(L, 1.0);
    return 1;
}

typedef void (__fastcall *MapUnload_t)(void* ecx, void* edx);
static void __fastcall Hook_MapUnload(void* ecx, void* edx)
{
    Highlight_Clear(false); // tous les objets vont etre detruits : rien a remettre
    // Le monde va liberer toutes ses defs de modeles : on libere la notre avant (comme l'annulation du ciblage natif).
    if (g_ghost.def) Ghost_Release("dechargement de la carte");
    g_ghost.want = false; g_ghost.havePos = false; g_ghost.pinned = false;
    Markers_ReleaseAll("dechargement de la carte");
    Preload_ReleaseAll("dechargement de la carte");
    g_worldReady = false; g_haveMouse = false;
    ((MapUnload_t)VA_MAP_UNLOAD)(ecx, edx);
}

static bool LuaNum(void* L, int idx, float* out) { if (!lua_isnumber_(L, idx)) return false; *out = (float)lua_tonumber_(L, idx); return true; }
static float Clamp01(float v) { return v < 0 ? 0 : v > 1 ? 1 : v; }

// Voie native (sort de pose 40001, section plus bas) : etat partage avec WowlheimGhostGetPos / WowlheimGhostSetColor
static const DWORD VA_NATIVE_GHOST = 0xceca8c; // def du fantome natif (lu par 0x6e6970)
static const DWORD VA_TARGET_RANGE = 0x83dc2c; // 0 point dans la portee du sort, 1 hors portee, 3 avant calcul (0x4820f0)
static bool  g_nativeOk = false;
static float g_nativeLastFacing = 0.0f; // derniere orientation donnee au fantome natif (WowlheimGhostGetPos, 7e valeur)
// Teinte du fantome natif (WowlheimGhostSetColor(..., 1)) : appliquee a chaque image au CM2Model de [0xceca8c]
static bool  g_nativeTint = false;
static bool  g_nativeTintRestore = false; // une derniere ecriture neutre (1,1,1, alpha 1, sans lueur) apres l'arret
static float g_nativeRgb[3] = { 1.0f, 1.0f, 1.0f };
static float g_nativeAlpha = 1.0f;
static float g_nativeGlow = 0.0f;

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
    g_ghost.pinned = false;
    Ghost_Release("WowlheimGhostHide");
    return 0;
}

// WowlheimGhostPlace(x, y, z) : le fantome DLL est pose a ce point (position apres accroche renvoyee par le serveur,
// `.build api canplace` -> CP|ok|x|y|z|o|accroche) au lieu du point sous la souris ; WowlheimGhostPlace() : retour a la
// souris. WowlheimGhostGetPos renvoie toujours le point sous la souris. Remis a zero par WowlheimGhostHide.
static int __fastcall Lua_GhostPlace(void* L)
{
    float x, y, z;
    if (LuaNum(L, 1, &x) && LuaNum(L, 2, &y) && LuaNum(L, 3, &z)) {
        g_ghost.pinPos[0] = x; g_ghost.pinPos[1] = y; g_ghost.pinPos[2] = z;
        g_ghost.pinned = true;
    } else {
        g_ghost.pinned = false;
    }
    return 0;
}

// WowlheimGhostGetPos() -> x, y, z, orientation, type (1 sol/WMO, 2 objet) [, portee, orientationNative] ; nil si aucun point
//   portee (voie native active) : [0x83dc2c] du ciblage au sol, 0 = point dans la portee du sort, 1 = hors portee, 3 = pas
//   encore calcule ; orientationNative : derniere orientation donnee au fantome natif (Hook_NativeFacing).
// Pas de nouvelle API : les deux caves de trampolines sont pleines (14 / 14), on etend les fonctions existantes.
static int __fastcall Lua_GhostGetPos(void* L)
{
    if (!g_ghost.havePos) { lua_pushnil_(L); return 1; }
    lua_pushnumber_(L, g_ghost.pos[0]);
    lua_pushnumber_(L, g_ghost.pos[1]);
    lua_pushnumber_(L, g_ghost.pos[2]);
    lua_pushnumber_(L, g_ghost.facing);
    lua_pushnumber_(L, (double)g_ghost.kind);
    if (!g_nativeOk) return 5;
    lua_pushnumber_(L, (double)*(volatile DWORD*)VA_TARGET_RANGE);
    lua_pushnumber_(L, g_nativeLastFacing);
    return 7;
}

// WowlheimGhostSetColor(r, g, b [, a [, lueur [, cible]]]) : composantes 0..1 ; lueur = part de (r,g,b) ajoutee en emissif.
//   cible absente / 0 : fantome DLL (WowlheimGhostShow) ; cible 1 : fantome NATIF du sort de pose (teinte appliquee a chaque
//   image ; defauts a = 1, lueur = 0) ; cible -1 : fin de la teinte du fantome natif (retour neutre).
static int __fastcall Lua_GhostSetColor(void* L)
{
    float v, target = 0.0f;
    LuaNum(L, 6, &target);
    if (target < 0.0f) {
        if (g_nativeTint) g_nativeTintRestore = true;
        g_nativeTint = false;
        return 0;
    }
    if (target > 0.0f) {
        if (!g_nativeOk) return 0;
        for (int i = 0; i < 3; ++i) g_nativeRgb[i] = LuaNum(L, i + 1, &v) ? Clamp01(v) : 1.0f;
        g_nativeAlpha = LuaNum(L, 4, &v) ? Clamp01(v) : 1.0f;
        g_nativeGlow = LuaNum(L, 5, &v) ? Clamp01(v) : 0.0f;
        g_nativeTint = true; g_nativeTintRestore = false;
        return 0;
    }
    for (int i = 0; i < 3; ++i) if (LuaNum(L, i + 1, &v)) g_ghost.rgb[i] = Clamp01(v);
    if (LuaNum(L, 4, &v)) g_ghost.alpha = Clamp01(v);
    if (LuaNum(L, 5, &v)) g_ghost.glow = Clamp01(v);
    return 0;
}

// WowlheimMarkerShow(id, cheminModele, x, y, z [, orientation [, echelle]]) -> 1 / nil
//   id 0..255 ; reappeler avec le meme id deplace le marqueur (ou change son modele).
static int __fastcall Lua_MarkerShow(void* L)
{
    float fid, x, y, z, o = 0.0f, s = 1.0f;
    if (!g_ghostOk || g_ghost.faulted || !LuaNum(L, 1, &fid) || !lua_isstring_(L, 2) || !LuaNum(L, 3, &x) || !LuaNum(L, 4, &y) || !LuaNum(L, 5, &z)) {
        lua_pushnil_(L); return 1;
    }
    int id = (int)fid;
    const char* p = lua_tostring_(L, 2);
    if (id < 0 || id >= MAX_MARKERS || !p || !*p || strlen(p) >= MAX_PATH) { lua_pushnil_(L); return 1; }
    LuaNum(L, 6, &o);
    if (LuaNum(L, 7, &s) && (s < 0.01f || s > 100.0f)) s = 1.0f;
    const float twoPi = 6.28318530718f;
    while (o < 0) o += twoPi;
    while (o >= twoPi) o -= twoPi;
    Marker& m = g_markers[id];
    bool same = m.want && m.def && strcmp(m.path, p) == 0 && m.pos[0] == x && m.pos[1] == y && m.pos[2] == z && m.facing == o && m.scale == s;
    if (!same) {
        strcpy(m.path, p);
        m.pos[0] = x; m.pos[1] = y; m.pos[2] = z; m.facing = o; m.scale = s;
        m.want = true; m.dirty = true;
        if (g_worldReady) {
            __try { Marker_Place(id); }
            __except (EXCEPTION_EXECUTE_HANDLER) {
                g_ghost.faulted = true; m.def = NULL; m.want = false;
                Log("ERREUR exception 0x%08lx en posant le marqueur %d : apercu desactive", GetExceptionCode(), id);
                lua_pushnil_(L); return 1;
            }
        }
    }
    lua_pushnumber_(L, 1.0);
    return 1;
}

// WowlheimMarkerHide(id) masque un marqueur ; WowlheimMarkerHide() les masque tous.
static int __fastcall Lua_MarkerHide(void* L)
{
    float fid;
    if (LuaNum(L, 1, &fid)) {
        int id = (int)fid;
        if (id >= 0 && id < MAX_MARKERS) { g_markers[id].want = false; g_markers[id].dirty = false; Marker_Release(id); }
    } else {
        Markers_ReleaseAll("WowlheimMarkerHide()");
    }
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
static bool  g_placeFacingSet = false;
static bool  g_placeFacingRel = false;  // vrai : g_placeFacing est AJOUTE a l'orientation native (joueur) a chaque image
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

// WowlheimSetPlaceFacing(radians) impose l'orientation du fantome natif ; WowlheimSetPlaceFacing(radians, 1) l'AJOUTE a
// l'orientation native recalculee a chaque image (celle du joueur : le serveur pose avec orientation du joueur + rot x 22,5
// deg, server/Wowlheim/BuildPlacement.cpp PlaceFromSpell) ; WowlheimSetPlaceFacing() (sans argument) rend la main au
// client (orientation du joueur ; mode maison : [0xcecad4], +pi/2 par clic droit).
static float NormAngle(float f)
{
    const float twoPi = 6.28318530718f;
    while (f < 0) f += twoPi;
    while (f >= twoPi) f -= twoPi;
    return f;
}
static int __fastcall Lua_SetPlaceFacing(void* L)
{
    float f, rel = 0.0f;
    if (LuaNum(L, 1, &f)) {
        g_placeFacing = NormAngle(f); g_placeFacingSet = true;
        g_placeFacingRel = LuaNum(L, 2, &rel) && rel != 0.0f;
    } else {
        g_placeFacingSet = false; g_placeFacingRel = false;
    }
    return 0;
}

// =====================================================================================================
// WowlheimUseHammer(slot) : UseInventoryItem(slot) comme si le joueur avait appuye sur une touche (pose en chaine).
// Pourquoi UseInventoryItem(16) appele par l'addon depuis OnUpdate / un evenement ne demarre pas le ciblage alors que
// /script UseInventoryItem(16) tape au clavier le fait : Spell_C_CastSpell (0x6e4b60) appelle CanPerformAction(2)
// (0x494a50, en 0x6e4bc1) et abandonne SANS message s'il renvoie 0. 0x494a50 : si [0xceeac0] (souillure : != 0 pendant
// l'execution du code d'un addon ; remise a 0 par 0x4b7ad0 pour les commandes tapees, qui met aussi [[0xb71290]+0xd8]=1)
// est non nul, le mode 2 n'est autorise que si [0xcf4dc4] (0x77e430 : evenement clavier en cours, mis a 1 / 0 autour du
// script d'un raccourci en 0x77b438 / 0x77b459) ou [0xcf4da0] (0x779890 : clic souris en cours) ou [[0xb71290]+0xd8]
// est non nul. On met donc [0xcf4dc4] a 1 le temps d'appeler la fonction C d'origine de UseInventoryItem (0x4c8de0,
// lue dans la table Lua 0x848518), puis on remet l'ancienne valeur. [0xcf4dc4] n'est lu que par 0x77e430, lui-meme appele
// seulement par 0x494a50 (0x494a92, 0x494b1a) : aucun autre effet. Le slot est valide ici (1..23, meme borne que 0x4c8520)
// pour que 0x4c8de0 ne leve jamais d'erreur Lua (longjmp) pendant que le drapeau est force.
// Renvoie 1 si le ciblage d'un sort est en cours apres l'appel (Spell_C_IsTargeting 0x6e48a0), sinon nil.
// =====================================================================================================
static const DWORD VA_LUA_USEINVITEM = 0x4c8de0;
static const DWORD VA_HW_KEY_EVENT    = 0xcf4dc4;
typedef int  (__fastcall *LuaCFunction_t)(void* L);
typedef bool (__cdecl *Spell_IsTargeting_t)();
static bool g_useOk = false;

static int __fastcall Lua_UseHammer(void* L)
{
    // slot obligatoire (l'addon passe 16) ; borne testee en double comme 0x4c8520 (ftol 0x40a2b0 puis 1..23)
    double f = lua_isnumber_(L, 1) ? lua_tonumber_(L, 1) : 0.0;
    if (!g_useOk || !(f >= 1.0 && f < 24.0)) { lua_pushnil_(L); return 1; }
    volatile LONG* hw = (volatile LONG*)VA_HW_KEY_EVENT;
    g_hwSaved = *hw; g_hwForced = true; *hw = 1;
    __try { ((LuaCFunction_t)VA_LUA_USEINVITEM)(L); }
    __except (EXCEPTION_EXECUTE_HANDLER) { Log("ERREUR exception 0x%08lx dans WowlheimUseHammer", GetExceptionCode()); }
    *hw = g_hwSaved; g_hwForced = false;
    bool targeting = ((Spell_IsTargeting_t)0x6e48a0)();
    Log("WowlheimUseHammer(%d) -> ciblage %s", (int)f, targeting ? "oui" : "non");
    if (targeting) lua_pushnumber_(L, 1.0); else lua_pushnil_(L);
    return 1;
}

// Teinte du fantome natif : memes champs du CM2Model que le fantome DLL (Ghost_ApplyLook). La def [0xceca8c] est celle que
// 0x4820f0 passe a 0x6709a0 juste apres notre hook (0x6e6970 -> ESI) : valide pendant ce rappel.
static void NativeGhost_ApplyTint()
{
    if (!g_nativeTint && !g_nativeTintRestore) return;
    __try {
        BYTE* d = *(BYTE**)VA_NATIVE_GHOST;
        if (!d || !(*(DWORD*)(d + DEF_FLAGS) & 0x40)) return;   // pas de fantome / WMO
        BYTE* m = *(BYTE**)(d + DEF_M2MODEL);
        if (!m) return;
        bool on = g_nativeTint;
        *(float*)(m + M2_ALPHA) = on ? g_nativeAlpha : 1.0f;
        for (int i = 0; i < 3; ++i) {
            ((float*)(m + M2_DIFFUSE))[i]  = on ? g_nativeRgb[i] : 1.0f;
            ((float*)(m + M2_EMISSIVE))[i] = on ? g_nativeRgb[i] * g_nativeGlow : 0.0f;
        }
        if (!on) g_nativeTintRestore = false;
    }
    __except (EXCEPTION_EXECUTE_HANDLER) {
        g_nativeTint = false; g_nativeTintRestore = false;
        Log("ERREUR exception 0x%08lx en teintant le fantome natif : teinte desactivee", GetExceptionCode());
    }
}

// Remplace le CALL 0x6e6980 de 0x4820f0 : renvoie (dans ST0) l'orientation passee a 0x6709a0 pour le fantome natif.
// Appele a chaque image pendant le ciblage au sol quand le rayon touche le sol : on y teinte aussi le fantome natif.
static float __cdecl Hook_NativeFacing()
{
    float f = ((float (__cdecl*)())VA_NATIVE_FACING)();   // conserve le comportement d'origine (ecrit [0xcecad4])
    if (g_placeFacingSet) f = g_placeFacingRel ? NormAngle(f + g_placeFacing) : g_placeFacing;
    g_nativeLastFacing = f;
    NativeGhost_ApplyTint();
    return f;
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
    { "WowlheimMarkerShow",     (void*)&Lua_MarkerShow,     1, NULL },
    { "WowlheimMarkerHide",     (void*)&Lua_MarkerHide,     1, NULL },
    { "WowlheimGetMouseoverObject", (void*)&Lua_GetMouseoverObject, 3, NULL },
    { "WowlheimSetInstantFade",     (void*)&Lua_SetInstantFade,     4, NULL },
    { "WowlheimPreloadModel",       (void*)&Lua_PreloadModel,       5, NULL },
    { "WowlheimHighlightObject",    (void*)&Lua_HighlightObject,    7, NULL },
    { "WowlheimGhostPlace",         (void*)&Lua_GhostPlace,         1, NULL },
    { "WowlheimUseHammer",          (void*)&Lua_UseHammer,          8, NULL },
};

static int __cdecl Hook_InitLua()
{
    int r = ((int (__cdecl*)())VA_FRAMESCRIPT_INIT)();   // comportement d'origine
    Log("FrameScript_Initialize termine (retour %d), lua_State global [0xceef74]=%p", r, *(void**)0xceef74);
    // Nouvel etat Lua (demarrage, ReloadUI, changement de personnage) : l'addon qui pilotait le fantome a disparu.
    g_ghost.want = false; g_ghost.pinned = false;
    if (g_ghost.def) Ghost_Release("reinitialisation Lua");
    if (g_nativeTint) g_nativeTintRestore = true;   // teinte / orientation du fantome natif : etat de l'ancien addon
    g_nativeTint = false;
    g_placeFacingSet = false; g_placeFacingRel = false;
    Markers_ReleaseAll("reinitialisation Lua");
    Highlight_Clear(true); // l'addon qui reappliquait la surbrillance a chaque image a disparu
    int n = 0;
    for (size_t i = 0; i < sizeof g_api / sizeof g_api[0]; ++i) {
        LuaApi& a = g_api[i];
        if ((a.group == 1 && !g_ghostOk) || (a.group == 2 && !g_nativeOk) || (a.group == 3 && !g_pickOk) ||
            (a.group == 4 && !g_fadeOk) || (a.group == 5 && !g_preloadOk) || (a.group == 7 && !g_hlOk) ||
            (a.group == 8 && !g_useOk)) continue;
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
        "  WowlheimMarkerHide() "
        "end "
        "if WowlheimGetMouseoverObject then WowlheimPing('mouseover=' .. tostring(WowlheimGetMouseoverObject())) end "
        "if WowlheimSetInstantFade then local a, b, c, d, e, f, g, h = WowlheimSetInstantFade() WowlheimPing('instant fade=' .. tostring(a) .. ' ' .. tostring(b) .. '-' .. tostring(c) .. ' pick ' .. tostring(f) .. '-' .. tostring(g) .. ' despawn=' .. tostring(h)) end "
        "if WowlheimHighlightObject then WowlheimHighlightObject() WowlheimPing('highlight absent=' .. tostring(WowlheimHighlightObject('0000000000000000', 1, 1, 1))) end "
        "WowlheimPing('use hammer api=' .. tostring(WowlheimUseHammer ~= nil)) "
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

// Groupe g : toutes les signatures du groupe et celles des fonctions Lua (groupe 1) doivent correspondre.
static bool CheckGroup(int g, const char* what)
{
    for (size_t i = 0; i < sizeof g_sigs / sizeof g_sigs[0]; ++i) {
        if (g_sigs[i].group != g && !(g_sigs[i].group == 1 && g_sigs[i].va >= 0x6f0000 && g_sigs[i].va < 0x700000)) continue;
        if (!CheckSig(g_sigs[i])) { Log("%s DESACTIVE : octets inattendus en 0x%08lx (attendu %s)", what, g_sigs[i].va, g_sigs[i].hex); return false; }
    }
    return true;
}

// Disparition instantanee (groupe 6) et surbrillance de la piece visee (groupe 7, exige le survol : 0x464870).
static void InstallDespawnHighlightHooks()
{
    if (CheckGroup(6, "disparition instantanee")) {
        bool ok = InstallCallHook(0x614603, VA_MODEL_FADEOUT, (void*)&Stub_ModelFadeout) &&
                  InstallCallHook(0x5fbf30, VA_MODEL_FADEOUT, (void*)&Stub_ModelFadeout);
        if (ok) { g_despawnOk = true; Log("hooks poses en 0x00614603 et 0x005fbf30 (CALL 0x672df0 -> Stub_ModelFadeout) -> disparition instantanee"); }
        else Log("disparition instantanee : pose des hooks incomplete, desactivee");
    }
    if (g_pickOk && CheckGroup(7, "surbrillance (WowlheimHighlightObject)")) g_hlOk = true;
}

static void InstallExtraHooks()
{
    // survol : le lancer de rayon 0x481190 doit aussi etre valide (groupe 1, controle par InstallGhostHooks -> g_ghostOk)
    if (g_ghostOk && CheckGroup(3, "survol (WowlheimGetMouseoverObject)") &&
        InstallCallHook(VA_CALLSITE_PICKMASK, VA_PICKMASK, (void*)&Hook_PickMask)) {
        Log("hook pose en 0x%08lx (CALL 0x%08lx -> Hook_PickMask)", VA_CALLSITE_PICKMASK, VA_PICKMASK);
        g_pickOk = true;
    }
    if (CheckGroup(4, "apparition instantanee")) {
        bool ok = InstallCallHook(0x5f7c6b, 0x613af0, (void*)&Hook_ObjInitFade) &&
                  InstallCallHook(0x5fb956, 0x613af0, (void*)&Hook_ObjInitFade) &&
                  InstallCallHook(0x5f7e83, 0x614640, (void*)&Hook_ObjReshowFade) &&
                  InstallCallHook(0x5fbd67, 0x614640, (void*)&Hook_ObjReshowFade);
        if (ok) { g_fadeOk = true; Log("hooks poses en 0x005f7c6b, 0x005fb956 (0x613af0) et 0x005f7e83, 0x005fbd67 (0x614640) -> apparition instantanee"); }
        else Log("apparition instantanee : pose des hooks incomplete, desactivee");
    }
    if (CheckGroup(5, "prechargement des modeles")) g_preloadOk = true;
    if (CheckGroup(8, "WowlheimUseHammer")) g_useOk = true;
    InstallDespawnHighlightHooks();
}

static void InstallNativeHooks()
{
    // les fonctions Lua utilisees (groupe 1 : lua_tonumber, ...) et la voie native (groupe 2) doivent correspondre
    for (size_t i = 0; i < sizeof g_sigs / sizeof g_sigs[0]; ++i) {
        if (g_sigs[i].group != 1 && g_sigs[i].group != 2) continue;
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
            InstallExtraHooks();
        }
    } else if (reason == DLL_PROCESS_DETACH) {
        Log("DllMain DLL_PROCESS_DETACH (WowlheimPing appelee %ld fois ; fantome mis a jour sur %lu images)",
            (long)g_pingCount, g_ghost.frames);
    }
    return TRUE;
}
