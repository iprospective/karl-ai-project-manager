#!/usr/bin/env python3
"""Tests RM3067 — pm-think-classify : extraction SANS tooling, lots, parsing tolérant, écriture idempotente.
Aucun appel de modèle : le moteur est injecté par PM_CLASSIFY_CMD."""
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pm_think                                     # noqa: E402
spec = importlib.util.spec_from_file_location("classify", HERE / "pm-think-classify.py")
C = importlib.util.module_from_spec(spec); spec.loader.exec_module(C)
FAIL = []


def check(label, cond, detail=""):
    print(("  ✓ " if cond else "  ✗ ") + label + ("" if cond else f"  {detail}"))
    if not cond:
        FAIL.append(label)


print("[RM3067] extraction : le tooling ne part JAMAIS au modèle")
lignes = [
    json.dumps({"type": "user", "message": {"content": "Tu deploies pour l'instant en ssh -A, on verra plus tard pour faire plus propre."}}),
    json.dumps({"type": "assistant", "message": {"content": [
        {"type": "thinking", "thinking": "je réfléchis en secret"},
        {"type": "text", "text": "Je propose de garder le repli en dur pour l'instant ; il faudra une conf quand le multi-instance arrivera, sinon on recodera deux fois."},
        {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "rm -rf /tmp/x"}}]}}),
    json.dumps({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "content": "sortie de commande sensible"}]}}),
    json.dumps({"type": "user", "message": {"content": "<command-name>/context</command-name>"}}),
    json.dumps({"type": "user", "message": {"content": "/model"}}),
    json.dumps({"type": "user", "message": {"content": "ok"}}),                       # trop court
    json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "Fait."}]}}),   # trop court
    json.dumps({"type": "user", "isMeta": True, "message": {"content": "meta à ignorer, assez longue pour passer la taille"}}),
]
ts = C.tours(lignes)
check("deux tours de conversation retenus, dans l'ordre", [r for r, _ in ts] == ["M", "A"], str(ts))
joint = " ".join(t for _, t in ts)
for interdit in ("rm -rf", "sortie de commande sensible", "command-name", "je réfléchis en secret", "meta à ignorer"):
    check(f"« {interdit} » n'est pas envoyé au modèle", interdit not in joint)
check("troncature à MAX_CHARS", all(len(t) <= C.MAX_CHARS for _, t in C.tours([json.dumps({"type": "user", "message": {"content": "x" * 5000}})])))

print("\n[RM3067] parsing de la réponse du modèle")
check("tableau nu", [x["t"] for x in C._json_tableau('[{"i":0,"t":"dette"}]')] == ["dette"])
check("tableau entouré de prose et de ```json", [x["i"] for x in C._json_tableau('Voici :\n```json\n[{"i":2,"t":"question"}]\n```\nvoilà')] == [2])
check("réponse illisible → rien, pas d'exception", C._json_tableau("désolé je ne peux pas") == [] and C._json_tableau("") == [])

print("\n[RM3067] classification, avec moteur injecté")
os.environ["PM_CLASSIFY_CMD"] = ("python3 -c \"import sys,json;sys.stdin.read();"
                                 "print(json.dumps([{'i':0,'t':'dette','x':\\\"Le deploiement passe par ssh -A faute de mieux : prevoir un acces propre.\\\"},"
                                 "{'i':1,'t':'rien'},{'i':9,'t':'dette','x':'hors bornes'},{'i':0,'t':'zzz','x':'type inconnu'}]))\"")
lot = [("M", "Tu deploies pour l'instant en ssh -A…"), ("M", "ok merci")]
ret, cout = C.classe(lot)
check("seul l'item valide et dans les bornes est retenu, avec sa reformulation", len(ret) == 1 and ret[0][0] == "M" and ret[0][2] == "dette" and ret[0][3].startswith("Le deploiement"), str(ret))
check("coût rapporté", isinstance(cout, float))

print("\n[RM3067] moteur Ollama (local ou hébergé), sans appel réseau")
import urllib.request
appels = {}


class _Faux:
    def __init__(self, payload): self.payload = payload
    def read(self): return json.dumps(self.payload).encode()
    def __enter__(self): return self
    def __exit__(self, *a): return False


def _urlopen(req, timeout=0):
    appels["url"] = req.full_url; appels["headers"] = dict(req.headers)
    appels["body"] = json.loads(req.data.decode())
    return _Faux({"message": {"content": '[{"i":0,"t":"dette","x":"Le deploiement passe par ssh -A faute de mieux : prevoir un acces propre."}]'}})


