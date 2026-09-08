#!/usr/bin/env python3
"""Tests RM3004 — chemins historiques : table inverse et historical_target (karl_api_routes), compteur + journal (note_historical_path,
info puis debug, par client), GET /api/log/historical sur le vrai Handler, et un appel /api/… qui ne compte pas."""
import http.client
import importlib.util
import json
import os
import pathlib
import sys
import threading
import time
from http.server import ThreadingHTTPServer

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
JDIR = "/tmp/karl-journal-test-hist"; os.environ["KARL_JOURNAL_DIR"] = JDIR; os.environ["KARL_JOURNAL_STDERR"] = "0"; os.environ["KARL_JOURNAL_LEVEL"] = "debug"
spec = importlib.util.spec_from_file_location("karl_agent", HERE / "karl-agent.py"); ka = importlib.util.module_from_spec(spec); sys.modules["karl_agent"] = ka; spec.loader.exec_module(ka)
import karl_api_routes as R  # noqa: E402
import pm_log  # noqa: E402

fails = []


def check(name, cond, detail=""):
    print(("✓ " if cond else "✗ ") + name + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


check("table inverse : un chemin historique par cible (les doublons de la carte n'en font qu'un)", len(R.CURRENT_TO_TARGET) == len(set(R.TARGET_TO_CURRENT.values())) and R.CURRENT_TO_TARGET["/sessions"] == "/api/session/sessions")
check("historical_target : exact, suffixe, cible /api → None, inconnu → None", R.historical_target("/sessions") == "/api/session/sessions" and R.historical_target("/resolve/42") == "/api/ticket/resolve/42" and R.historical_target("/api/session/sessions") is None and R.historical_target("/nope") is None)
check("api_alias reste l'inverse", R.api_alias(R.historical_target("/resolve/42")) == "/resolve/42" and R.api_alias("/api/log/historical") == "/log/historical")
ka._HIST.clear(); ka._HIST_SEEN.clear()
p = pathlib.Path(JDIR) / "karl-agent.jsonl"; p.parent.mkdir(parents=True, exist_ok=True); p.write_text("")
check("note : cible rendue, /api ignoré", ka.note_historical_path("/sessions", "curl/8", "127.0.0.1") == "/api/session/sessions" and ka.note_historical_path("/api/session/sessions", "curl/8", "127.0.0.1") is None and ka.note_historical_path("/inconnu", "", "") is None)
ka.note_historical_path("/sessions", "curl/8", "127.0.0.1"); ka.note_historical_path("/sessions", "python-urllib/3", "10.0.0.1"); ka.note_historical_path("/resolve/7", "", "10.0.0.2")
st = ka.op_historical_paths()
check("compteurs par chemin et par sorte de client", st["total"] == 4 and st["paths"][0]["path"] == "/sessions" and st["paths"][0]["n"] == 3 and st["paths"][0]["clients"] == {"curl": 2, "python": 1} and st["paths"][1]["path"] == "/resolve/7" and st["paths"][1]["clients"] == {"sans-ua": 1} and st["paths"][0]["target"] == "/api/session/sessions", json.dumps(st))
recs = [json.loads(l) for l in p.read_text().splitlines() if "historique" in l]
lv = [(r["path"], r["client"], r["level"]) for r in recs]
check("journal : info à la première occurrence par (chemin, client), debug ensuite", lv == [("/sessions", "curl", "info"), ("/sessions", "curl", "debug"), ("/sessions", "python", "info"), ("/resolve/7", "sans-ua", "info")], str(lv))
ka._HIST_SEEN[("/sessions", "curl")] -= ka._HIST_INFO_EVERY_S + 1; ka.note_historical_path("/sessions", "curl/8", "127.0.0.1")
recs = [json.loads(l) for l in p.read_text().splitlines() if "historique" in l]; check("après une heure : info à nouveau", recs[-1]["level"] == "info" and recs[-1]["n"] == 4)
check("client_kind", ka._client_kind("Mozilla/5.0") == "mozilla" and ka._client_kind("okhttp/4") == "okhttp" and ka._client_kind("") == "sans-ua" and ka._client_kind("MonAppli/1") == "monappli/1")

ka.AUTH_TOKEN = None; ka.BASIC_USER = None; ka.BASIC_PASS = None; ka._HIST.clear(); ka._HIST_SEEN.clear()
srv = ThreadingHTTPServer(("127.0.0.1", 0), ka.Handler); srv.daemon_threads = True; port = srv.server_address[1]; threading.Thread(target=srv.serve_forever, daemon=True).start()
def get(path, ua="test/1"):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=5); c.request("GET", path, headers={"User-Agent": ua}); r = c.getresponse(); body = r.read(); c.close(); return r.status, body
try:
    st1, _ = get("/help"); st2, _ = get("/api/session/cockpit-config"); st3, _ = get("/cockpit-config")
    check("public, /api et /cockpit-config : servis, non comptés", st1 == 200 and st2 == 200 and st3 == 200 and ka.op_historical_paths()["total"] == 0, str(ka.op_historical_paths()))
    st4, _ = get("/voice/caps", ua="curl/8"); st5, _ = get("/api/voice/caps", ua="curl/8")
    stx, body = get("/api/log/historical"); d = json.loads(body)
    check("un chemin historique est compté, sa cible /api ne l'est pas ; /api/log/historical le montre", st4 == 200 and st5 == 200 and stx == 200 and d["total"] == 1 and d["paths"][0]["path"] == "/voice/caps" and d["paths"][0]["clients"] == {"curl": 1} and "since" in d, body[:200])
finally:
    srv.shutdown()

print()
if fails:
    print(f"✗ {len(fails)} échec(s) : " + ", ".join(fails)); sys.exit(1)
print("OK — chemins historiques RM3004")
