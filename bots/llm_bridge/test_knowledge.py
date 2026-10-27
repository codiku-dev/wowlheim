"""Tests de knowledge.py (selection de faits vanilla).  python -m unittest test_knowledge -v"""

import json
import time
import unittest

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import knowledge as kb  # noqa: E402

NE_DRUID = {"race": "Night Elf", "classe": "Druid", "niveau": "10", "zone": "Teldrassil"}
TAUREN_DRUID = {"race": "Tauren", "classe": "Druid", "niveau": "10", "zone": "Mulgore"}
ORC_WAR = {"race": "Orc", "classe": "Warrior", "niveau": "22", "zone": "The Barrens"}
HUM_PALA = {"race": "Human", "classe": "Paladin", "niveau": "38", "zone": "Duskwood"}
UD_MAGE = {"race": "Undead", "classe": "Mage", "niveau": "40", "zone": "Tirisfal Glades"}


def joined(facts):
    return " || ".join(facts)


class DataTests(unittest.TestCase):
    def test_json_valid_and_size(self):
        with open(kb.KB_PATH, encoding="utf-8") as f:
            data = json.load(f)
        facts = data["facts"]
        self.assertTrue(150 <= len(facts) <= 300, len(facts))
        ids = [x["id"] for x in facts]
        self.assertEqual(len(ids), len(set(ids)))
        for x in facts:
            self.assertTrue(x["kw"], x["id"])
            self.assertLess(len(x["text"]), 320, x["id"])
            self.assertIn(x.get("faction", "A"), ("A", "H"))
            if "levels" in x:
                lo, hi = x["levels"]
                self.assertTrue(1 <= lo <= hi <= 60, x["id"])

    def test_no_later_expansion_content(self):
        """Aucun fait ne doit presenter du contenu post-vanilla comme existant."""
        banned = ["Shattrath", "Outreterre", "Draeneï", "Exodar", "Lune-d'argent", "Norfendre", "Karazhan"]
        for f in kb.facts():
            if f["cat"] == "mecanique" and "Burning Crusade n'existe pas" in f["text"]:
                continue
            for word in banned:
                self.assertNotIn(word, f["text"], f["id"])


