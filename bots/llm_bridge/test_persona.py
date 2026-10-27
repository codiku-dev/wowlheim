#!/usr/bin/env python3
"""Tests des personnalites des bots (stdlib seulement, sans LM Studio).

  python -I bots/llm_bridge/test_persona.py
"""
import json
import os
import re
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import persona as P  # noqa: E402

# 45 bots reels du serveur de test (nom, race, classe, niveau ; ids 1.12), releve du 2026-10-26.
BOTS = [
    ("Alygyael", 4, 1, 1), ("Alynul", 4, 5, 26), ("Arabelah", 1, 2, 43), ("Aramianon", 5, 4, 1),
    ("Arinaris", 5, 9, 1), ("Bapoh", 6, 7, 1), ("Barany", 5, 9, 39), ("Berreno", 1, 9, 38),
    ("Bimlink", 7, 8, 15), ("Brerraliugs", 3, 3, 1), ("Caryrin", 4, 11, 15), ("Cateranie", 5, 4, 1),
    ("Charo", 1, 4, 16), ("Chelenelle", 1, 2, 25), ("Cinic", 7, 8, 29), ("Delanaya", 4, 4, 1),
    ("Drolghe", 8, 1, 27), ("Drorguglast", 2, 7, 5), ("Duhdun", 8, 8, 10), ("Elalas", 4, 11, 22),
    ("Emandy", 1, 2, 1), ("Esodren", 4, 4, 1), ("Estemily", 5, 4, 1), ("Faralar", 4, 3, 1),
    ("Fenci", 7, 8, 1), ("Galalleas", 4, 4, 30), ("Gared", 5, 4, 11), ("Garthaan", 4, 4, 1),
    ("Gawi", 2, 7, 1), ("Geline", 1, 8, 16), ("Gengeanvi", 3, 1, 11), ("Gnale", 7, 4, 44),
    ("Gommi", 3, 3, 1), ("Grungig", 3, 4, 34), ("Gustan", 5, 5, 1), ("Gysa", 3, 3, 54),
    ("Hadoti", 6, 7, 41), ("Harald", 5, 4, 1), ("Icalan", 5, 1, 1), ("Isona", 5, 1, 13),
    ("Ithee", 7, 9, 54), ("Karabetta", 1, 9, 1), ("Katerna", 5, 9, 33), ("Kedries", 4, 11, 16),
    ("Kilbonk", 7, 8, 1),
]
# Combinaisons race/classe autorisees en 1.12.
VALID = {
    "human": ["warrior", "paladin", "rogue", "priest", "mage", "warlock"],
    "dwarf": ["warrior", "paladin", "hunter", "rogue", "priest"],
    "night elf": ["warrior", "hunter", "rogue", "priest", "druid"],
    "gnome": ["warrior", "rogue", "mage", "warlock"],
    "orc": ["warrior", "hunter", "rogue", "shaman", "warlock"],
    "undead": ["warrior", "rogue", "priest", "mage", "warlock"],
    "tauren": ["warrior", "hunter", "shaman", "druid"],
    "troll": ["warrior", "hunter", "rogue", "priest", "shaman", "mage"],
}
FORBIDDEN = re.compile(
    r"valheim|wowlheim|construi|construction|b[aâ]tir|marteau|maison|abattre|\barbres?\b|\bmurs?\b|"
    r"\bia\b|intelligence artificielle|\bbots?\b|\bllm\b|chatgpt|mod[eè]le de langage|\.build", re.I)
SIXTY_ONLY = re.compile(r"C[œo]eur du Magma|Aile noire|Zul'Gurub|monture épique|rang d'honneur|Bénédiction|"
                        r"Rhok'delar|destrier de l'effroi|destrier épique", re.I)


def texts(p):
    out = [p["style"], p["vie"], p["heures_de_jeu"]] + list(p["traits"]) + list(p["objectifs"]) + list(p["tics"]) + [p["expressions_rp"]]
    return [t for t in out if isinstance(t, str)]


def all_combos(levels=(1, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 58, 60)):
    i = 0
    for race, classes in VALID.items():
        for cls in classes:
            for lvl in levels:
                i += 1
                yield P.generate("Test%s" % "".join(chr(97 + int(d)) for d in str(i)), race, cls, lvl), race, cls, lvl


