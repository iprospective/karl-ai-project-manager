#!/usr/bin/env python3
"""Tests RM2466 volet 2 — agrégat « en attente de toi » (pending_entries).

Unitaire (sans tmux ni transcript) : la fonction est pure, on lui passe les
sessions et les deux sources de questions.
Lancer : python3 scripts/test_karl_agent_pending.py
"""
import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("karl_agent", HERE / "karl-agent.py")
ka = importlib.util.module_from_spec(spec)
sys.modules["karl_agent"] = ka
spec.loader.exec_module(ka)

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


SESSIONS = [
    {"rm_id": "100", "state": "idle", "created": 10, "client": "acme", "project": "shop"},
    {"rm_id": "200", "state": "choice", "created": 20},
    {"rm_id": "300", "state": "working", "created": 30},
    {"rm_id": "400", "state": "attention", "created": 40},
]
UNRESOLVED = {"100": [{"text": "On garde l'ancien nom ?", "full": "détail 1"}],
              "300": [{"text": "Quelle base ?", "full": "détail 2"}]}
QUESTIONS = {"200": "Quelle option pour le cadrage ?", "400": "On continue ?"}

e = ka.pending_entries(SESSIONS, UNRESOLVED, QUESTIONS)
check("les deux signaux remontent (2 live + 2 en souffrance)",
      [x["kind"] for x in e] == ["live", "live", "stale", "stale"])
check("les sessions BLOQUÉES passent devant celles qui traînent une question",
      e[0]["kind"] == "live" and e[-1]["kind"] == "stale")
check("à égalité de nature, la session la plus récemment active d'abord",
      [x["rm_id"] for x in e[:2]] == ["400", "200"]
      and [x["rm_id"] for x in e[2:]] == ["300", "100"])
check("une question live porte le texte capturé à l'écran",
      e[1]["text"] == "Quelle option pour le cadrage ?")
check("une question en souffrance porte son texte et son détail",
      e[3]["text"] == "On garde l'ancien nom ?" and e[3]["full"] == "détail 1")
check("l'état de la session est transmis (icône côté UI)",
      e[0]["state"] == "attention" and e[1]["state"] == "choice")
check("client / projet repris quand ils sont connus",
      e[3]["client"] == "acme" and e[3]["project"] == "shop")
check("une session sans rien en attente n'apparaît pas",
      all(x["rm_id"] != "999" for x in e))

# une même session peut être bloquée MAINTENANT et traîner une vieille question :
# ce sont deux entrées distinctes, pas un doublon à écraser.
deux = ka.pending_entries(
    [{"rm_id": "500", "state": "attention", "created": 1}],
    {"500": [{"text": "vieille question", "full": ""}]},
    {"500": "question à l'écran"})
check("bloquée ET en souffrance → deux entrées, la bloquée d'abord",
      [x["kind"] for x in deux] == ["live", "stale"]
      and deux[0]["text"] == "question à l'écran")

# un état bloqué sans texte capturable ne doit pas disparaître silencieusement
muet = ka.pending_entries([{"rm_id": "600", "state": "choice", "created": 1}], {}, {})
check("bloquée sans texte lisible : signalée quand même",
      len(muet) == 1 and muet[0]["kind"] == "live" and muet[0]["text"])

# les sessions ENREGISTRÉES mais pas démarrées n'attendent rien de personne
fantome = ka.pending_entries(
    [{"rm_id": "700", "state": "ghost", "ghost": True, "created": 1},
     {"rm_id": "701", "state": "attention", "ghost": True, "created": 2}],
    {"700": [{"text": "q", "full": ""}]}, {"701": "q"})
check("une session fantôme n'attend rien (ni live ni en souffrance)", fantome == [])

check("aucune session → aucune entrée", ka.pending_entries([], {}, {}) == [])
check("sources absentes tolérées", ka.pending_entries(None, {}, {}) == []
      and len(ka.pending_entries(SESSIONS, {}, {})) == 2)

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests pending RM2466 passent")
