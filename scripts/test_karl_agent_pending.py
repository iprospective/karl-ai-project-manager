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
# RM2930 : RM2 (a_tester_demandeur) a quitté « en attente » pour « à tester /
# valider » — il attend une action, pas un déblocage.
check("reste à faire / à tester / fait, chacun dans sa section",
      [len(b["todo"]), len(b["testing"]), len(b["waiting"]), len(b["done"])] == [2, 1, 0, 1])
check("un statut de livraison compte comme « à tester » (pas comme fait)",
      b["testing"][0]["ref"] == "RM2")
check("un chantier hors ticket a sa place dans le worklog",
      any(e["ref"] == "chantier-libre" for e in b["todo"]))
check("dérive signalée quand le statut a bougé depuis l'ouverture",
      b["testing"][0]["drifted"] is True and b["done"][0]["drifted"] is True)
check("pas de dérive quand rien n'a bougé", b["todo"][0]["drifted"] is False)
check("opened_status vide ne fabrique pas une fausse dérive",
      [e for e in b["todo"] if e["ref"] == "chantier-libre"][0]["drifted"] is False)
# Un statut hors référentiel n'est PAS « à faire » : le ranger là affirmerait
# ce qu'on ne sait pas. Il a sa propre section, et reste visible.
inc = ka.worklog_buckets([{"ref": "RM9", "status": "statut_exotique"},
                          {"ref": "RM10", "status": "a_teste_demandeur"}])  # faute de frappe
check("statut hors référentiel → « statut inconnu », jamais « reste à faire »",
      len(inc["unknown"]) == 2 and not inc["todo"])
check("un statut mal orthographié se voit au lieu de se fondre",
      any(e["ref"] == "RM10" for e in inc["unknown"]))
check("les statuts NORMS actifs restent bien dans « reste à faire »",
      len(ka.worklog_buckets([{"ref": "RM12", "status": "etude_chiffrage_en_cours"},
                              {"ref": "RM13", "status": "a_corriger"}])["todo"]) == 2)
# RM2860 : la MEP a son bucket. Un ticket dont le dev est fini n'a rien à faire
# parmi ceux qui restent à écrire — et il doit rester ATTEINGNABLE, pas escamoté.
_mep = ka.worklog_buckets([{"ref": "RM11", "status": "a_mep"},
                           {"ref": "RM14", "status": "en_mep"},
                           {"ref": "RM13", "status": "a_corriger"}])
check("a_mep et en_mep vont dans « à mettre en prod », pas dans « reste à faire »",
      len(_mep["mep"]) == 2 and len(_mep["todo"]) == 1)
check("le statut exact reste lisible dans le bucket MEP (a_mep ≠ en_mep)",
      sorted(e["status"] for e in _mep["mep"]) == ["a_mep", "en_mep"])
check("aucun item n'est perdu, quel que soit son statut",
      sum(len(v) for v in ka.worklog_buckets(ITEMS + [{"ref": "RMX", "status": "?"}]).values())
      == len(ITEMS) + 1)
_vide = {"todo": [], "testing": [], "mep": [], "waiting": [], "done": [],
         "unknown": []}
check("worklog vide ou absent toléré",
      ka.worklog_buckets([]) == _vide and ka.worklog_buckets(None) == _vide)
# la classification DOIT rester celle de pm-session-status : deux vérités
# divergentes sur « où on en est » seraient pires que pas de panneau du tout
import re as _re
_src = (HERE / "pm-session-status.py").read_text(encoding="utf-8")
_done = eval(_re.search(r"^DONE = (\{[^}]*\})", _src, _re.M).group(1))
_wait = eval(_re.search(r"^WAITING = (\{[^}]*\})", _src, _re.M | _re.S).group(1))
check("DONE identique à celui de pm-session-status.py", ka.WORKLOG_DONE == _done)
check("WAITING identique à celui de pm-session-status.py", ka.WORKLOG_WAITING == _wait)
_mep_set = eval(_re.search(r"^MEP = (\{[^}]*\})", _src, _re.M).group(1))
check("MEP identique à celui de pm-session-status.py (RM2860)", ka.WORKLOG_MEP == _mep_set)
_test_set = eval(_re.search(r"^TESTING = (\{[^}]*\})", _src, _re.M | _re.S).group(1))
check("TESTING identique à celui de pm-session-status.py (RM2930)",
      ka.WORKLOG_TESTING == _test_set)

# — RM2930 : « à tester / valider » est son propre bucket —
_TEST_ITEMS = [{"ref": "RM%d" % i, "status": st} for i, st in enumerate(
    ["a_valider", "a_tester_demandeur", "a_tester_dev", "a_tester_preprod"])]
_tb = ka.worklog_buckets(_TEST_ITEMS + [{"ref": "RMW", "status": "en_pause"}])
check("les 4 statuts de test/validation vont dans « à tester / valider »",
      len(_tb["testing"]) == 4)
check("aucun d'eux ne retombe dans « en attente / bloqué »",
      [e["ref"] for e in _tb["waiting"]] == ["RMW"])
check("a_tester_preprod n'est plus une MEP (RM2930)",
      "a_tester_preprod" not in ka.WORKLOG_MEP and _tb["mep"] == [])
check("test/validation et attente sont disjoints",
      not (ka.WORKLOG_TESTING & ka.WORKLOG_WAITING))
check("un statut de test/validation n'est pas un statut « à faire »",
      not (ka.WORKLOG_TESTING & ka.WORKLOG_TODO))
check("un statut MEP n'est plus un statut « à faire »",
      not (ka.WORKLOG_MEP & ka.WORKLOG_TODO))

# — RM2581 : superposition du statut LIVE sur le worklog —
_items = [
    {"ref": "RM1", "status": "a_mep", "opened_status": "nouveau"},   # avancé ailleurs
    {"ref": "RM2", "status": "en_cours", "opened_status": "en_cours"},  # inchangé
    {"ref": "chantier-x", "status": "en_cours"},                     # hors ticket
    {"ref": "RM3", "status": "a_faire", "opened_status": "a_faire"},  # pas de live
]
_live = {"RM1": "ferme", "RM2": "en_cours"}   # RM3 absent (MD introuvable)
_ov = ka._worklog_apply_live(_items, _live)
check("live écrase le statut périmé (RM1 a_mep→ferme)", _ov[0]["status"] == "ferme")
check("opened_status préservé pour la dérive", _ov[0]["opened_status"] == "nouveau")
check("statut inchangé si live == stocké", _ov[1]["status"] == "en_cours")
check("chantier hors ticket intact", _ov[2]["status"] == "en_cours")
check("ref sans live garde le statut stocké", _ov[3]["status"] == "a_faire")
check("apply_live ne mute pas l'entrée d'origine", _items[0]["status"] == "a_mep")
check("apply_live tolère vide/None",
      ka._worklog_apply_live([], {}) == [] and ka._worklog_apply_live(None, None) == [])
# la dérive se calcule ensuite normalement sur le statut live
_bk = ka.worklog_buckets(_ov)
check("après live : RM1 classé fait (ferme) et marqué dérivé",
      any(e["ref"] == "RM1" and e["drifted"] for e in _bk["done"]))

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests pending RM2466 + worklog live RM2581 passent")
