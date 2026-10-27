"""Canal client-serveur [WL] : les commandes `.build api ...` répondent par des lignes structurées préfixées [WL] (celles que lira
l'addon). Vérifie le format avec le même analyseur que l'addon (WowlheimCore.lua, via lupa).
python api_test.py <compte> <mdp>   (serveur lancé ; utiliser le Python du venv tools/client pour lupa)"""
import os, sys, time
from wlclient import Session

try:
    from lupa import LuaRuntime
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute("table.getn = function(t) return #t end")
    lua.execute(open(os.path.join(os.path.dirname(__file__), "client", "addon", "Wowlheim", "WowlheimCore.lua"), encoding="utf-8").read())
    core = lua.eval("WowlheimCore")
except ImportError:
    core = None

s = Session(sys.argv[1], sys.argv[2])
g, n = s.chars()[0]
s.login(g)
ok = True


def lines(cmd, t=1.2):
    return [l for l in s.say(cmd, t) if l.startswith("[WL]")]


def check(name, cond, detail=""):
    global ok
    ok &= bool(cond)
    print(("[OK]   " if cond else "[ÉCHEC]"), name, detail)


s.say(".revive", 0.5)
L = lines(".build api list")
check("api list : 7 lignes P puis D|list|1", len([l for l in L if l.startswith("[WL]P|")]) >= 7 and "[WL]D|list|1" in L, str(L[-2:]))
if core:
    parsed = [core.ParseLine(l) for l in L]
    # des lignes poussées par le serveur hors commande (EN| endurance, SK| compétences, K*| connaissances...) peuvent s'intercaler :
    # elles sont légitimes ; chaque ligne doit être reconnue par l'addon (ParseLine renvoie le type « ? » pour un type inconnu)
    bad = [l for l, p in zip(L, parsed) if p is None or p["type"] == "?"]
    check("toutes les lignes sont analysables par l'addon", not bad, str(bad[:3]) + " autres types : " +
          str(sorted({p["type"] for p in parsed if p is not None and p["type"] not in ("P", "D")})))
    plancher = [p for p in parsed if p["type"] == "P" and p["name"].startswith("Plancher")][0]   # « Plancher 2x2 » (nom de Valheim)
    check("Plancher : coût 2 Bois (9200001:2)", plancher["cost"][1]["item"] == 9200001 and plancher["cost"][1]["count"] == 2)
L = lines(".build api inv")
check("api inv : ligne I puis D", any(l.startswith("[WL]I|") for l in L) and L[-1] == "[WL]D|inv|1", str(L))
L = lines(".build api recipes")
check("api recipes : lignes C", len([l for l in L if l.startswith("[WL]C|")]) >= 10, str(len(L)))
L = lines(".build api place 99 3 0 0 0")
check("api place d'une pièce inconnue : message M puis D|place|0", any(l.startswith("[WL]M|") for l in L) and L[-1] == "[WL]D|place|0", str(L))
L = lines(".build api bogus")
check("commande API inconnue : E puis D|…|0", L and L[0].startswith("[WL]E|") and L[-1].endswith("|0"), str(L))
# les lignes ne fuient pas hors du mode API : une commande normale n'émet aucune ligne [WL]
check("commande normale : aucune ligne [WL]", not lines(".build count"))
s.close()
print("RÉSULTAT :", "OK" if ok else "ÉCHEC")
