#!/usr/bin/env python3
"""Tests RM2718 — statut de session « à tester » (`[A TESTER]`).

Ce qui compte ici n'est pas qu'un troisième libellé existe, mais que les DEUX
bouts de la chaîne s'accordent : le skill `/session-mark` ÉCRIT un marqueur dans
le titre de la session, karl-agent le RELIT depuis le transcript. Les deux
tables vivent dans deux fichiers que rien ne relie — d'où le test d'aller-retour
ci-dessous, qui échouera le jour où l'un des deux bougera seul.

On protège aussi la sémantique, seule raison d'être du statut :
  - `[A TESTER]` n'est PAS `[DONE]` → la session ne sort pas du jeu ;
  - `[A TESTER]` n'est PAS `[WIP]`  → elle ne se relance pas au démarrage ;
  - un statut en chasse un autre, mais un `[RM1222]` (identité) survit.

Lancer : python3 scripts/test_session_mark.py
"""
import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


ms = load("mark_session", ROOT / "skills" / "session-mark" / "mark-session.py")
ka = load("karl_agent", HERE / "karl-agent.py")

fails = []


def check(name, cond, detail=""):
    print(("✓ " if cond else "✗ ") + name + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


# — le skill : composition du titre —
check("« à tester » a son marqueur", ms.marked_title("a-tester", "Machin") == "[A TESTER] Machin",
      ms.marked_title("a-tester", "Machin"))
check("alias reconnus (atester/tester/test)",
      {ms.marked_title(a, "M") for a in ("atester", "tester", "test")} == {"[A TESTER] M"})
check("un statut en CHASSE un autre (wip → à tester)",
      ms.marked_title("a-tester", "[WIP] Machin") == "[A TESTER] Machin")
check("…et réciproquement (à tester → wip)",
      ms.marked_title("wip", "[A TESTER] Machin") == "[WIP] Machin")
check("marquer deux fois ne double pas le marqueur (idempotent)",
      ms.marked_title("a-tester", ms.marked_title("a-tester", "Machin")) == "[A TESTER] Machin")
check("le ticket est une IDENTITÉ : il survit au marquage",
      ms.marked_title("a-tester", "[RM1222] [WIP] Machin") == "[A TESTER] [RM1222] Machin")
check("clear retire aussi le nouveau marqueur",
      ms.marked_title("clear", "[A TESTER] [RM1222] Machin") == "[RM1222] Machin")
check("variante accentuée acceptée en LECTURE",
      ms.marked_title("clear", "[À TESTER] Machin") == "Machin")
check("…mais seule la forme ASCII est ÉCRITE",
      "À" not in ms.marked_title("a-tester", "Machin"))
check("un [A TESTER] en FIN de titre est du texte, pas un statut",
      ms.marked_title("done", "Machin [A TESTER]") == "[DONE] Machin [A TESTER]")

# — l'aller-retour skill → karl-agent : le contrat entre les deux fichiers —
for status, key in (("done", "done"), ("wip", "wip"), ("a-tester", "test")):
    title = ms.marked_title(status, "[RM1222] Migration ERP")
    m = ka._MARK_RE.match(title)
    check(f"karl-agent relit le marqueur écrit pour « {status} » → {key}",
          ka._mark_key(m) == key, f"{title!r} → {ka._mark_key(m)!r}")
    check(f"…et retrouve le titre nu ({status})",
          ka._MARK_RE.sub("", title) == "[RM1222] Migration ERP")
check("karl-agent tolère la variante accentuée",
      ka._mark_key(ka._MARK_RE.match("[À TESTER] X")) == "test")
check("pas de marqueur → pas de statut inventé",
      ka._mark_key(ka._MARK_RE.match("Migration ERP")) is None)
check("un marqueur inconnu n'est pas un statut",
      ka._mark_key(ka._MARK_RE.match("[RM1222] X")) is None)

# — la sémantique côté karl-agent : ni évincée, ni relancée —
MARKS = {}
ka._transcript_info = lambda sid, engine=None: {"mark": MARKS.get(sid)}
MARKS.update({"s-wip": "wip", "s-done": "done", "s-test": "test", "s-nu": None})
check("[A TESTER] ne se relance PAS au démarrage (comme [DONE], pas comme [WIP])",
      [ka._default_restart(s) for s in ("s-wip", "s-test", "s-done", "s-nu")]
      == ["auto", "idle", "idle", "idle"])
check("[A TESTER] ne sort PAS du jeu (contrairement à [DONE])",
      [ka._is_marked_done(s) for s in ("s-test", "s-done")] == [False, True])

# — critère de jeu dérivé : « ce qui attend mon test » —
def rule_error(rule):
    """Message d'erreur de _rule_norm, ou None si la règle passe."""
    try:
        ka._rule_norm(rule)
        return None
    except ka.ApiError as e:
        return f"{e.code}:{e.message}" if hasattr(e, "message") else f"{e.code}:{e}"


check("rule.mark = test accepté (un jeu « ce qui attend mon test » est possible)",
      ka._rule_norm({"mark": "test"}) == {"mark": "test"})
check("les trois statuts restent des critères valides",
      all(ka._rule_norm({"mark": m}) == {"mark": m} for m in ka.MARKS))
err = rule_error({"mark": "zzz"})
check("un statut inventé est refusé (400)", err is not None and err.startswith("400:"), str(err))
check("…et le message ÉNUMÈRE les statuts valides (sinon on cherche à l'aveugle)",
      err is not None and all(m in err for m in ka.MARKS), str(err))

# — panneau de reprise : ce que le filtre laisse voir —
# Le défaut du panneau est `not-done` : une session livrée doit y RESTER (c'est
# celle qu'on rouvre si le test échoue), là où une session terminée en sort.
ka._runs_by_session = lambda: {}
ka._list_sessions = lambda: []
ka.CLAUDE_STORES = []
ka._pm_project_of_cwd = lambda cwd: (None, None)
ka._ENGINE_LIST = {"claude": lambda: [
    ("s-wip", {"title": "[WIP] A", "cwd": "/x", "mtime": 4}),
    ("s-test", {"title": "[A TESTER] B", "cwd": "/x", "mtime": 3}),
    ("s-done", {"title": "[DONE] C", "cwd": "/x", "mtime": 2}),
    ("s-nu", {"title": "D", "cwd": "/x", "mtime": 1}),
]}


def sids(qs):
    return [e["session_id"] for e in ka.op_resumable(qs)]


check("défaut du panneau (sauf terminées) : la session à tester reste visible",
      sids({"status": "not-done"}) == ["s-wip", "s-test", "s-nu"], str(sids({"status": "not-done"})))
check("filtre explicite « à tester » : elle seule", sids({"status": "test"}) == ["s-test"],
      str(sids({"status": "test"})))
check("le filtre [WIP] ne ramène pas les à tester", sids({"status": "wip"}) == ["s-wip"])
check("le titre exposé est débarrassé du marqueur",
      [e["title"] for e in ka.op_resumable({"status": "test"})] == ["B"])

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests statut de session « à tester » RM2718 passent")