vrai = urllib.request.urlopen; urllib.request.urlopen = _urlopen
os.environ["OLLAMA_HOST"] = "https://ollama.example"; os.environ["OLLAMA_API_KEY"] = "cle-de-test"
items, cout = C._ollama("prompt de test", C.MODEL)
check("appelle /api/chat sur l'hôte configuré, avec la clé en Bearer", appels["url"] == "https://ollama.example/api/chat" and appels["headers"].get("Authorization") == "Bearer cle-de-test", str(appels.get("url")))
check("sortie contrainte en JSON, température nulle, pas de flux", appels["body"]["format"] == "json" and appels["body"]["stream"] is False and appels["body"]["options"]["temperature"] == 0)
check("modèle par défaut adapté à Ollama, pas celui d'Anthropic", appels["body"]["model"] != C.MODEL)
check("réponse exploitée, coût nul (abonnement)", len(items) == 1 and items[0]["t"] == "dette" and cout == 0.0)
urllib.request.urlopen = lambda req, timeout=0: _Faux({"message": {"content": '{"resultats": [{"i": 0, "t": "question", "x": "Une question restée ouverte sur le déploiement."}]}'}})
items, _ = C._ollama("p", "qwen3:8b")
check("objet enveloppe toléré (petits modèles bavards)", len(items) == 1 and items[0]["t"] == "question", str(items))
urllib.request.urlopen = vrai; del os.environ["OLLAMA_HOST"]; del os.environ["OLLAMA_API_KEY"]

print("\n[RM3067] moteur OpenAI-compatible (Lemonade Server, vLLM, LM Studio…)")
appels.clear()


def _urlopen2(req, timeout=0):
    appels["url"] = req.full_url; appels["headers"] = dict(req.headers); appels["body"] = json.loads(req.data.decode())
    return _Faux({"choices": [{"message": {"content": '[{"i":0,"t":"feature","x":"Servir le tri par un modele local sur la machine Ryzen AI."}]'}}]})


urllib.request.urlopen = _urlopen2
os.environ["LLM_BASE_URL"] = "http://strix.lan:8000/api/v1"; os.environ["LLM_API_KEY"] = "k"; os.environ["LLM_MODEL"] = "qwen3-14b"
items, cout = C._openai("prompt", C.MODEL)
check("appelle /chat/completions sur la base configurée", appels["url"] == "http://strix.lan:8000/api/v1/chat/completions")
check("modèle et clé pris de l'environnement, JSON demandé, température nulle",
      appels["body"]["model"] == "qwen3-14b" and appels["headers"].get("Authorization") == "Bearer k"
      and appels["body"]["response_format"]["type"] == "json_object" and appels["body"]["temperature"] == 0)
check("réponse exploitée, coût nul (local)", len(items) == 1 and items[0]["t"] == "feature" and cout == 0.0)
urllib.request.urlopen = vrai
for v in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL"):
    os.environ.pop(v, None)

print("\n[RM3067] écriture dans le think, idempotente")
with tempfile.TemporaryDirectory() as tmp:
    tasks = pathlib.Path(tmp); sheet = tasks / "RM88_x.md"; sheet.write_text("---\nredmine_id: 88\ntitle: t\n---\n")

    class Cfg:
        def find_task(self, rm): return sheet if int(rm) == 88 else None
    n1 = C.ecrit(88, ret, sid="s1", cfg=Cfg())
    n2 = C.ecrit(88, ret, sid="s1", cfg=Cfg())
    th = pm_think.think_path(sheet)
    check("écrit une fois, pas deux", (n1, n2) == (1, 0), f"{n1}/{n2}")
    check("la reformulation est consignée en note, signée du demandeur", "faute de mieux" in th.read_text() and "· Mathieu" in th.read_text() or "· M" in th.read_text())
    dec = [("A", "brut", "decision", "On garde le repli en dur jusqu'au multi-instance, décision du 2026-09-10.")]
    C.ecrit(88, dec, sid="s1", cfg=Cfg())
    rows = pm_think.load(th)
    check("une décision va dans la bonne rubrique, à l'état validé", rows["decision"]["rows"] and rows["decision"]["rows"][0]["state"] == "valide")
del os.environ["PM_CLASSIFY_CMD"]

print("\n[RM3067] bout en bout --dry-run (aucune écriture)")
with tempfile.TemporaryDirectory() as tmp:
    tp = pathlib.Path(tmp) / "aaaaaaaa-0000-4000-8000-000000000001.jsonl"
    tp.write_text("\n".join(lignes) + "\n")
    env = dict(os.environ, PM_CLASSIFY_CMD="python3 -c \"import sys,json;sys.stdin.read();print(json.dumps([{'i':0,'t':'dette','x':'Le deploiement passe par ssh -A faute de mieux : prevoir un acces propre.'}]))\"")
    r = subprocess.run([sys.executable, str(HERE / "pm-think-classify.py"), "--transcript", str(tp), "--json"],
                       capture_output=True, text=True, env=env)
    check("sortie JSON exploitable, un retenu, rien d'écrit", r.returncode == 0 and json.loads(r.stdout)["total"]["retenus"] == 1
          and json.loads(r.stdout)["total"]["ecrites"] == 0, (r.stdout + r.stderr)[-300:])

print("\n" + ("ÉCHEC — " + ", ".join(FAIL) if FAIL else "OK — pm-think-classify"))
sys.exit(1 if FAIL else 0)
