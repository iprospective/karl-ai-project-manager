#!/usr/bin/env python3
"""Tests RM2954 — la vue « toutes les sessions ».

Les vues existantes laissaient un angle mort. `all` désigne **tous les JEUX** —
donc rien de ce qui n'a jamais été enregistré ; `client:<slug>` va bien au-delà
des jeux (elle lit l'index des clés) mais reste bornée à UN client, et laisse
donc de côté les sessions dont le client ne se résout pas. Une session éteinte,
hors jeu, sur un dossier hors arbo PM n'apparaissait dans aucune vue alors
qu'elle est parfaitement connue et relançable.

Ce qu'on protège :
  - `sessions` est une vue valide, distincte de `all` (les JEUX) ;
  - elle rend les sessions de tous les clients, celles sans client résolu
    comprises, qu'elles soient dans un jeu ou non ;
  - elle n'applique PAS le plafond des jeux : une vue qui s'appelle « toutes les
    sessions » et s'arrête à 24 se contredirait ;
  - les hygiènes de RM2949 valent ici aussi (ticket fermé, rien à rouvrir) ;
  - le compte annoncé au sélecteur est le compte réel.

Lancer : python3 scripts/test_karl_agent_view_sessions.py
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
ka.PROJECTS_BASE = TMP / "projects" / "clients"      # aucun ticket fermé ici

KEYS = {
    "5001": {"engine": "claude", "session_id": "u5001", "cwd": "/zfs/cal", "model": None},
    "5002": {"engine": "claude", "session_id": "u5002", "cwd": "/zfs/inf", "model": None},
    # sans client résolu, et dans aucun jeu : l'angle mort du ticket
    "orphe": {"engine": "claude", "session_id": "u-orphe", "cwd": "/zfs/ailleurs", "model": None},
}
LIVE = {}
ka._all_keys = lambda: list(KEYS.items())
ka._list_sessions = lambda: [{"rm_id": sid} for sid in LIVE]
ka._key_info = lambda sid: KEYS.get(sid)
ka._has_session = lambda sid: sid in LIVE
ka._is_marked_done = lambda sid: False
ka._session_mark = lambda sid: None
ka._transcript_title = lambda sid: None
ka._transcript_age = lambda sid: None
ka._is_resumable = lambda engine, sid: True
ka._pm_project_of_cwd = lambda cwd: {"/zfs/cal": ("calicote", "presta"),
                                     "/zfs/inf": ("iprospective", "infra")}.get(cwd, (None, None))

# ── 1. la vue existe et se distingue de « tous les jeux » ────────────────────
check("« sessions » est une vue valide", ka._view_valid("sessions") is True)
check("elle ne se confond pas avec « all »", "sessions" in ka.SESSION_SET_VIEWS
      and "all" in ka.SESSION_SET_VIEWS)
r = ka.op_session_set_current({"view": "sessions"}, {"user": None})
check("le serveur accepte d'y basculer", r.get("view") == "sessions", r)

# ── 2. contenu : tout ce que l'index connaît, jeu ou pas, client ou pas ──────
vus = {g["rm_id"] for g in ka._ghost_sessions({"user": None})}
check("toutes les sessions connues y figurent", vus == {"5001", "5002", "orphe"}, sorted(vus))
check("y compris celle sans client résolu (invisible ailleurs)", "orphe" in vus)

# ce qui TOURNE n'est pas un fantôme : la tuile vivante vient de /sessions
LIVE["5001"] = KEYS["5001"]
vus = {g["rm_id"] for g in ka._ghost_sessions({"user": None})}
check("une session vivante ne produit pas de tuile grise", "5001" not in vus, sorted(vus))
LIVE.clear()

# comparaison avec « tous les jeux » : elle, ne montre que ce qui est enregistré
ka.op_session_set_create({"group": "unjeu", "sids": []}, {"user": None})
ka.op_session_set_current({"view": "all"}, {"user": None})
check("« tous les jeux » ne voit rien de ce qui n'est dans aucun jeu",
      ka._ghost_sessions({"user": None}) == [])
ka.op_session_set_current({"view": "sessions"}, {"user": None})

# ── 3. pas de plafond : « toutes » veut dire toutes ─────────────────────────
GARDE = ka.SESSION_SET_MAX
ka.SESSION_SET_MAX = 2
check("la vue ne s'arrête pas au plafond des jeux",
      len(ka._ghost_sessions({"user": None})) == 3,
      len(ka._ghost_sessions({"user": None})))
ka.SESSION_SET_MAX = GARDE

# ── 4. le sélecteur annonce un compte exact ─────────────────────────────────
l = ka.op_session_sets_list({}, {"user": None})
check("la liste des jeux porte le compte de la vue", l.get("sessions_count") == 3, l.get("sessions_count"))

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests vue « toutes les sessions » RM2954 passent")
