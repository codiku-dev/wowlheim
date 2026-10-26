"""Verification statique (lecture seule) des adresses utilisees par wowlheim_client.cpp.

Lit la table g_sigs de wowlheim_client.cpp (une seule source de verite) et compare chaque motif d'octets aux
octets du fichier WoW.exe 1.12.1 (build 5875) donne en argument. Verifie aussi que chaque site de hook est un
CALL/JMP rel32 vers la cible attendue. N'ecrit rien, n'execute rien.

usage: python verify_addrs.py [chemin\\WoW.exe]   (defaut: C:\\Wowlheim\\client_test\\WoW.exe)
"""
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
EXE = sys.argv[1] if len(sys.argv) > 1 else r"C:\Wowlheim\client_test\WoW.exe"

# sites de hook -> cible attendue du CALL/JMP rel32 (doit refleter les InstallCallHook de la DLL)
HOOKS = {
    0x402aee: 0x7039e0,  # FrameScript_Initialize (demarrage)
    0x703b8e: 0x7039e0,  # FrameScript_Initialize (reload)
    0x48184a: 0x481190,  # lancer de rayon ecran->monde dans CGWorldFrame::OnLayerUpdate
    0x66fc45: 0x697ac0,  # CMap::Unload-like
    0x6920cc: 0x697ac0,  # CMap::Unload-like
    0x4821c5: 0x6e6980,  # orientation du fantome natif
    0x540740: 0x54ffd0,  # (controle) CALL WowClientDB<SpellRec>::Load apres MOV ECX,0xc0d780
}


def load_pe(path):
    d = open(path, "rb").read()
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, pe + 6)[0]
    optsz = struct.unpack_from("<H", d, pe + 20)[0]
    base = struct.unpack_from("<I", d, pe + 24 + 28)[0]
    secs = []
    for i in range(nsec):
        o = pe + 24 + optsz + i * 40
        vs, va, rs, ro = struct.unpack_from("<IIII", d, o + 8)
        secs.append((base + va, max(vs, rs), ro, rs))

    def v2o(v):
        for sva, size, ro, rs in secs:
            if sva <= v < sva + size and v - sva < rs:
                return ro + v - sva
        return None
    return d, v2o


def main():
    src = open(os.path.join(HERE, "wowlheim_client.cpp"), encoding="utf-8").read()
    sigs = re.findall(r'\{\s*0x([0-9a-fA-F]+),\s*"([0-9a-fA-F ]*)",\s*([012])\s*\}', src)
    d, v2o = load_pe(EXE)
    bad = 0
    print("fichier:", EXE)
    for va_s, hx, ghost in sigs:
        va = int(va_s, 16)
        want = bytes.fromhex(hx.replace(" ", ""))
        o = v2o(va)
        got = d[o:o + len(want)] if o is not None else b""
        ok = got == want
        bad += not ok
        print("%-4s 0x%06x %-6s attendu %s%s" % ("OK" if ok else "FAUX", va, {"0": "base", "1": "ghost", "2": "natif"}[ghost],
                                               want.hex(), "" if ok else "  lu " + got.hex()))
    for site, target in sorted(HOOKS.items()):
        o = v2o(site)
        op = d[o]
        rel = struct.unpack_from("<i", d, o + 1)[0]
        t = (site + 5 + rel) & 0xFFFFFFFF
        ok = op in (0xE8, 0xE9) and t == target
        bad += not ok
        print("%-4s hook 0x%06x : %s 0x%06x (attendu 0x%06x)" % ("OK" if ok else "FAUX", site,
                                                               "CALL" if op == 0xE8 else "JMP" if op == 0xE9 else "op %02x" % op, t, target))
    # structure de la table Spell : le chargeur 0x54ffd0 compare le nombre de colonnes / la taille de ligne
    o = v2o(0x54ffd0)
    body = d[o:o + 588]
    for what, pat in (("173 colonnes", bytes.fromhex("3dad000000")), ("692 octets/ligne", bytes.fromhex("3db4020000"))):
        ok = pat in body
        bad += not ok
        print("%-4s Spell.dbc %s dans 0x54ffd0" % ("OK" if ok else "FAUX", what))
    print("RESULTAT:", "toutes les verifications passent" if not bad else "%d echec(s)" % bad)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
