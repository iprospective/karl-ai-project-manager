#!/usr/bin/env python3
"""Tests RM2395 — jeux de sessions enregistrés (1re étape : store + save/get).

Unitaire (sans tmux ni réseau) : résolution user/group (défauts superadmin/
default), op_session_set_save (instantané), op_session_set_get (relecture +
état alive), préservation d'autostart à l'écrasement, coexistence des groupes
nommés, plafond, et correctif RM1941 (_record_key mémorise/préserve le modèle).
Lancer : python3 scripts/test_karl_agent_session_set.py
"""
import importlib.util
import json
import pathlib
import sys
import tempfile

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


# — store en tmpdir, sessions/clés simulées (pas de tmux) —
TMP = pathlib.Path(tempfile.mkdtemp())
ka.SESSION_SET_FILE = TMP / "session-set.json"

LIVE = {}   # sid → key info (engine, session_id, cwd, model)
ka._list_sessions = lambda: [{"rm_id": sid} for sid in LIVE]
ka._key_info = lambda sid: LIVE.get(sid)

LIVE.update({
    "2395": {"engine": "claude", "session_id": "uuid-2395", "cwd": "/zfs/a", "model": "opus"},
    "worm-x": {"engine": "claude", "session_id": "uuid-worm", "cwd": "/zfs/b", "model": None},
})

# — résolution user/group : défauts superadmin / default —
check("user : auth ouverte (user None) → superadmin", ka._session_set_user({"user": None}) == "superadmin")
check("user : ctx None → superadmin", ka._session_set_user(None) == "superadmin")
check("user : compte nommé normalisé (minuscule)", ka._session_set_user({"user": "Alice"}) == "alice")
check("group : défaut → default", ka._session_set_group(None) == "default")
try:
    ka._session_set_group("bad group!")
    check("group : nom invalide refusé", False)
except ka.ApiError as e:
    check("group : nom invalide refusé (400)", e.code == 400)

# — save : instantané des vivantes sous superadmin/default —
r = ka.op_session_set_save({}, {"user": None})
check("save : couple par défaut superadmin/default", r["user"] == "superadmin" and r["group"] == "default")
check("save : 2 entrées instantanées", r["count"] == 2)
e2395 = next(e for e in r["entries"] if e["sid"] == "2395")
check("save : champs capturés (engine/session_id/cwd/model)",
      e2395 == {"sid": "2395", "engine": "claude", "session_id": "uuid-2395",
                "cwd": "/zfs/a", "model": "opus"})

# — persistance disque : schéma users → groups (anticipation multi-user/jeux) —
store = json.loads(ka.SESSION_SET_FILE.read_text())
check("disque : schéma users/superadmin/groups/default",
      "default" in store["users"]["superadmin"]["groups"])
check("disque : version posée", store.get("version") == 1)

# — get : relit + marque alive selon l'état tmux courant —
g = ka.op_session_set_get({}, {"user": None})
check("get : exists + count", g["exists"] and g["count"] == 2)
check("get : toutes vivantes", all(e["alive"] for e in g["entries"]))
del LIVE["worm-x"]   # une session disparaît
g = ka.op_session_set_get({}, {"user": None})
alive = {e["sid"]: e["alive"] for e in g["entries"]}
check("get : session disparue → alive False, entrée conservée",
      alive == {"2395": True, "worm-x": False})

# — écrasement : re-save préserve autostart et rafraîchit l'instantané —
store = ka._session_set_load()
store["users"]["superadmin"]["groups"]["default"]["autostart"] = True
ka._write_json_atomic(ka.SESSION_SET_FILE, store)
ka.op_session_set_save({}, {"user": None})
g = ka.op_session_set_get({}, {"user": None})
check("save : autostart préservé à l'écrasement", g["autostart"] is True)
check("save : instantané rafraîchi (worm-x parti)", g["count"] == 1)

# — anticipation multi-jeux : un groupe nommé coexiste avec default —
ka.op_session_set_save({"group": "nuit"}, {"user": None})
store = ka._session_set_load()
check("save : groupe nommé coexiste avec default",
      set(store["users"]["superadmin"]["groups"]) == {"default", "nuit"})

# — get sur jeu absent —
g = ka.op_session_set_get({"group": "vide"}, {"user": None})
check("get : jeu absent → exists False", g["exists"] is False and g["entries"] == [])

# — plafond : un instantané trop gros est refusé —
LIVE.clear()
LIVE.update({str(i): {"engine": "claude", "session_id": f"u{i}", "cwd": "/x", "model": None}
             for i in range(ka.SESSION_SET_MAX + 1)})
try:
    ka.op_session_set_save({}, {"user": None})
    check("save : plafond dépassé refusé", False)
except ka.ApiError as e:
    check("save : plafond dépassé refusé (409)", e.code == 409)

# — correctif RM1941 : _record_key mémorise le modèle et le préserve à la reprise —
LIVE.clear()
KLOG = TMP / "state"
ka.LOG_DIR = KLOG
ka.SESS_DIR = KLOG / "sessions"
ka._record_key("2395", "claude", "uuid-z", "/zfs/z", model="sonnet")
key = json.loads((KLOG / "keys" / "RM2395.json").read_text())
check("record_key : modèle mémorisé au spawn", key.get("model") == "sonnet")
ka._record_key("2395", "claude", "uuid-z", "/zfs/z")   # reprise, sans model
key = json.loads((KLOG / "keys" / "RM2395.json").read_text())
check("record_key : modèle préservé à la reprise", key.get("model") == "sonnet")

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests jeux de sessions RM2395 passent")
