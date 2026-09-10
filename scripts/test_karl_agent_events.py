#!/usr/bin/env python3
"""Tests RM3006 — canal de push : bus d'événements, publication (validation), trame SSE, pm_events (best-effort), et le canal
/api/session/events de bout en bout sur un serveur local (hello, topics à la publication, fermeture propre).
Lancer : python3 scripts/test_karl_agent_events.py"""
import http.client
import importlib.util
import json
import os
import pathlib
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
os.environ["KARL_JOURNAL_DIR"] = "/tmp/karl-journal-test-events"; os.environ["KARL_JOURNAL_STDERR"] = "0"
spec = importlib.util.spec_from_file_location("karl_agent", HERE / "karl-agent.py")
ka = importlib.util.module_from_spec(spec); sys.modules["karl_agent"] = ka; spec.loader.exec_module(ka)
import pm_events  # noqa: E402

fails = []


def check(name, cond, detail=""):
    print(("✓ " if cond else "✗ ") + name + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


# — bus —
bus = ka._EventBus()
check("bus vierge : seq 0, rien depuis 0", bus.seq == 0 and bus.topics_since(0) == [] and bus.wait(0, 0.01) == 0)
s1 = bus.publish(["tickets", "worklog"], source="t"); s2 = bus.publish(["tickets", "mail"], source="t")
check("publish incrémente et garde les sujets dédoublonnés", (s1, s2) == (1, 2) and bus.topics_since(0) == ["tickets", "worklog", "mail"] and bus.topics_since(1) == ["tickets", "mail"])
woke = []
def waiter():
    woke.append(bus.wait(2, 5.0))
th = threading.Thread(target=waiter); th.start(); time.sleep(0.1); bus.publish(["sessions"]); th.join(2)
check("wait est réveillé par une publication", woke == [3])
for i in range(300):
    bus.publish(["env"])
check("historique borné", len(bus.last) <= 201)

# — op_events_publish —
try:
    ka.op_events_publish({"topics": []}); check("topics vide refusé", False)
except ka.ApiError as e:
    check("topics vide refusé (400)", e.code == 400)
try:
    ka.op_events_publish({"topics": ["tickets", "zz"]}); check("sujet inconnu refusé", False)
except ka.ApiError as e:
    check("sujet inconnu refusé (400), liste des connus donnée", e.code == 400 and "zz" in e.msg and "tickets" in e.msg)
before = ka.EVENTS.seq
r = ka.op_events_publish({"topics": ["tickets"], "source": "x" * 200, "rm_id": "42"}, {"user": "mathieu"})
check("publication acceptée : seq avance, source bornée", r["ok"] and r["seq"] == before + 1 and len(ka.EVENTS.last[r["seq"]]["source"]) == 80 and ka.EVENTS.last[r["seq"]]["user"] == "mathieu")
check("trame SSE", ka._sse_frame("topics", {"a": 1}) == b'event: topics\ndata: {"a": 1}\n\n')

# — pm_events : best-effort contre un faux karl-agent —
received = []
class Fake(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0")) or "0") or b"{}")
        received.append((self.path, self.headers.get("X-Karl-Token"), body))
        code = 400 if "zz" in body.get("topics", []) else 200
        out = json.dumps({"ok": code == 200}).encode(); self.send_response(code); self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out)
    def log_message(self, *a): pass
srv = HTTPServer(("127.0.0.1", 0), Fake); port = srv.server_address[1]; threading.Thread(target=srv.serve_forever, daemon=True).start()
os.environ["KARL_AGENT_PORT"] = str(port); os.environ["KARL_AGENT_TOKEN"] = "secret"; os.environ.pop("PM_EVENTS_DISABLE", None)
check("publish → POST /api/session/events/publish avec le jeton et les champs", pm_events.publish(["tickets", "inconnu"], source="test", rm_id="7") is True and received[-1][0] == "/api/session/events/publish" and received[-1][1] == "secret" and received[-1][2] == {"topics": ["tickets"], "source": "test", "rm_id": "7"}, str(received))
check("aucun sujet connu → rien envoyé", pm_events.publish(["inconnu"]) is False and len(received) == 1)
os.environ["PM_EVENTS_DISABLE"] = "1"; check("PM_EVENTS_DISABLE=1 coupe", pm_events.publish(["tickets"]) is False and len(received) == 1); os.environ.pop("PM_EVENTS_DISABLE")
srv.shutdown(); os.environ["KARL_AGENT_PORT"] = str(port)
t0 = time.time(); check("karl-agent absent : False, vite, sans exception", pm_events.publish(["tickets"]) is False and time.time() - t0 < 2)

# — le canal de bout en bout sur le vrai Handler (auth ouverte) —
ka.AUTH_TOKEN = None; ka.BASIC_USER = None; ka.BASIC_PASS = None
sse = ThreadingHTTPServer(("127.0.0.1", 0), ka.Handler); sse.daemon_threads = True; sport = sse.server_address[1]
threading.Thread(target=sse.serve_forever, daemon=True).start()
def read_event(resp, want, deadline=5.0):
    """Lit des lignes jusqu'à `event: <want>` puis rend sa data."""
    end = time.time() + deadline; ev = None
    while time.time() < end:
        line = resp.readline().decode("utf-8").rstrip("\n")
        if line.startswith("event: "): ev = line[7:]
        elif line.startswith("data: ") and ev == want: return json.loads(line[6:])
    return None
try:
    c = http.client.HTTPConnection("127.0.0.1", sport, timeout=5); c.request("GET", "/api/session/events?blocks=")
    resp = c.getresponse()
    check("GET /api/session/events → 200 text/event-stream", resp.status == 200 and "text/event-stream" in resp.getheader("Content-Type", ""))
    hello = read_event(resp, "hello")
    check("première trame : hello (seq, blocs, heartbeat)", hello is not None and hello["blocks"] == [] and hello["heartbeat_s"] == ka.EVENT_HEARTBEAT_S, str(hello))
    time.sleep(0.2); check("un auditeur compté", ka.EVENTS.listeners == 1)
    c2 = http.client.HTTPConnection("127.0.0.1", sport, timeout=5); body = json.dumps({"topics": ["tickets", "worklog"], "source": "test"})
    c2.request("POST", "/api/session/events/publish", body=body, headers={"Content-Type": "application/json", "Content-Length": str(len(body))}); pr = json.loads(c2.getresponse().read())
    check("POST publish → ok + auditeurs", pr.get("ok") and pr.get("listeners") == 1, str(pr))
    top = read_event(resp, "topics")
    check("le canal reçoit les sujets publiés", top is not None and top["topics"] == ["tickets", "worklog"], str(top))
    resp.close(); c.close(); time.sleep(1.6)   # la boucle du canal sonde le socket à chaque tour (≤ 1 s)
    check("client parti → auditeur décompté sans attendre une publication", ka.EVENTS.listeners == 0, str(ka.EVENTS.listeners))
    c3 = http.client.HTTPConnection("127.0.0.1", sport, timeout=5); c3.request("GET", "/api/session/events?blocks=zz:"); r3 = c3.getresponse(); h3 = read_event(r3, "hello")
    c4 = http.client.HTTPConnection("127.0.0.1", sport, timeout=5); c4.request("POST", "/api/session/events/publish", body=json.dumps({"topics": ["env"]}), headers={"Content-Type": "application/json"}); c4.getresponse().read()
    top3 = read_event(r3, "topics", 5.0) if h3 else None
    check("un bloc inconnu ne casse pas le canal : les sujets arrivent, aucun bloc n'est poussé", h3 is not None and h3["blocks"] == ["zz"] and top3 is not None and top3["topics"] == ["env"], str((h3, top3)))
    c3.close()
finally:
    sse.shutdown()

print()
if fails:
    print(f"✗ {len(fails)} échec(s) : " + ", ".join(fails)); sys.exit(1)
print("OK — canal de push RM3006")
