#!/usr/bin/env python3
"""Tests RM2894 — le LIBELLÉ d'une session vivante est exposé par /sessions.

Le panneau de droite du cockpit affiche le libellé de la session attachée en
en-tête, au-dessus de ses onglets. Il ne pouvait pas : `_sessions_view` servait
`rm_id`, `engine`, `session_id`, l'état… mais jamais le titre. Seules les tuiles
« fantômes » en avaient un (nom mémorisé dans le jeu, RM2439), si bien qu'une
session VIVANTE ancrée sur un slug n'affichait que son nom tmux — qui répète son
identifiant au lieu de la nommer.

Lancer : python3 scripts/test_karl_agent_session_title.py
"""
import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from test_support import hermetic_core          # noqa: E402

hermetic_core()

_spec = importlib.util.spec_from_file_location("karl_agent", HERE / "karl-agent.py")
ka = importlib.util.module_from_spec(_spec)
sys.modules["karl_agent"] = ka
_spec.loader.exec_module(ka)

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


SID_TICKET = "2894"
SID_SLUG = "calicote-presta"
CSID = {SID_TICKET: "aaaaaaaa-1111-2222-3333-444444444444",
        SID_SLUG:   "bbbbbbbb-5555-6666-7777-888888888888"}
TITRES = {CSID[SID_TICKET]: "Cockpit : libellé de session",
          CSID[SID_SLUG]:   "MEP mmi_productcheck"}


def _view(titres):
    """_sessions_view sur deux sessions vivantes, tout le reste neutralisé."""
    ka._list_sessions = lambda: [
        {"rm_id": SID_TICKET, "is_ticket": True, "tmux": "karl-RM2894",
         "created": 100, "attached": False, "activity": 100},
        {"rm_id": SID_SLUG, "is_ticket": False, "tmux": "karl-" + SID_SLUG,
         "created": 200, "attached": False, "activity": 200},
    ]
    ka._key_info = lambda sid: {"engine": "claude", "session_id": CSID.get(sid)}
    ka._runs_by_session = lambda: {}
    ka._session_registry = lambda: {}
    ka._registry_rm_map = lambda reg: {}
    ka._session_state = lambda sid, engine=None: "idle"
    ka._last_message_at = lambda sid, engine=None: None
    ka._ghosts_for = lambda qs, ctx=None: []
    ka._transcript_title = lambda csid: titres.get(csid)
    return {s["rm_id"]: s for s in ka._sessions_view({}, None)}


# 1. le libellé accompagne chaque session vivante — ticket comme slug
v = _view(TITRES)
check("session de ticket : libellé exposé",
      v[SID_TICKET].get("title") == "Cockpit : libellé de session")
check("session ancrée sur un slug : libellé exposé aussi — c'est SON seul nom",
      v[SID_SLUG].get("title") == "MEP mmi_productcheck")

# 2. le libellé est lu sur le transcript de LA session, pas sur un autre
check("le libellé suit le session_id de chaque session",
      v[SID_TICKET]["title"] != v[SID_SLUG]["title"])

# 3. pas de titre → pas de clé : le front distingue « sans libellé » d'un vide
v = _view({})
check("transcript sans titre : aucune clé `title` inventée",
      "title" not in v[SID_TICKET] and "title" not in v[SID_SLUG])

# 4. un titre vide ne crée pas davantage de clé (il ne nommerait rien)
v = _view({CSID[SID_TICKET]: "", CSID[SID_SLUG]: None})
check("titre vide ou None : ignoré",
      "title" not in v[SID_TICKET] and "title" not in v[SID_SLUG])

print()
if fails:
    print(f"✗ {len(fails)} échec(s) : " + ", ".join(fails))
    sys.exit(1)
print("✓ tous les tests passent")
