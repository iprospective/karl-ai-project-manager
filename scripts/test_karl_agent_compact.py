#!/usr/bin/env python3
"""Tests RM3249 — compacter la conversation d'une session depuis sa tuile.

Ce que ces tests protègent :

  * **la commande vient du moteur, pas du client.** Le cockpit demande « compacte » ;
    le serveur sait comment CE moteur le dit. Un moteur sans commande (shell) est
    refusé en 409 et sa tuile n'offre pas le geste (`can_compact` absent).
  * **jamais hors repos.** Pendant un tour, la ligne se mêlerait à la saisie ; sur
    une question, « /compact » partirait comme RÉPONSE au menu affiché. Refus 409,
    et rien n'est tapé.
  * **la séquence de touches** : la commande en littéral (`-l --`), puis Entrée.

Unitaire (sans tmux). Lancer : python3 scripts/test_karl_agent_compact.py
"""
import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import test_support  # noqa: E402
test_support.hermetic_core()

spec = importlib.util.spec_from_file_location("karl_agent", HERE / "karl-agent.py")
ka = importlib.util.module_from_spec(spec)
sys.modules["karl_agent"] = ka
spec.loader.exec_module(ka)

fails = []


def check(name, cond, detail=""):
    print(("✓ " if cond else "✗ ") + name + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


# — la table : chaque moteur à TUI dit sa commande, le shell n'en a pas —
check("claude → /compact", ka._compact_cmd("claude") == "/compact")
check("opencode → /compact", ka._compact_cmd("opencode") == "/compact")
check("vibe → /compact", ka._compact_cmd("vibe") == "/compact")
check("shell → aucune", ka._compact_cmd("shell") is None)
check("moteur inconnu ou absent → aucune", ka._compact_cmd("xyz") is None and ka._compact_cmd(None) is None)

# — op_compact —
calls = []
ka._tmux = lambda *a, timeout=10: (calls.append(a), (0, "", ""))[1]
ka._has_session = lambda rm_id: True
ka._jlog = lambda *a, **k: None
ETAT = {"engine": "claude", "state": "idle"}
ka._key_info = lambda rm_id: {"engine": ETAT["engine"]}
ka._session_state = lambda rm_id, engine: ETAT["state"]

r = ka.op_compact({"rm_id": "42"})
sent = [c for c in calls if c[0] == "send-keys"]
check("au repos : la commande est tapée en littéral", ("-l", "--", "/compact") == sent[0][-3:], sent)
check("…puis Entrée", len(sent) == 2 and sent[1][-1] == "Enter", sent)
check("…et la réponse dit ce qui a été tapé", r["cmd"] == "/compact" and r["engine"] == "claude" and r["sent"])


def refus(nom, code):
    calls.clear()
    try:
        ka.op_compact({"rm_id": "42"})
        check(nom, False, "aucun refus")
    except ka.ApiError as e:
        check(nom, e.code == code and not [c for c in calls if c[0] == "send-keys"], f"{e.code} {calls}")


for st in ("working", "attention", "choice"):
    ETAT["state"] = st
    refus(f"session {st} → 409, rien de tapé", 409)
ETAT.update(state="idle", engine="shell")
refus("moteur sans commande → 409, rien de tapé", 409)
ETAT["engine"] = "claude"
ka._has_session = lambda rm_id: False
refus("session absente → 404", 404)

# — la liste des sessions annonce le droit, jamais la commande —
src = (HERE / "karl-agent.py").read_text(encoding="utf-8")
check("la liste pose `can_compact` depuis la table des moteurs",
      'if _compact_cmd(s.get("engine")):' in src and 's["can_compact"] = True' in src)
check("la route POST /compact est servie", 'if path == "/compact":' in src)
routes = (HERE / "karl_api_routes.py").read_text(encoding="utf-8")
check("…et son alias /api/session/compact est déclaré", "/api/session/compact" in routes)

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests compaction RM3249 passent")
