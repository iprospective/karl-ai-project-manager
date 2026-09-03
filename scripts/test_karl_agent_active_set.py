#!/usr/bin/env python3
"""Tests RM2953 — « default » est le REGISTRE des sessions actives.

Ce que le demandeur a décidé (2026-09-03) : une session s'ajoute à `default` à
la création et à la reprise, elle en sort quand elle est marquée `[DONE]` ET
éteinte. Le jeu courant redevient un pur filtre d'affichage.

Ce que ces tests protègent :
  - l'adhésion vise `default`, MÊME quand le jeu courant est autre chose — y
    compris un jeu DÉRIVÉ, cas qui la refusait en silence (`reason: "derive"`)
    et laissait des sessions enregistrées nulle part ;
  - aucun plafond sur le registre : un registre qui refuse des entrées ment sur
    ce qui tourne. Les jeux manuels gardent le leur ;
  - le rattrapage : une session vivante absente du registre y entre au fil du
    poll, sans geste ;
  - la sortie est bien `[DONE]` ET éteinte — une `[DONE]` qui tourne encore reste
    inscrite ;
  - ⊖ sur une session VIVANTE du registre est refusé : elle reviendrait au poll
    suivant, et un geste qui se défait tout seul n'est pas un geste (RM2952).

Lancer : python3 scripts/test_karl_agent_active_set.py
"""
import importlib.util
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("karl_agent", HERE / "karl-agent.py")
ka = importlib.util.module_from_spec(spec)
sys.modules["karl_agent"] = ka
spec.loader.exec_module(ka)

fails = []


def check(name, cond, detail=""):
    print(("✓ " if cond else "✗ ") + name + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


TMP = pathlib.Path(tempfile.mkdtemp())
ka.SESSION_SET_FILE = TMP / "session-set.json"

LIVE = {}          # sid → info de clé (ce qui tourne)
MARKS = {}         # session_id → marque [WIP]/[DONE]
ka._list_sessions = lambda: [{"rm_id": sid} for sid in LIVE]
ka._has_session = lambda sid: sid in LIVE
ka._key_info = lambda sid: LIVE.get(sid) or KEYS.get(sid)
ka._session_mark = lambda sid: MARKS.get(sid)
ka._is_marked_done = lambda sid: MARKS.get(sid) == "done"
ka._transcript_title = lambda sid: None
ka._transcript_age = lambda sid: None
ka._pm_project_of_cwd = lambda cwd: (None, None)
ka._all_keys = lambda: list(KEYS.items())
KEYS = {}


def reg():
    """Les sid inscrits au registre."""
    return {e["sid"] for e in
            ka.op_session_set_get({"group": "default"}, {"user": None})["entries"]}


def demarre(sid, cwd="/zfs/ws"):
    info = {"engine": "claude", "session_id": "uuid-" + sid, "cwd": cwd, "model": None}
    LIVE[sid] = info
    KEYS[sid] = info
    return info


# ── 1. l'adhésion vise le registre, pas le jeu courant ───────────────────────
demarre("8001")
r = ka._auto_join_active_set("8001", {"user": None})
check("une session créée entre au registre « default »",
      r["joined"] is True and r["group"] == "default" and "8001" in reg(), r)

ka.op_session_set_create({"group": "chantier", "label": "Chantier"}, {"user": None})
ka.op_session_set_current({"group": "chantier"}, {"user": None})
demarre("8002")
r = ka._auto_join_active_set("8002", {"user": None})
check("jeu courant AUTRE : la session va quand même au registre",
      r["group"] == "default" and "8002" in reg(), r)
check("…et le jeu courant n'a rien reçu",
      ka.op_session_set_get({"group": "chantier"}, {"user": None})["entries"] == [])

# le cas qui a motivé le ticket : jeu courant DÉRIVÉ ⇒ plus rien n'était enregistré
ka.op_session_set_create({"group": "pm", "rule": {"client": "iprospective"}}, {"user": None})
ka.op_session_set_current({"group": "pm"}, {"user": None})
demarre("8003")
r = ka._auto_join_active_set("8003", {"user": None})
check("jeu courant DÉRIVÉ : la session est enregistrée au lieu d'être perdue",
      r["joined"] is True and "8003" in reg(), r)

r = ka._auto_join_active_set("8003", {"user": None})
check("adhésion idempotente", r["joined"] is False and r["reason"] == "deja")

# ── 2. pas de plafond sur le registre ────────────────────────────────────────
GARDE = ka.SESSION_SET_MAX
ka.SESSION_SET_MAX = 2
for sid in ("8101", "8102", "8103", "8104"):
    demarre(sid)
    ka._auto_join_active_set(sid, {"user": None})
check("le registre n'a pas de plafond (4 entrées avec SESSION_SET_MAX=2)",
      {"8101", "8102", "8103", "8104"} <= reg(), sorted(reg()))
try:
    ka.op_session_set_save({"group": "chantier", "sids": ["8101", "8102", "8103"]}, {"user": None})
    check("un jeu MANUEL garde son plafond", False)
except ka.ApiError as e:
    check("un jeu MANUEL garde son plafond", e.code == 409, f"{e.code} {e.msg}")
ka.SESSION_SET_MAX = GARDE

# ── 3. rattrapage : ce qui tourne finit inscrit, sans geste ──────────────────
demarre("8201")
demarre("8202")
check("les nouvelles vivantes ne sont pas encore inscrites",
      not ({"8201", "8202"} & reg()))
ka._ghost_sessions({"user": None})          # un simple passage du poll
check("le poll rattrape les sessions vivantes absentes du registre",
      {"8201", "8202"} <= reg(), sorted(reg()))

# ── 4. la sortie, c'est [DONE] ET éteinte ────────────────────────────────────
MARKS["uuid-8201"] = "done"                  # marquée terminée, mais elle TOURNE
ka._ghost_sessions({"user": None})
check("une session [DONE] encore vivante reste inscrite", "8201" in reg())
del LIVE["8201"]                             # elle s'éteint
ka._ghost_sessions({"user": None})
check("[DONE] + éteinte ⇒ elle sort du registre", "8201" not in reg(), sorted(reg()))

del LIVE["8202"]                             # éteinte, mais pas marquée terminée
ka._ghost_sessions({"user": None})
check("éteinte sans marque ⇒ elle RESTE (tuile grise, invariant RM2439)",
      "8202" in reg())

# ── 5. ⊖ sur une vivante du registre : refusé, avec le motif ─────────────────
try:
    ka.op_session_set_delete({"group": "default", "sid": "8202"}, {"user": None})
    check("⊖ sur une session ÉTEINTE du registre : accepté", "8202" not in reg())
except ka.ApiError as e:
    check("⊖ sur une session ÉTEINTE du registre : accepté", False, f"{e.code} {e.msg}")
try:
    ka.op_session_set_delete({"group": "default", "sid": "8001"}, {"user": None})
    check("⊖ sur une session VIVANTE du registre : refusé", False)
except ka.ApiError as e:
    check("⊖ sur une session VIVANTE du registre : refusé (409, motivé)",
          e.code == 409 and ("registre" in e.msg or "tourne" in e.msg), f"{e.code} {e.msg}")
check("…et elle est toujours inscrite", "8001" in reg())

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests registre des sessions actives RM2953 passent")
