#!/usr/bin/env python3
"""Ajoute une courte histoire (champ « histoire ») aux personnalites generees, HORS jeu.

Lance a la main, une fois, quand le serveur n'a pas besoin du GPU. Le resultat est ecrit
dans <state>/personas/<Nom>.json ; relire les fiches avant de les copier dans bots/personas/.

  python -I bots/llm_bridge/enrich_personas.py [--state-dir C:/Wowlheim/bots/state] [--limit 10]
"""
import argparse
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bridge  # noqa: E402

PROMPT = ("Ecris en francais, en deux phrases maximum (moins de 250 caracteres), l'histoire d'un personnage "
          "de World of Warcraft vanilla nomme {nom}, {race} {classe}. Ton : {traits}. Reste dans l'univers "
          "d'Azeroth (aucune construction de maison, aucun autre jeu). Pas de guillemets, pas de markdown.")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-dir", default=r"C:\Wowlheim\bots\state")
    ap.add_argument("--lm-url", default=bridge.bot_chat.DEFAULT_URL)
    ap.add_argument("--model", default=bridge.bot_chat.DEFAULT_MODEL)
    ap.add_argument("--limit", type=int, default=10)
    a = ap.parse_args(argv)
    b = bridge.Bridge(a.lm_url, a.model, a.state_dir, timeout=30)
    done = 0
    for path in sorted(glob.glob(os.path.join(a.state_dir, "personas", "*.json"))):
        if done >= a.limit:
            break
        with open(path, encoding="utf-8") as f:
            p = json.load(f)
        if p.get("histoire") or not p.get("race"):
            continue
        msg = PROMPT.format(nom=p["nom"], race=p.get("race", "?"), classe=p.get("classe", "?"),
                            traits=", ".join(p.get("traits", [])))
        try:
            text = b._call_lm([{"role": "user", "content": msg}])
        except Exception as e:
            print("%s : LLM indisponible (%s)" % (p["nom"], type(e).__name__))
            return 1
        text = bridge.bot_chat.filter_reply(text, 250)
        if not text or bridge._FORBIDDEN_OUT.search(text):
            print("%s : sortie rejetee" % p["nom"])
            continue
        p["histoire"] = text
        p["source"] = "generee+llm (a relire)"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(p, f, ensure_ascii=False, indent=1)
        print("%s : %s" % (p["nom"], text))
        done += 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
