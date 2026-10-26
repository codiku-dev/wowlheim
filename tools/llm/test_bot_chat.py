"""Tests unitaires (faux serveur HTTP sur 127.0.0.1, port ephemere).
Lancer : python -I tools/llm/test_bot_chat.py
"""
import http.server
import importlib.util
import json
import os
import socket
import threading
import time
import unittest

_here = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("bot_chat", os.path.join(_here, "bot_chat.py"))
bc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bc)

PERSONA = bc.DEMO_PERSONA
CTX = {"zone": "Elwynn", "lieu": "auberge", "joueur": "Salut"}


class Handler(http.server.BaseHTTPRequestHandler):
    mode = "ok"
    reply = "Salut voyageur !"
    last_body = None

    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        Handler.last_body = json.loads(self.rfile.read(n))
        m = Handler.mode
        if m == "slow":
            time.sleep(1.5)
        if m == "500":
            self.send_response(500); self.end_headers(); return
        body = b"pas du json" if m == "garbage" else json.dumps(
            {"choices": [{"message": {"content": Handler.reply}}]} if m != "nochoices" else {"choices": []}
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class FilterTests(unittest.TestCase):
    def test_think_tags(self):
        self.assertEqual(bc.filter_reply("<think>hmm\nreflexion</think>Bonjour a toi"), "Bonjour a toi")
        self.assertEqual(bc.filter_reply("reflexion perdue</think> Yo"), "Yo")
        self.assertIsNone(bc.filter_reply("<think>jamais ferme"))

    def test_newlines_quotes_markdown(self):
        self.assertEqual(bc.filter_reply('"Salut\n\nca va ?"'), "Salut ca va ?")
        self.assertEqual(bc.filter_reply("**Gras** et _italique_ # titre"), "Gras et italique titre")
        self.assertEqual(bc.filter_reply("«Ok» l’auberge"), "Ok l'auberge")

    def test_links_refused(self):
        for t in ("va sur http://x.y", "www.truc.fr", "regarde exemple.com", "|cffff0000|Hitem:1|h"):
            self.assertIsNone(bc.filter_reply(t), t)

    def test_truncate(self):
        out = bc.filter_reply("mot " * 200)
        self.assertLessEqual(len(out), bc.MAX_CHARS)
        self.assertFalse(out.endswith(" "))
        self.assertLessEqual(len(bc.filter_reply("x" * 500)), bc.MAX_CHARS)

    def test_empty_and_types(self):
        for t in ("", "   \n ", None, 42):
            self.assertIsNone(bc.filter_reply(t))


class UrlTests(unittest.TestCase):
    def test_validate(self):
        self.assertEqual(bc.validate_base_url("http://127.0.0.1:1234/v1/"), "http://127.0.0.1:1234/v1")
        self.assertEqual(bc.validate_base_url("http://localhost:1234/v1"), "http://localhost:1234/v1")
        for u in ("http://example.com/v1", "http://192.168.1.5:1234/v1", "http://0.0.0.0:1234/v1",
                  "https://127.0.0.1/v1", "http://127.0.0.1@evil.com/v1", "http://localhost.evil.com/v1",
                  "http://user:pw@127.0.0.1/v1", "ftp://localhost/"):
            with self.assertRaises(ValueError, msg=u):
                bc.validate_base_url(u)

    def test_generate_refuses_remote(self):
        with self.assertRaises(ValueError):
            bc.generate_reply(PERSONA, CTX, base_url="http://example.com/v1")


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.url = "http://127.0.0.1:%d/v1" % cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown(); cls.srv.server_close()

    def setUp(self):
        Handler.mode = "ok"; Handler.reply = "Salut voyageur !"

    def test_ok_and_payload(self):
        self.assertEqual(bc.generate_reply(PERSONA, CTX, base_url=self.url), "Salut voyageur !")
        b = Handler.last_body
        self.assertEqual(b["model"], bc.DEFAULT_MODEL)
        self.assertEqual(b["messages"][0]["role"], "system")
        self.assertIn("Thorgrim", b["messages"][0]["content"])
        self.assertIn("Salut", b["messages"][1]["content"])

    def test_custom_model(self):
        bc.generate_reply(PERSONA, CTX, model="autre", base_url=self.url)
        self.assertEqual(Handler.last_body["model"], "autre")

    def test_output_filtered(self):
        Handler.reply = "<think>x</think>\"Ca roule\"\nvoir http://a.b"
        self.assertIsNone(bc.generate_reply(PERSONA, CTX, base_url=self.url))
        Handler.reply = "<think>x</think>\"Ca roule\"\nbien"
        self.assertEqual(bc.generate_reply(PERSONA, CTX, base_url=self.url), "Ca roule bien")

    def test_fallbacks(self):
        for mode in ("500", "garbage", "nochoices"):
            Handler.mode = mode
            self.assertIsNone(bc.generate_reply(PERSONA, CTX, base_url=self.url), mode)

    def test_timeout(self):
        Handler.mode = "slow"
        t = time.time()
        self.assertIsNone(bc.generate_reply(PERSONA, CTX, base_url=self.url, timeout=0.3))
        self.assertLess(time.time() - t, 1.2)

    def test_server_absent(self):
        s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
        self.assertIsNone(bc.generate_reply(PERSONA, CTX, base_url="http://127.0.0.1:%d/v1" % port, timeout=1))


if __name__ == "__main__":
    unittest.main(verbosity=2)
