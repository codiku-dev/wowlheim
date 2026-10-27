#!/usr/bin/env python3
"""Juge automatique des transcriptions du banc (eval_chat.py) avec TypeSafe Jev (API en ligne).

N'envoie QUE des dialogues de test synthetiques (jamais le chat du jeu). Cle lue dans
C:\\Wowlheim\\bots\\state\\typesafe_api_key.txt (hors depot), jamais affichee.
Par scenario : P(un humain aurait ecrit ces repliques), comprehension, naturel, tenue du personnage.

  python -I bots/tests/jev_judge.py C:/Wowlheim/bots/state/eval/<modele>_bench.json [...]
"""
import json
import os
import statistics
import sys
import urllib.error
import urllib.request

URL = "https://api.typesafe.ai/v1/systemone"
KEY_FILE = r"C:\Wowlheim\bots\state\typesafe_api_key.txt"
LEVELS = ["0 nul", "1 faible", "2 moyen", "3 bon", "4 excellent"]
QUESTIONS = {
    "humain": {"type": "noul", "instructions":
               "Ces repliques du personnage BOT pourraient-elles avoir ete ecrites par un vrai joueur humain "
               "francais dans le chat de World of Warcraft, sans qu'on soupconne une IA ?"},
    "comprehension": {"type": "score", "instructions":
                      "Le BOT comprend-il ce que le joueur lui dit et y repond-il vraiment (pas d'esquive, pas de "
                      "reponse a cote) ?", "criteria": LEVELS},
    "naturel": {"type": "score", "instructions":
                "Les repliques du BOT ont-elles le ton, la longueur et la spontaneite d'un chat de MMO entre "
                "joueurs ?", "criteria": LEVELS},
    "personnage": {"type": "score", "instructions":
                   "Le BOT respecte-t-il sa fiche (style d'ecriture, caractere, race, classe, niveau) et reste-t-il "
                   "coherent d'une replique a l'autre ?", "criteria": LEVELS},
}


def ask(state, key):
    body = json.dumps({"model": "jev-latest", "state": state, "questions": QUESTIONS}).encode("utf-8")
    req = urllib.request.Request(URL, data=body, method="POST", headers={
        "Authorization": "Bearer " + key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def state_of(persona, sc):
    lines = ["FICHE DU BOT : " + json.dumps({k: persona.get(k) for k in
                                              ("nom", "race", "classe", "style", "traits", "vie")}, ensure_ascii=False),
             "CONTEXTE : %s" % json.dumps(sc.get("context", {}), ensure_ascii=False), "DIALOGUE :"]
    for t in sc["turns"]:
        lines.append("JOUEUR : %s" % (t.get("player") or t.get("msg") or ""))
        lines.append("BOT : %s" % (t.get("reply") or "(pas de reponse)"))
    return "\n".join(lines)


def num(ans):
    if ans.get("type") == "noul":
        return ans.get("noul")
    return ans.get("score")


def main(paths):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    with open(KEY_FILE, encoding="utf-8") as f:
        key = f.read().strip()
    for path in paths:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        res = {q: [] for q in QUESTIONS}
        for sc in d["scenarios"]:
            try:
                a = ask(state_of(d["personas"].get(sc["bot"], {}), sc), key)["answers"]
            except urllib.error.HTTPError as e:
                print("  %s : HTTP %s %s" % (sc["id"], e.code, e.read()[:200].decode("utf-8", "replace")))
                continue
            vals = {q: num(a[q]) for q in QUESTIONS if q in a}
            for q, v in vals.items():
                if v is not None:
                    res[q].append(v)
            print("  %s %-40s %s" % (sc["id"], sc["title"][:40], " ".join("%s=%.2f" % (q, v) for q, v in vals.items()
                                                                           if v is not None)))
        moy = {q: round(statistics.mean(v), 2) for q, v in res.items() if v}
        print("%s -> %s" % (d["model"], moy), flush=True)
        out = os.path.splitext(path)[0] + "_jev.json"
        with open(out, "w", encoding="utf-8") as f:
            json.dump({"model": d["model"], "moyennes": moy, "detail": res}, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main(sys.argv[1:])