class SelectionTests(unittest.TestCase):
    def test_bear_form_alliance_druid(self):
        facts = kb.relevant_facts("où j'apprends la forme d'ours ?", NE_DRUID)
        self.assertTrue(facts)
        self.assertIn("Darnassus", facts[0])
        self.assertIn("Reflet-de-Lune", facts[0])
        self.assertIn("niveau 10", facts[0])
        self.assertNotIn("Pitons-du-Tonnerre", joined(facts))

    def test_bear_form_horde_druid(self):
        facts = kb.relevant_facts("c'est où qu'on a la bear form ?", TAUREN_DRUID)
        self.assertIn("Pitons-du-Tonnerre", facts[0])
        self.assertNotIn("Darnassus", joined(facts))

    def test_druid_trainer_not_elwynn(self):
        facts = kb.relevant_facts("il est où mon entraîneur ?", NE_DRUID)
        self.assertTrue(facts)
        self.assertIn("druide", facts[0])
        self.assertIn("Darnassus", facts[0])

    def test_deadmines(self):
        facts = kb.relevant_facts("on va aux mortemines ?", HUM_PALA)
        self.assertTrue(facts)
        self.assertIn("Mortemines", facts[0])
        self.assertIn("17-26", facts[0])
        self.assertIn("Marche de l'Ouest", facts[0])

    def test_dungeon_abbreviations(self):
        self.assertIn("Cœur du Magma", joined(kb.relevant_facts("mc ce soir ?", ORC_WAR)))
        self.assertIn("Monastère Écarlate", joined(kb.relevant_facts("qqn pour SM cathé ?", ORC_WAR)))
        self.assertIn("Zul'Gurub", joined(kb.relevant_facts("on tente ZG ?", ORC_WAR)))

    def test_small_talk_injects_nothing(self):
        for msg in ["salut ça va", "lol", "mdr t'es nul", "t'es druide ?", "tu veux grouper ?",
                    "j'ai tué un loup", "je suis à elwynn", "j'ai 25 ans", "gg", "bonne nuit à tous",
                    "je monte de niveau", "merci beaucoup", "tu fais quoi ce soir",
                    "t'as vu le prix du fer à l'hdv", "je vais réparer", "on se retrouve à l'auberge"]:
            self.assertEqual(kb.relevant_facts(msg, ORC_WAR), [], msg)
            self.assertEqual(kb.relevant_facts(msg, NE_DRUID), [], msg)

    def test_horde_capital_not_alliance(self):
        facts = kb.relevant_facts("c'est où la capitale ?", ORC_WAR)
        self.assertTrue(facts)
        self.assertIn("Orgrimmar", facts[0])
        self.assertNotIn("Hurlevent", joined(facts))

    def test_explicit_enemy_capital_still_answered(self):
        facts = kb.relevant_facts("c'est où hurlevent ?", ORC_WAR)
        self.assertTrue(facts and "Hurlevent" in facts[0])

    def test_mount_own_race_first(self):
        facts = kb.relevant_facts("où j'achète ma monture ?", ORC_WAR)
        self.assertIn("orcs", facts[0])
        self.assertIn("Orgrimmar", facts[0])
        self.assertNotIn("Darnassus", joined(facts))
        facts = kb.relevant_facts("où j'achète ma monture ?", UD_MAGE)
        self.assertIn("Brill", facts[0])

    def test_mount_other_race_mentioned(self):
        facts = kb.relevant_facts("les taurens achètent leur monture où ?", ORC_WAR)
        self.assertIn("Sabot-de-Sang", facts[0])

    def test_paladin_and_warlock_mount(self):
        self.assertIn("destrier", kb.relevant_facts("ma monture pala c'est quand ?", HUM_PALA)[0])
        warlock = {"race": "Gnome", "classe": "Warlock", "niveau": "39"}
        self.assertIn("Cabestan", kb.relevant_facts("comment j'ai le felsteed ?", warlock)[0])

    def test_hunter_pet(self):
        hunt = {"race": "orc", "classe": "hunter", "niveau": "10"}
        facts = kb.relevant_facts("comment j'apprivoise un familier ?", hunt)
        self.assertIn("niveau 10", facts[0])
        self.assertIn("Apprivoiser une bête", facts[0])

    def test_shaman_totem(self):
        cham = {"race": "troll", "classe": "shaman", "niveau": "9"}
        facts = kb.relevant_facts("où j'ai le totem de feu ?", cham)
        self.assertIn("niveau 10", facts[0])

    def test_class_question_about_other_class(self):
        """Un guerrier qui demande pour un ami druide recoit le fait druide (la classe citee prime)."""
        facts = kb.relevant_facts("mon pote druide demande où on a la forme aquatique", ORC_WAR)
        self.assertTrue(facts and "Forme aquatique" in facts[0])

    def test_generic_zone_question_uses_level_and_faction(self):
        facts = kb.relevant_facts("je vais où pour xp ?", ORC_WAR)
        self.assertTrue(facts)
        txt = joined(facts)
        self.assertNotIn("Bois de la Pénombre", txt)  # alliance
        self.assertNotIn("Silithus", txt)  # mauvais niveau
        facts = kb.relevant_facts("où xp au niveau 52 ?", ORC_WAR)
        self.assertTrue(any("5" in f.split(":")[1][:20] for f in facts), facts)

    def test_generic_dungeon_question_uses_level(self):
        facts = kb.relevant_facts("quel donjon à mon niveau ?", ORC_WAR)
        self.assertTrue(facts)
        for f in facts:
            self.assertNotIn("58-60", f)
        self.assertNotIn("Prison", joined(facts))

    def test_zone_name_needs_question(self):
        self.assertEqual(kb.relevant_facts("je quête dans les carmines", HUM_PALA), [])
        self.assertIn("15-25", kb.relevant_facts("c'est quel niveau les carmines ?", HUM_PALA)[0])

    def test_travel_by_faction(self):
        self.assertIn("Menethil", kb.relevant_facts("comment aller à kalimdor ?", HUM_PALA)[0])
        self.assertIn("Zeppelins", kb.relevant_facts("comment aller à kalimdor ?", UD_MAGE)[0])

    def test_mechanics(self):
        self.assertIn("1 po", kb.relevant_facts("comment on reset ses talents ?", ORC_WAR)[0])
        self.assertIn("aubergiste", kb.relevant_facts("ma pierre de foyer elle est liée où ?", ORC_WAR)[0])
        self.assertIn("Burning Crusade", kb.relevant_facts("tu montes un elfe de sang ?", ORC_WAR)[0])

    def test_limit_and_empty_inputs(self):
        self.assertLessEqual(len(kb.relevant_facts("quel donjon à mon niveau ?", ORC_WAR, limit=2)), 2)
        self.assertEqual(kb.relevant_facts("", ORC_WAR), [])
        self.assertEqual(kb.relevant_facts(None, None), [])
        self.assertTrue(kb.relevant_facts("on va aux mortemines ?", None))  # sans contexte : ne plante pas
        self.assertTrue(kb.relevant_facts("on va aux mortemines ?", {"race": "4", "classe": "11", "niveau": "x"}))

    def test_prompt_block(self):
        self.assertEqual(kb.prompt_block([]), "")
        block = kb.prompt_block(kb.relevant_facts("on va aux mortemines ?", HUM_PALA))
        self.assertTrue(block.startswith(" " + kb.PROMPT_PREFIX))

    def test_speed(self):
        msgs = ["salut ça va", "où j'apprends la forme d'ours ?", "quel donjon à mon niveau ?",
                "on va aux mortemines ce soir avec la guilde ? il nous faut un tank et un heal"] * 50
        kb.relevant_facts("warmup", ORC_WAR)
        t0 = time.perf_counter()
        for m in msgs:
            kb.relevant_facts(m, ORC_WAR)
        per_call_ms = (time.perf_counter() - t0) * 1000 / len(msgs)
        self.assertLess(per_call_ms, 5.0)


if __name__ == "__main__":
    unittest.main()
