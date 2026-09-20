#!/usr/bin/env python3
"""Tests RM3070 L4 — l'isolation des sessions, et les gestes partagés réservés en multi.

« Authentifié » ne veut pas dire « isolé ». Trois choses étaient ouvertes à tout compte du cockpit :
le moteur `shell` (un shell de connexion sous le compte de service, donc ses droits UNIX complets),
le déverrouillage du coffre et de l'agent SSH (partagés par le processus : les ouvrir, c'est les
ouvrir pour tout le monde), et la liste des sessions (celles des autres comprises).

En MONO, rien ne change : le seul développeur est administrateur de fait.

Lancer : python3 scripts/test_karl_agent_isolation.py
"""
import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
fails = []


def check(name, cond, detail=""):
    print(("✓ " if cond else "✗ ") + name + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


spec = importlib.util.spec_from_file_location("ka", HERE / "karl-agent.py")
ka = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(ka)
except SystemExit:
    pass


def mode(m):
    ka._INSTALL_CACHE.update({"at": 9e9, "etat": {"mode": m, "source": "test", "signals": {},
                                                  "can": {"sudo_root": False}, "warnings": []}})


def err(fn, *a, **k):
    try:
        fn(*a, **k)
    except ka.ApiError as e:
        return e
    return None


# la garde testée est celle du MOTEUR : on ne veut pas dépendre de l'état tmux de la machine
# (une session homonyme, ou un tmux injoignable en environnement purgé, répondrait avant elle)
ka._has_session = lambda rm_id: False

ALICE = {"mode": "device", "user": "alice", "admin": False}
ADMIN = {"mode": "device", "user": "mathieu", "admin": True}

print("[L4] le moteur « shell » donne les droits du compte de service")
mode("multi")
e = err(ka.op_spawn, {"rm_id": "999123", "engine": "shell"}, ALICE)
check("multi, non-admin : refusé, en disant pourquoi",
      e and e.code == 403 and "compte de service" in e.msg, str(e))
mode("mono")
e = err(ka.op_spawn, {"rm_id": "999123", "engine": "shell"}, ALICE)
check("mono : pas ce refus-là (le seul développeur est administrateur de fait)",
      not (e and e.code == 403 and "compte de service" in e.msg), str(e))

print("\n[L4] coffre et agent SSH : partagés, donc réservés en multi")
mode("multi")
e = err(ka._guard_secret_route, ALICE)
check("multi, non-admin : refusé", e and e.code == 403 and "partagés" in e.msg, str(e))
check("multi, admin : passe", err(ka._guard_secret_route, ADMIN) is None)
mode("mono")
check("mono, non-admin : passe comme avant", err(ka._guard_secret_route, ALICE) is None)

print("\n[L4] chacun ne voit que ses sessions")
S = [{"rm_id": "1", "owner": "alice"}, {"rm_id": "2", "owner": "bob"}, {"rm_id": "3", "owner": ""}]
mode("mono")
check("mono : aucun filtrage (rien ne disparaît en mettant à jour)",
      [s["rm_id"] for s in ka._mes_sessions(S, ALICE)] == ["1", "2", "3"])
mode("multi")
check("multi : alice voit la sienne, pas celle de bob",
      [s["rm_id"] for s in ka._mes_sessions(S, ALICE)] == ["1"],
      str([s["rm_id"] for s in ka._mes_sessions(S, ALICE)]))
check("…une session d'AVANT (sans propriétaire) ne lui est pas attribuée",
      all(s["owner"] == "alice" for s in ka._mes_sessions(S, ALICE)))
check("l'administrateur voit tout — sinon personne ne reprend la session d'un absent",
      len(ka._mes_sessions(S, ADMIN)) == 3)
mode("mono")

print("\n[L4] le propriétaire est inscrit dans la fiche, pas dans le nom tmux")
src = (HERE / "karl-agent.py").read_text(encoding="utf-8")
check("_record_key accepte un propriétaire", "def _record_key(" in src and "owner: str | None = None" in src)
check("…et le spawn le pose depuis l'identité COCKPIT, pas le compte UNIX du démon",
      'owner=str((auth_ctx or {}).get("user") or "") or None' in src)
check("renommer les sessions tmux n'a PAS été fait (celles qui tournent survivent)",
      's:<user>:' not in src and 'f"s:{' not in src.replace('f"s:{rm_id}"', ""))

print()
if fails:
    print(f"✗ {len(fails)} échec(s) : " + ", ".join(fails)); sys.exit(1)
print("OK — isolation des sessions et gestes partagés (RM3070 L4)")
