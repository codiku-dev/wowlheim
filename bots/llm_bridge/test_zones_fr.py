"""Wowlheim : tests de zones_fr (python -I bots/llm_bridge/test_zones_fr.py)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from zones_fr import ZONES_FR, fr  # noqa: E402


class ZonesFrTest(unittest.TestCase):
    def test_noms_connus(self):
        self.assertEqual(fr("Northshire Valley"), "Vallée de Northshire")
        self.assertEqual(fr("Goldshire"), "Comté-de-l'Or")
        self.assertEqual(fr("Elwynn Forest"), "Forêt d'Elwynn")
        self.assertEqual(fr("Westfall"), "Marche de l'Ouest")
        self.assertEqual(fr("Darkshore"), "Sombrivage")
        self.assertEqual(fr("Stormwind City"), "Hurlevent")
        self.assertEqual(fr("Ironforge"), "Forgefer")
        self.assertEqual(fr("Undercity"), "Fossoyeuse")
        self.assertEqual(fr("Thunder Bluff"), "Les Pitons-du-Tonnerre")
        self.assertEqual(fr("The Barrens"), "Les Tarides")

    def test_casse_et_espaces(self):
        self.assertEqual(fr("  elwynn forest "), "Forêt d'Elwynn")

    def test_inconnu_et_vide(self):
        self.assertEqual(fr("Nulle Part"), "Nulle Part")
        self.assertEqual(fr(""), "")
        self.assertIsNone(fr(None))

    def test_table_propre(self):
        for en, fr_name in ZONES_FR.items():
            self.assertTrue(en and en == en.strip(), en)
            self.assertTrue(fr_name and fr_name == fr_name.strip(), en)
        self.assertGreaterEqual(len(ZONES_FR), 80)
        lowered = [k.lower() for k in ZONES_FR]
        self.assertEqual(len(lowered), len(set(lowered)))


if __name__ == "__main__":
    unittest.main()
