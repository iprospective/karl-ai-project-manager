#!/usr/bin/env python3
"""Tests RM2691 — op_spawn répond pour TOUS les moteurs, pas seulement claude.

Régression corrigée : `joined` n'était affecté que dans la branche
`if session_id:` (posée uniquement pour claude, RM1939 set-at-launch) mais lu
inconditionnellement dans le `return` → tout /spawn shell/opencode/vibe
répondait 500 « UnboundLocalError », alors que la session tmux était bien
créée (l'appelant relançait et tombait sur le 409 « session déjà active »).

Unitaire (sans tmux, sans réseau) : tmux et les écritures d'index sont doublés,
c'est la VRAIE op_spawn qui est appelée.
Lancer : python3 scripts/test_karl_agent_spawn_engines.py
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


# — harnais : rien ne sort du process (ni tmux, ni disque) —
started = []
recorded = []
ka._has_session = lambda rm_id: False
# RM2951 : /spawn et /resume vérifient que la session a SURVÉCU avant de
# répondre « créée ». Point de mesure distinct de la garde « déjà active »,
# que ce harnais fige à False pour pouvoir enchaîner les lancements.
ka._session_started = lambda rm_id: True
ka._start_session_tmux = lambda rm_id, cmd, cwd, w, h, env: started.append((rm_id, cmd))
ka._resolve_cwd = lambda c: pathlib.Path(c or "/zfs/workspaces")
ka._record_run = lambda *a, **k: recorded.append(("run", a))
ka._record_key = lambda *a, **k: recorded.append(("key", a))
ka._auto_join_current_set = lambda sid, ctx=None: {"group": "default", "joined": True}

# — chaque moteur du catalogue doit rendre une réponse, pas une exception —
for engine in ka.ENGINES:
    started.clear()
    try:
        res = ka.op_spawn({"rm_id": "demo", "engine": engine,
                           "cwd": "/zfs/workspaces"}, {"user": None})
    except Exception as exc:                       # y compris UnboundLocalError
        check(f"spawn {engine} : réponse rendue ({type(exc).__name__})", False)
        continue
    check(f"spawn {engine} : réponse rendue",
          res.get("created") is True and res.get("engine") == engine)
    check(f"spawn {engine} : la session tmux a bien été démarrée", len(started) == 1)
    check(f"spawn {engine} : champ `set` toujours présent", "set" in res)

# — claude : set-at-launch ⇒ clé enregistrée + adhésion au jeu (non-régression) —
recorded.clear()
res = ka.op_spawn({"rm_id": "demo", "engine": "claude", "cwd": "/zfs/workspaces"},
                  {"user": None})
check("claude : session_id fixé au lancement", bool(res.get("session_id")))
check("claude : clé de session enregistrée",
      any(kind == "key" for kind, _ in recorded))
check("claude : jeu courant rejoint", res["set"] == {"group": "default", "joined": True})

# — sans set-at-launch : pas d'adhésion, et la raison est DITE (pas un None nu) —
for engine in ("shell", "opencode", "vibe"):
    recorded.clear()
    res = ka.op_spawn({"rm_id": "demo", "engine": engine, "cwd": "/zfs/workspaces"},
                      {"user": None})
    check(f"{engine} : pas de session_id (capture différée)",
          res.get("session_id") is None)
    check(f"{engine} : aucune clé/jonction écrite", recorded == [])
    check(f"{engine} : `set` explicite plutôt que muet",
          res["set"] == {"group": None, "joined": False, "reason": "sans-session-id"})

# — le front (RM2450) ne doit rien casser sur cette forme : il ne réagit qu'à
#   `joined === false && reason === "plein"` —
check("la forme rendue n'est pas confondue avec le refus « jeu plein »",
      res["set"]["reason"] != "plein")

print(("ÉCHECS : " + ", ".join(fails)) if fails
      else "OK — tous les tests spawn multi-moteur passent")
sys.exit(1 if fails else 0)
