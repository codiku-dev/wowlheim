#!/usr/bin/env python3
"""Tests de la route /intent (intent.py) avec un faux Jev : aucun appel reseau.

  python -I bots/llm_bridge/test_intent.py
"""
import io
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
import intent as I  # noqa: E402


class FakeJev:
    """Classe selon une table message normalise -> (etiquette, confiance)."""

    def __init__(self, table=None, default=("discussion", 0.95), delay=0.0, fail=False):
        self.table, self.default, self.delay, self.fail = table or {}, default, delay, fail
        self.calls = []
        self.lock = threading.Lock()

    def __call__(self, state):
        with self.lock:
            self.calls.append(state)
        time.sleep(self.delay)
        if self.fail:
            raise TimeoutError("jev lent")
        msg = state.rsplit(" : ", 1)[-1]
        return self.table.get(I.normalize(msg), self.default)


def read_log(d):
    with open(os.path.join(d, "intent_log.jsonl"), encoding="utf-8") as f:
        return f.read()


def req(message, channel="whisper", relation="groupe", bot="Thorgrim", other="Robin"):
    return {"bot": bot, "other": other, "channel": channel, "relation": relation, "message": message}


class IntentTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def make(self, jev=None, **kw):
        return I.IntentClassifier(self.tmp, classify=jev or FakeJev(), **kw)

    def test_phrases_de_robin(self):
        jev = FakeJev({
            "tu viens on va aux mortemines": ("aller_donjon", 0.93),
            "attends moi devant la porte": ("rester", 0.97),
            "on fait la quete des kobolds ensemble": ("quete_ensemble", 0.9),
            "tape celui la": ("attaquer", 0.91),
            "rejoins moi a hurlevent": ("rejoindre", 0.88),
            "tu peux quitter le groupe": ("quitter", 0.95),
            "ouvre l echange": ("echanger", 0.9),
            "passe moi le lead": ("donner_chef", 0.9),
            "ramasse le loot": ("ramasser", 0.9),
            "ca va": ("discussion", 0.99),
        })
        c = self.make(jev)
        cases = {
            "tu viens on va aux mortemines ?": "follow",
            "attends moi devant la porte": "stay",
            "on fait la quête des kobolds ensemble ?": "follow",
            "tape celui-là": "attack",
            "rejoins moi à Hurlevent": "follow",   # jamais de teleportation (retour Robin)
            "tu peux quitter le groupe": "leave",
            "ouvre l'échange": "",   # pas d echange impose (retour Robin)
            "passe moi le lead": "give leader",
            "ramasse le loot": "loot",
            "ça va ?": "",
        }
        for msg, cmd in cases.items():
            r = c.handle(req(msg))
            self.assertEqual(r["command"], cmd, msg)
            self.assertIn(r["command"], I.ALLOWED_COMMANDS | {""})

    def test_toutes_les_commandes_existent(self):
        # Chaque commande possible est un declencheur de ChatTriggerContext.h (verifie a la main) et
        # figure dans la liste blanche cote C++.
        cmds = set(I.COMMANDS_IN_GROUP.values()) | set(I.MASTER_ONLY.values()) | {"invite"}
        self.assertEqual(cmds - {""}, I.ALLOWED_COMMANDS)
        self.assertEqual(set(I.COMMANDS_IN_GROUP), set(I.INTENTS))

    def test_seuil_de_confiance(self):
        c = self.make(FakeJev(default=("suivre", 0.79)))
        r = c.handle(req("viens par la toi"))
        self.assertEqual((r["command"], r["intent"]), ("", "suivre"))
        c = self.make(FakeJev(default=("suivre", 0.8)))
        self.assertEqual(c.handle(req("viens par la toi"))["command"], "follow")

    def test_relation(self):
        jev = FakeJev({"on va aux mortemines": ("aller_donjon", 0.95), "suis moi": ("suivre", 0.95),
                       "tu veux grouper": ("grouper", 0.95)})
        c = self.make(jev)
        self.assertEqual(c.handle(req("on va aux mortemines", relation="inconnu"))["command"], "invite")
        self.assertEqual(c.handle(req("suis moi", relation="inconnu"))["command"], "")
        self.assertEqual(c.handle(req("suis moi", relation="maitre"))["command"], "follow")
        self.assertEqual(c.handle(req("tu veux grouper", relation="groupe"))["command"], "")
        self.assertEqual(c.handle(req("tu veux grouper", relation="maitre"))["command"], "invite")
        # Un inconnu n'est ecoute qu'en chuchotement.
        self.assertEqual(c.handle(req("on va aux mortemines", channel="party", relation="inconnu"))["command"], "")

    def test_canaux_et_longueur(self):
        jev = FakeJev(default=("suivre", 0.99))
        c = self.make(jev)
        for ch in ("say", "directly", "general", "guild", "", "yell"):
            self.assertEqual(c.handle(req("viens avec moi stp", channel=ch))["command"], "", ch)
        self.assertEqual(c.handle(req("viens avec moi stp", channel="in party chat"))["command"], "follow")
        self.assertEqual(c.handle(req("x" * 256))["command"], "")
        self.assertEqual(c.handle(req(".gm on"))["command"], "")
        self.assertEqual(c.handle(req("viens", bot="../x"))["command"], "")
        self.assertEqual(len(jev.calls), 1)

    def test_interrupteurs(self):
        jev = FakeJev(default=("suivre", 0.99))
        self.assertEqual(self.make(jev, enabled=False).handle(req("viens avec moi"))["command"], "")
        c = self.make(jev)
        open(os.path.join(self.tmp, "intent_off"), "w").close()
        self.assertEqual(c.handle(req("viens avec moi"))["command"], "")
        os.remove(os.path.join(self.tmp, "intent_off"))
        self.assertEqual(c.handle(req("viens avec moi"))["command"], "follow")
        self.assertEqual(len(jev.calls), 1)

    def test_erreurs_donnent_commande_vide(self):
        self.assertEqual(self.make(FakeJev(fail=True)).handle(req("viens"))["command"], "")
        self.assertEqual(self.make(FakeJev(default=("danser", 0.99))).handle(req("viens"))["command"], "")
        self.assertEqual(self.make().handle(None)["command"], "")
        self.assertEqual(self.make().handle({"message": 3})["command"], "")
        # Sans cle : commande vide, pas d'exception.
        c = I.IntentClassifier(self.tmp, key_path=os.path.join(self.tmp, "absente.txt"))
        r = c.handle(req("viens avec moi"))
        self.assertEqual(r["command"], "")
        log = read_log(self.tmp)
        self.assertIn("exception:RuntimeError", log)

    def test_cache_et_appels_concurrents(self):
        jev = FakeJev(default=("suivre", 0.95), delay=0.2)
        c = self.make(jev)
        out = []
        ths = [threading.Thread(target=lambda b=b: out.append(c.handle(req("allez on y va les gars", "party",
                                                                            bot=b))["command"]))
               for b in ("Thorgrim", "Bimlink", "Kedries", "Valando")]
        [t.start() for t in ths]
        [t.join() for t in ths]
        self.assertEqual(out, ["follow"] * 4)
        self.assertEqual(len(jev.calls), 1)  # 4 bots du groupe, 1 seul appel Jev
        c.handle(req("Allez, on y va les gars !", "party"))
        self.assertEqual(len(jev.calls), 1)
        # Expiration du cache.
        now = [1000.0]
        c2 = self.make(jev, clock=lambda: now[0], cache_ttl=60)
        c2.handle(req("allez on y va")); now[0] += 61; c2.handle(req("allez on y va"))
        self.assertEqual(len(jev.calls), 3)

    def test_ordre_a_un_autre_bot(self):
        jev = FakeJev(default=("rester", 0.95))
        c = self.make(jev, known_bots=lambda: {"Bimlink", "Thorgrim"})
        self.assertEqual(c.handle(req("Bimlink attends moi la", "party"))["command"], "")
        self.assertEqual(c.handle(req("Thorgrim attends moi la", "party"))["command"], "stay")

    def test_journal(self):
        c = self.make(FakeJev(default=("rester", 0.95)))
        c.handle(req("attends moi devant la porte"))
        lines = read_log(self.tmp).splitlines()
        e = json.loads(lines[-1])
        self.assertEqual((e["intent"], e["cmd"], e["why"], e["ch"]), ("rester", "stay", "ok", "whisper"))

    def test_appel_jev_format(self):
        """Corps envoye a Jev, en-tete d'autorisation, delai, lecture de la reponse ; cle jamais journalisee."""
        seen = {}

        class Resp(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake_urlopen(r, timeout=None):
            seen.update(url=r.full_url, auth=r.get_header("Authorization"), body=json.loads(r.data), timeout=timeout)
            return Resp(json.dumps({"answers": {"intention": {"type": "choice", "choice": "rester",
                                                              "confidence": 0.91}}}).encode())

        keyf = os.path.join(self.tmp, "k.txt")
        with open(keyf, "w") as f:
            f.write("SECRET-TEST-KEY\n")
        orig = urllib.request.urlopen
        urllib.request.urlopen = fake_urlopen
        try:
            r = I.IntentClassifier(self.tmp, key_path=keyf).handle(req("attends moi devant la porte"))
        finally:
            urllib.request.urlopen = orig
        self.assertEqual(r, {"command": "stay", "intent": "rester", "confidence": 0.91})
        self.assertEqual(seen["url"], I.JEV_URL)
        self.assertEqual(seen["auth"], "Bearer SECRET-TEST-KEY")
        self.assertEqual(seen["timeout"], 2.0)
        q = seen["body"]["questions"]["intention"]
        self.assertEqual((seen["body"]["model"], q["type"]), ("jev-latest", "choice"))
        self.assertEqual(set(q["criteria"]), set(I.INTENTS))
        self.assertIn("attends moi devant la porte", seen["body"]["state"])
        log = read_log(self.tmp)
        self.assertNotIn("SECRET", log)

    def test_route_http(self):
        b = B.Bridge("http://127.0.0.1:1", "m", self.tmp, generate=lambda m: "ok")
        srv = ThreadingHTTPServer(("127.0.0.1", 0), B.make_handler(b))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        url = "http://127.0.0.1:%d/intent" % srv.server_address[1]

        def post(obj):
            r = urllib.request.Request(url, data=json.dumps(obj).encode(), method="POST",
                                       headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(r, timeout=5) as resp:
                return json.loads(resp.read())
        try:
            # Sans classifieur (pont lance sans route) : commande vide.
            self.assertEqual(post(req("suis moi"))["command"], "")
            b.intent = self.make(FakeJev(default=("suivre", 0.97)))
            self.assertEqual(post(req("tu viens avec moi ?")),
                             {"command": "follow", "intent": "suivre", "confidence": 0.97})
        finally:
            srv.shutdown()
            srv.server_close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