class PersonaTest(unittest.TestCase):
    def test_catalogue_size(self):
        self.assertGreaterEqual(len(P.FORMES) + len(P.REGISTRES), 25)
        self.assertGreaterEqual(len(P.REGISTRES), 20)
        self.assertGreaterEqual(len(P.TRAITS), 30)
        self.assertGreaterEqual(len(P.LIVES), 20)
        self.assertEqual(len(P.TRAITS), len(set(P.TRAITS)))

    def test_deterministic_and_api(self):
        for name, race, cls, lvl in BOTS[:10]:
            a = P.generate(name, race, cls, lvl)
            self.assertEqual(a, P.generate(name, race, cls, lvl))
            self.assertEqual(a, P.generate(name.upper(), race, cls, lvl) | {"nom": name})
            for k in ("nom", "race", "classe", "style", "traits", "vie", "objectifs", "aime_grouper"):
                self.assertIn(k, a)
            self.assertIsInstance(a["style"], str)
            self.assertEqual(a["style"], P.generate(name, level=lvl)["style"])  # style independant de la race
            self.assertIsInstance(a["traits"], list)
            self.assertIsInstance(a["objectifs"], list)
            self.assertTrue(a["objectifs"])
        self.assertEqual(P.generate("Thorgrim", "Dwarf", "Warrior", 12)["race"], "nain")
        self.assertEqual(P.generate("Thorgrim", "Night Elf", "Druid", 12)["race"], "elfe de la nuit")
        self.assertEqual(P.generate("Thorgrim", "4", "11", 12)["classe"], "druide")
        self.assertEqual(P.RACE_FR["undead"], "mort-vivant")
        self.assertEqual(P.CLASS_FR["warlock"], "demoniste")
        self.assertEqual(P.safe_name("Élyria"), "Élyria")
        self.assertIsNone(P.safe_name("../x"))
        self.assertIsNotNone(P.generate("Inconnu"))  # sans race/classe/niveau

    def test_store_saves_reloads_and_upgrades(self):
        tmp = tempfile.mkdtemp()
        try:
            s = P.PersonaStore(tmp, repo_dir=os.path.join(tmp, "repo"))
            p1 = s.get("Bimlink", "Gnome", "Mage", 15)
            p2 = P.PersonaStore(tmp, repo_dir=os.path.join(tmp, "repo")).get("Bimlink")
            self.assertEqual(p1, p2)
            # Ancienne fiche (version 1) avec histoire relue -> regeneree, histoire gardee.
            old = {"nom": "Gawi", "style": "utilise des smileys texte comme :) ou ^^ de temps en temps",
                   "traits": ["chill"], "vie": "x", "objectifs": ["y"], "source": "generee+llm (a relire)",
                   "histoire": "Gawi a grandi a Orgrimmar."}
            with open(os.path.join(tmp, "personas", "Gawi.json"), "w", encoding="utf-8") as f:
                json.dump(old, f)
            p = P.PersonaStore(tmp, repo_dir=os.path.join(tmp, "repo")).get("Gawi", "Orc", "Shaman", 1)
            self.assertEqual(p["version"], P.PERSONA_VERSION)
            self.assertEqual(p["histoire"], old["histoire"])
            self.assertNotIn("^^ de temps", p["style"])
            # Le bot a pris 40 niveaux : objectifs recalcules, style inchange.
            p40 = P.PersonaStore(tmp, repo_dir=os.path.join(tmp, "repo")).get("Bimlink", "Gnome", "Mage", 55)
            self.assertEqual(p40["style"], p1["style"])
            for g in p40["objectifs"]:
                lo, hi = P.goal_range(g)
                self.assertTrue(lo <= 55 <= hi, g)
            # Une fiche ecrite a la main n'est jamais modifiee.
            os.makedirs(os.path.join(tmp, "repo"))
            with open(os.path.join(tmp, "repo", "Hadoti.json"), "w", encoding="utf-8") as f:
                json.dump({"nom": "Hadoti", "style": "main", "objectifs": ["atteindre le niveau 10"]}, f)
            self.assertEqual(P.PersonaStore(tmp, repo_dir=os.path.join(tmp, "repo")).get(
                "Hadoti", "Tauren", "Shaman", 41)["style"], "main")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_goals_match_level(self):
        for p, race, cls, lvl in all_combos():
            for g in p["objectifs"]:
                rng = P.goal_range(g)
                self.assertIsNotNone(rng, g)
                self.assertTrue(rng[0] <= lvl <= rng[1], (lvl, g))
                if lvl < 60:
                    self.assertIsNone(SIXTY_ONLY.search(g), (lvl, g))
                if lvl < 40:
                    self.assertNotIn("niveau 60", g)
            if lvl <= 10:
                self.assertFalse(any(re.search(r"Rochenoire|Stratholme|Scholomance|Maraudon|Zul'Farrak", g)
                                     for g in p["objectifs"]), p["objectifs"])

    def test_no_enemy_faction_places(self):
        for p, race, cls, lvl in all_combos():
            fac = P.FACTION[race]
            enemy = P.FACTION_PLACES["H" if fac == "A" else "A"]
            blob = " | ".join(texts(p))
            for place in enemy:
                self.assertNotIn(place, blob, (race, cls, lvl, place))

    def test_class_goals_only_for_own_class(self):
        marks = {"posture": "warrior", "totem": "shaman", "familier rare": "hunter", "forme d": "druid",
                 "poisons": "rogue", "succube": "warlock", "portails": "mage", "Rédemption": "paladin"}
        for p, race, cls, lvl in all_combos():
            for g in p["objectifs"]:
                for mark, owner in marks.items():
                    if mark in g:
                        self.assertEqual(owner, cls, g)

    def test_style_coherence(self):
        forme = {f["id"]: f for f in P.FORMES}
        reg = {g["id"]: g for g in P.REGISTRES}
        for i in range(3000):
            p = P.generate("Coh%d" % i, "human", "mage", 1 + i % 60)
            f, g = forme[p["forme"]], reg[p["registre"]]
            self.assertTrue(f["age"][0] <= p["age"] <= f["age"][1])
            self.assertTrue(g["age"][0] <= p["age"] <= g["age"][1])
            if p["niveau_genere"] > 25:
                self.assertNotEqual(p["registre"], "nouveau_naif")
            if p["ton_rp"] == "rp léger":
                self.assertTrue(g["rp"] and not f["abr"] and f["niveau"] != "relache", p["style_id"])
            self.assertFalse(f["niveau"] == "soigne" and g["reg"] == "familier", p["style_id"])
            self.assertFalse(f["niveau"] == "relache" and g["reg"] == "soutenu", p["style_id"])
            self.assertFalse(g.get("excl") and f["id"] == "exclamation", p["style_id"])
            for a in p["traits"]:
                for b in p["traits"]:
                    self.assertNotIn({a, b}, P.INCOMPATIBLE)
            # Smileys : regle explicite dans le style ; « ^^ » seulement si c'est LE smiley choisi.
            if p["smileys"] == "jamais":
                self.assertIn("jamais de smiley", p["style"])
                self.assertEqual(p["smiley"], "")
            else:
                self.assertIn(p["smiley"], p["style"])
                if p["smiley"] != "^^":
                    self.assertNotIn("^^", p["style"])

    def test_smileys_are_rare_overall(self):
        ps = [P.generate("Sm%d" % i, "orc", "warrior", 20) for i in range(3000)]
        rate = sum(p["smileys"] != "jamais" for p in ps) / len(ps)
        self.assertLess(rate, 0.15)
        self.assertLess(sum(p["smiley"] == "^^" for p in ps) / len(ps), 0.02)
        self.assertLess(sum(p["ton_rp"] == "rp léger" for p in ps) / len(ps), 0.25)

    def test_diversity_on_real_bots(self):
        ps = [P.generate(n, r, c, lvl) for n, r, c, lvl in BOTS]
        self.assertEqual(len(ps), 45)
        self.assertGreaterEqual(len({p["style_id"] for p in ps}), 30)
        self.assertGreaterEqual(len({p["registre"] for p in ps}), 15)
        self.assertGreaterEqual(len({p["forme"] for p in ps}), 10)
        self.assertGreaterEqual(len({p["vie"].split(";")[0].split(" ans, ")[1] for p in ps}), 15)
        self.assertLessEqual(sum(p["smileys"] != "jamais" for p in ps), 45 * 0.20)
        self.assertGreaterEqual(sum(p["ton_rp"] == "hors rp" for p in ps), 30)
        self.assertEqual(len({p["style"] for p in ps}), 45)

    def test_no_forbidden_words(self):
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), "tools", "llm"))
        import bridge  # noqa: E402
        tables = [t for _a, _b, _c, t in P.LEVEL_GOALS] + [t for _a, _b, t in P.MISC_GOALS]
        for d in (P.CLASS_GOALS, P.RACE_GOALS):
            tables += [t for v in d.values() for _a, _b, t in v]
        tables += [f["txt"] for f in P.FORMES] + [g["txt"] for g in P.REGISTRES]
        tables += [t for g in P.REGISTRES for t in g["tics"]] + [t for t, _ in P.TICS_PERSO]
        tables += [x for life in P.LIVES for x in (life[0], life[1], life[3])] + P.TRAITS
        tables += list(P.RP_FLAVOR.values())
        for t in tables:
            self.assertIsNone(FORBIDDEN.search(t), t)
            self.assertIsNone(bridge._FORBIDDEN_OUT.search(t), t)
        for p, *_ in all_combos():
            for t in texts(p):
                self.assertIsNone(FORBIDDEN.search(t), t)

    def test_prompt_carries_style(self):
        import bridge  # noqa: E402
        b = bridge.Bridge("http://127.0.0.1:1", "m", tempfile.mkdtemp(), generate=lambda m: "ok")
        p = P.generate("Bimlink", "Gnome", "Mage", 15)
        req = bridge.Bridge.normalize({"bot": "Bimlink", "bot_race": "Gnome", "bot_class": "Mage",
                                       "bot_level": "15", "bot_gender": "Male", "zone": "Dun Morogh",
                                       "other": "Robin", "channel": "in private message", "message": "salut"})
        sysmsg = b.build_messages(p, req, [])[0]["content"]
        self.assertIn(p["style"], sysmsg)
        self.assertIn(p["vie"], sysmsg)
        self.assertLess(len(sysmsg), 3500)   # regles de ton et de vie reelle ajoutees apres les retours de Robin


if __name__ == "__main__":
    unittest.main(verbosity=1)
