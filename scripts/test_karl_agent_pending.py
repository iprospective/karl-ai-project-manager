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


# — RM2466 étape 2 : worklog de session rangé en sections —
ITEMS = [
    {"ref": "RM1", "status": "en_cours", "opened_status": "en_cours", "label": "en cours"},
    {"ref": "RM2", "status": "a_tester_demandeur", "opened_status": "nouveau", "label": "livré"},
    {"ref": "RM3", "status": "ferme", "opened_status": "nouveau", "label": "fini"},
    {"ref": "chantier-libre", "status": "à_faire", "opened_status": "", "label": "hors ticket"},
]
b = ka.worklog_buckets(ITEMS)
check("reste à faire / en attente / fait, chacun dans sa section",
      [len(b["todo"]), len(b["waiting"]), len(b["done"])] == [2, 1, 1])
check("un statut de livraison compte comme « en attente » (pas comme fait)",
      b["waiting"][0]["ref"] == "RM2")
check("un chantier hors ticket a sa place dans le worklog",
      any(e["ref"] == "chantier-libre" for e in b["todo"]))
check("dérive signalée quand le statut a bougé depuis l'ouverture",
      b["waiting"][0]["drifted"] is True and b["done"][0]["drifted"] is True)
check("pas de dérive quand rien n'a bougé", b["todo"][0]["drifted"] is False)
check("opened_status vide ne fabrique pas une fausse dérive",
      [e for e in b["todo"] if e["ref"] == "chantier-libre"][0]["drifted"] is False)
check("statut inconnu → rangé dans « reste à faire » (jamais escamoté)",
      len(ka.worklog_buckets([{"ref": "RM9", "status": "statut_exotique"}])["todo"]) == 1)
check("worklog vide ou absent toléré",
      ka.worklog_buckets([]) == {"todo": [], "waiting": [], "done": []}
      and ka.worklog_buckets(None) == {"todo": [], "waiting": [], "done": []})
# la classification DOIT rester celle de pm-session-status : deux vérités
# divergentes sur « où on en est » seraient pires que pas de panneau du tout
import re as _re
_src = (HERE / "pm-session-status.py").read_text(encoding="utf-8")
_done = eval(_re.search(r"^DONE = (\{[^}]*\})", _src, _re.M).group(1))
_wait = eval(_re.search(r"^WAITING = (\{[^}]*\})", _src, _re.M | _re.S).group(1))
check("DONE identique à celui de pm-session-status.py", ka.WORKLOG_DONE == _done)
check("WAITING identique à celui de pm-session-status.py", ka.WORKLOG_WAITING == _wait)

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests pending RM2466 passent")
