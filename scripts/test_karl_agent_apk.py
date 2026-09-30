#!/usr/bin/env python3
"""Tests RM2331 — GET /app/karl-cockpit.apk sur le vrai Handler : route PUBLIQUE même
auth active (on installe l'app avant d'avoir un jeton), 404 lisible tant que rien n'est
publié, type MIME Android + pièce jointe une fois build-apk.sh passé.

Lancer : python3 scripts/test_karl_agent_apk.py
"""
import http.client
import importlib.util
import os
import pathlib
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
# journal du test isolé : jamais dans celui de l'agent en service
os.environ["KARL_JOURNAL_DIR"] = tempfile.mkdtemp(prefix="karl-apk-journal-"); os.environ["KARL_JOURNAL_STDERR"] = "0"
spec = importlib.util.spec_from_file_location("karl_agent", HERE / "karl-agent.py")
ka = importlib.util.module_from_spec(spec); sys.modules["karl_agent"] = ka; spec.loader.exec_module(ka)

fails = []


def check(name, cond, detail=""):
    print(("✓ " if cond else "✗ ") + name + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


tmp = pathlib.Path(tempfile.mkdtemp(prefix="karl-apk-"))
ka.STATE_DIR = tmp
ka.AUTH_TOKEN = "secret-partage"          # auth ACTIVE : la route doit rester publique
srv = ThreadingHTTPServer(("127.0.0.1", 0), ka.Handler); srv.daemon_threads = True
port = srv.server_address[1]; threading.Thread(target=srv.serve_forever, daemon=True).start()


def get(path):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=5); c.request("GET", path)
    r = c.getresponse(); body = r.read(); h = dict(r.getheaders()); c.close(); return r.status, h, body


try:
    st, _, body = get("/app/karl-cockpit.apk")
    check("rien de publié → 404 qui dit comment publier", st == 404 and b"build-apk.sh" in body, f"{st} {body[:80]!r}")
    (tmp / "app").mkdir(); apk = b"PK\x03\x04" + b"x" * 1000; (tmp / "app" / "karl-cockpit.apk").write_bytes(apk)
    st, h, body = get("/app/karl-cockpit.apk")
    check("publié → 200 sans jeton, octets identiques", st == 200 and body == apk, str(st))
    check("type MIME Android + pièce jointe", h.get("Content-Type") == "application/vnd.android.package-archive"
          and 'filename="karl-cockpit.apk"' in h.get("Content-Disposition", ""), str(h))
    st, _, _ = get("/app/../app/karl-cockpit.apk")
    check("seul le chemin exact est servi (pas de résolution de chemin)", st != 200, str(st))
    st, _, _ = get("/app/autre.apk")
    check("autre fichier du dossier : non servi publiquement", st == 401, str(st))
finally:
    srv.shutdown()

print(f"\n{'✓ OK' if not fails else '✗ ÉCHECS : ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
