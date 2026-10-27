#!/usr/bin/env python3
"""Tests du pont LLM (sans LM Studio : le LLM est remplace par une fonction).

  python -I bots/llm_bridge/test_bridge.py
"""
import json
import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bridge as B  # noqa: E402
import persona as P  # noqa: E402


def req(**kw):
    r = {"bot": "Thorgrim", "bot_race": "Dwarf", "bot_class": "Warrior", "bot_level": "12",
         "bot_gender": "Male", "zone": "Dun Morogh", "subzone": "Kharanos", "other": "Robin",
         "other_race": "Human", "other_class": "Mage", "other_level": "11",
         "channel": "in private message", "message": "salut tu fais quoi ?"}
    r.update(kw)
    return r


class FakeLLM:
    def __init__(self, text="je farme des sangliers, et toi ?", delay=0.0):
        self.text, self.delay, self.calls, self.active, self.max_active = text, delay, [], 0, 0
        self.lock = threading.Lock()

    def __call__(self, messages):
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        self.calls.append(messages)
        time.sleep(self.delay)
        with self.lock:
            self.active -= 1
        return self.text


class BridgeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def make(self, llm=None, **kw):
        g = B.Guards(rand=lambda: 0.0, **{k: kw.pop(k) for k in list(kw) if k in ("bot_cooldown", "per_minute")})
        return B.Bridge("http://127.0.0.1:1", "m", self.tmp, generate=llm or FakeLLM(), guards=g, **kw)

    def test_reply_and_persona_in_prompt(self):
        llm = FakeLLM()
        b = self.make(llm)
        self.assertEqual(b.handle(req()), "je farme des sangliers, et toi ?")
        sysmsg = llm.calls[0][0]["content"]
        self.assertIn("nain guerrier", sysmsg)
        self.assertIn("Kharanos, Dun Morogh", sysmsg)
        self.assertIn(P.generate("Thorgrim")["style"], sysmsg)
        self.assertNotIn("valheim", sysmsg.lower())
        self.assertIn("message prive", llm.calls[0][-1]["content"])

    def test_persona_is_stable_and_saved(self):
        b = self.make()
        p1 = b.personas.get("Thorgrim", "Dwarf", "Warrior", 12)
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "personas", "Thorgrim.json")))
        p2 = P.PersonaStore(self.tmp).get("Thorgrim")
        self.assertEqual(p1, p2)
        self.assertNotEqual(P.generate("Thorgrim")["style"] + P.generate("Thorgrim")["vie"],
                            P.generate("Elyria")["style"] + P.generate("Elyria")["vie"])
        self.assertIsNone(P.safe_name("../x"))

    def test_memory_both_sides_persisted(self):
        llm = FakeLLM()
        b = self.make(llm, bot_cooldown=0)
        b.handle(req(message="salut"))
        b.handle(req(message="tu veux grouper ?"))
        msgs = llm.calls[1]
        self.assertEqual([m["role"] for m in msgs], ["system", "user", "assistant", "user"])
        self.assertIn("salut", msgs[1]["content"])
        b2 = self.make(llm, bot_cooldown=0)
        self.assertEqual(len(b2.memory.history("Thorgrim", "Robin", time.time())), 4)

    def test_only_one_bot_answers_a_say(self):
        b = self.make()
        r1 = b.handle(req(channel="directly", message="quelqu'un pour les Mortemines ?"))
        r2 = b.handle(req(bot="Elyria", channel="directly", message="quelqu'un pour les Mortemines ?"))
        self.assertTrue(r1)
        self.assertEqual(r2, "")

    def test_message_addressed_to_other_bot(self):
        b = self.make()
        b.handle(req(bot="Elyria", channel="directly", message="bonjour"))
        self.assertEqual(b.handle(req(channel="directly", message="elyria tu viens ?")), "")

    def test_cooldown_and_commands(self):
        b = self.make()
        self.assertTrue(b.handle(req(message="a")))
        self.assertTrue(b.handle(req(message="b")))                   # tete-a-tete : chaque message a sa reponse
        self.assertTrue(b.handle(req(bot="Brumegarde", channel="in the general channel", message="c")))
        self.assertEqual(b.handle(req(bot="Brumegarde", channel="in the general channel", message="d")), "")   # canal public : recharge
        self.assertEqual(b.handle(req(bot="Elyria", message=".build list")), "")

    def test_output_filters(self):
        for bad in ("Je suis une IA, desole", "va sur www.site.com", "tu connais Valheim ?",
                    "en tant qu'assistant je", "<think>bla bla", "je joue juste a wow vanilla"):
            b = self.make(FakeLLM(bad))
            self.assertEqual(b.handle(req()), "", bad)
        b = self.make(FakeLLM('Thorgrim: "ok" on y va\\ ! **go**'))
        self.assertEqual(b.handle(req()), "ok on y va ! go")
        b = self.make(FakeLLM("x" * 400))
        self.assertLessEqual(len(b.handle(req())), B.MAX_REPLY_CHARS)

    def test_item_link_cleaned(self):
        llm = FakeLLM()
        b = self.make(llm)
        b.handle(req(message="tu veux |cff1eff00|Hitem:2140:0:0:0|h[Couteau de carnage]|h|r ?"))
        self.assertIn("[Couteau de carnage] ?", llm.calls[0][-1]["content"])
        self.assertNotIn("|H", llm.calls[0][-1]["content"])

    def test_llm_down_is_silence(self):
        def boom(_):
            raise OSError("refused")
        self.assertEqual(self.make(boom).handle(req()), "")
        self.assertEqual(self.make().handle({"garbage": 1}), "")
        self.assertEqual(self.make().handle("pas un dict"), "")

    def test_single_llm_call_at_a_time_and_bounded_queue(self):
        llm = FakeLLM(delay=0.3)
        b = self.make(llm, bot_cooldown=0, max_waiting=2)
        out = []
        ths = [threading.Thread(target=lambda i=i: out.append(b.handle(req(bot="Bot" + "abcdef"[i]))))
               for i in range(6)]
        for t in ths:
            t.start()
        for t in ths:
            t.join()
        self.assertEqual(llm.max_active, 1)
        self.assertLessEqual(sum(1 for o in out if o), 2)
        self.assertGreaterEqual(b.stats["file_pleine"], 1)

    def test_game_state_in_prompt(self):
        import gamestate
        def fake(sql):
            if "character_queststatus" in sql:
                return [["62", "7", "The Fargodeep Mine", "3"] + ["0", "0", "", "0", "0", ""] * 4,
                        ["60", "5", "Kobold Candles", "3", "3", "8", "Kobold Tunneler"] + ["0", "0", ""] + ["0", "0", "", "0", "0", ""] * 3]
            return [["7", "254300", "1"]]
        st = gamestate.GameState(query=fake)
        llm = FakeLLM()
        b = B.Bridge("http://127.0.0.1:1", "m", self.tmp, generate=llm, guards=B.Guards(rand=lambda: 0.0), state=st)
        b.handle(req())
        sysmsg = llm.calls[0][0]["content"]
        self.assertIn("25 pieces d'or", sysmsg)
        self.assertIn("[[q:62]] « The Fargodeep Mine »", sysmsg)
        self.assertIn("3/8 Kobold Tunneler", sysmsg)
        self.assertIn("en groupe avec lui", sysmsg)
        broken = gamestate.GameState(query=lambda sql: 1 / 0)
        self.assertEqual(broken.get("Thorgrim", "Robin"), {})

    def test_spontaneous_line_and_cooldown(self):
        llm = FakeLLM("bon on enchaine sur les murlocs ?")
        b = self.make(llm)
        r = req(channel="in party chat", message="")
        r["event"] = "silence"
        self.assertEqual(B.handle_spontaneous(b, r, now=1000.0), ("bon on enchaine sur les murlocs ?", None))
        self.assertIn("Dis spontanement", llm.calls[0][-1]["content"])
        self.assertEqual(B.handle_spontaneous(b, r, now=1100.0)[1], "recharge_initiative")
        r2 = dict(r, bot="Elyria")
        self.assertEqual(B.handle_spontaneous(b, r2, now=1010.0)[1], "recharge_initiative")   # plafond global
        self.assertEqual(B.handle_spontaneous(b, r2, now=1040.0)[1], None)
        self.assertEqual(B.handle_spontaneous(b, dict(r, event="pirater"), now=5000.0)[1], "requete_invalide")

    def test_quest_link_only_for_own_quest(self):
        import gamestate
        q = {"id": 783, "niveau": 1, "titre": "A Threat Within", "finie": False, "progres": ["4/10 Kobold Vermin"]}
        st = gamestate.GameState(query=lambda sql: [])
        st.get = lambda bot, other: {"or": 1, "quetes": [q], "groupe_avec_lui": False}
        llm = FakeLLM("je fais [[q:783]], j'en suis a 4 sur 10 [[q:9999]]")
        b = B.Bridge("http://127.0.0.1:1", "m", self.tmp, generate=llm, guards=B.Guards(rand=lambda: 0.0), state=st)
        out = b.handle(req(message="tu fais quelle quete ?"))
        self.assertEqual(out, "je fais |cffffff00|Hquest:783:1|h[A Threat Within]|h|r, j'en suis a 4 sur 10")
        self.assertIn("4/10 Kobold Vermin", llm.calls[0][0]["content"])

    def test_rejects_remote_lm_url(self):
        with self.assertRaises(ValueError):
            B.Bridge("http://192.168.1.5:1234/v1", "m", self.tmp)

    def test_http_kobold_format(self):
        b = self.make(FakeLLM("salut l'ami, ça va ?"))
        srv = ThreadingHTTPServer(("127.0.0.1", 0), B.make_handler(b))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            url = "http://127.0.0.1:%d/api/v1/generate" % srv.server_address[1]
            r = urllib.request.Request(url, data=json.dumps(req()).encode("utf-8"), method="POST",
                                       headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(r, timeout=5) as resp:
                raw = resp.read().decode("utf-8")
            self.assertIn('"text": "salut l\'ami, ça va ?"', raw)  # UTF-8 brut, pas de ç
        finally:
            srv.shutdown()


if __name__ == "__main__":
    unittest.main(verbosity=1)
